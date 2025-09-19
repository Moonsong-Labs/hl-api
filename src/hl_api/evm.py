"""HyperLiquid EVM implementation that routes actions through a strategy contract."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any, cast
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_account import Account
from eth_account.signers.local import LocalAccount
from hexbytes import HexBytes
from web3 import HTTPProvider, Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.types import ChecksumAddress, TxParams

from .abi import HyperliquidStrategy_abi
from .base import HLProtocolBase
from .exceptions import NetworkError, ValidationError
from .types import (
    ApprovalResponse,
    CancelResponse,
    DelegateResponse,
    FinalizeResponse,
    OrderResponse,
    SendResponse,
    StakingResponse,
    TransferResponse,
    VerificationPayload,
)
from .utils import (
    cloid_to_uint128,
    encode_tif,
    format_price_for_api,
    price_to_uint64,
    size_to_uint64,
    uint64_to_price,
    validate_address,
)

logger = logging.getLogger(__name__)

COREWRITER_ADDRESS = "0x3333333333333333333333333333333333333333"
MARK_PX_PRECOMPILE_ADDRESS = "0x0000000000000000000000000000000000000806"
BBO_PRECOMPILE_ADDRESS = "0x000000000000000000000000000000000000080e"
PERP_ASSET_INFO_PRECOMPILE_ADDRESS = "0x000000000000000000000000000000000000080a"
SPOT_INFO_PRECOMPILE_ADDRESS = "0x000000000000000000000000000000000000080b"
TOKEN_INFO_PRECOMPILE_ADDRESS = "0x000000000000000000000000000000000000080C"
CORE_USER_EXISTS_PRECOMPILE_ADDRESS = "0x0000000000000000000000000000000000000810"

DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_RECEIPT_TIMEOUT = 120.0

VerificationResolver = Callable[
    [str, Mapping[str, Any]], VerificationPayload | Mapping[str, Any] | None
]


class HLProtocolEVM(HLProtocolBase):
    """Interact with HyperLiquid via the HyperliquidStrategy contract."""

    def __init__(
        self,
        private_key: str,
        rpc_url: str,
        strategy_address: str,
        *,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        strategy_abi: list[dict[str, Any]] | None = None,
        verification_payload_url: str | None = None,
        verification_payload_resolver: VerificationResolver | None = None,
        wait_for_receipt: bool = True,
        receipt_timeout: float = DEFAULT_RECEIPT_TIMEOUT,
        testnet: bool = True,
    ) -> None:
        self.private_key = private_key
        self.rpc_url = rpc_url
        self.strategy_address = cast(ChecksumAddress, validate_address(strategy_address))
        self.corewriter_address = cast(ChecksumAddress, validate_address(COREWRITER_ADDRESS))

        self._strategy_abi = strategy_abi
        self._verification_payload_url = verification_payload_url
        self._verification_payload_resolver = verification_payload_resolver
        self._request_timeout = request_timeout
        self._wait_for_receipt = wait_for_receipt
        self._receipt_timeout = receipt_timeout
        self._testnet = testnet

        self._web3: Web3 | None = None
        self._account: LocalAccount | None = None
        self._strategy_contract: Contract | None = None
        self._chain_id: int | None = None
        self._connected = False
        self._subvault_address: ChecksumAddress | None = None

        self._asset_by_symbol: dict[str, int] = {}
        self._token_index_by_symbol: dict[str, int] = {}
        self._hype_token_index: int | None = None
        self._metadata_loaded = False
        self._perp_sz_decimals: dict[int, int] = {}
        self._spot_base_sz_decimals: dict[int, int] = {}

        self._info_url = (
            "https://api.hyperliquid-testnet.xyz/info"
            if self._testnet
            else "https://api.hyperliquid.xyz/info"
        )

    # ---------------------------------------------------------------------
    # Connection management
    # ---------------------------------------------------------------------
    def connect(self) -> None:
        """Establish a web3 connection and hydrate contract helpers."""

        try:
            provider = HTTPProvider(self.rpc_url, request_kwargs={"timeout": self._request_timeout})
            web3 = Web3(provider)
            if not web3.is_connected():
                raise NetworkError("Unable to connect to HyperLiquid RPC", endpoint=self.rpc_url)

            account = cast(LocalAccount, Account.from_key(self.private_key))  # type: ignore[arg-type]
            abi = self._fetch_strategy_abi()
            contract = web3.eth.contract(address=self.strategy_address, abi=abi)

            self._web3 = web3
            self._account = account
            self._strategy_contract = contract
            self._chain_id = web3.eth.chain_id
            self._subvault_address = None
            self._perp_sz_decimals.clear()
            self._spot_base_sz_decimals.clear()

            logger.info("Connected to HyperLiquid EVM at %s", self.rpc_url)

            try:
                self._hype_token_index = contract.functions.hypeTokenIndex().call()
            except Exception:
                self._hype_token_index = None

            self._subvault_address = self._load_and_validate_subvault()
            self._connected = True

        except ValidationError:
            self.disconnect()
            raise
        except NetworkError:
            self.disconnect()
            raise
        except Exception as exc:  # pragma: no cover - defensive
            self.disconnect()
            raise NetworkError(
                "Failed to initialize HyperLiquid EVM connection",
                endpoint=self.rpc_url,
                details={"error": str(exc)},
            ) from exc

    def disconnect(self) -> None:
        """Clear cached web3 state."""

        self._web3 = None
        self._account = None
        self._strategy_contract = None
        self._chain_id = None
        self._connected = False
        self._subvault_address = None
        self._perp_sz_decimals.clear()
        self._spot_base_sz_decimals.clear()

    def is_connected(self) -> bool:
        return self._connected and self._web3 is not None and self._strategy_contract is not None

    def _load_and_validate_subvault(self) -> ChecksumAddress:
        if self._strategy_contract is None:
            raise NetworkError(
                "Strategy contract unavailable while fetching subvault",
                endpoint=self.rpc_url,
            )

        try:
            raw_subvault = self._strategy_contract.functions.subvault().call()
        except Exception as exc:  # pragma: no cover - defensive
            raise ValidationError(
                "Unable to read strategy subvault address",
                field="subvault",
                details={"error": str(exc)},
            ) from exc

        try:
            normalized = Web3.to_checksum_address(raw_subvault)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValidationError(
                "Strategy contract returned an invalid subvault",
                field="subvault",
                value=raw_subvault,
                details={"error": str(exc)},
            ) from exc

        subvault = cast(ChecksumAddress, validate_address(normalized))
        if int(subvault, 16) == 0:
            raise ValidationError(
                "Strategy contract does not define a subvault address",
                field="subvault",
                value=subvault,
            )

        if not self._core_user_exists(subvault):
            raise ValidationError(
                "Strategy subvault is not registered on HyperLiquid core",
                field="subvault",
                value=subvault,
            )

        return subvault

    def _core_user_exists(self, address: ChecksumAddress) -> bool:
        (exists,) = self._call_l1_read_precompile(
            CORE_USER_EXISTS_PRECOMPILE_ADDRESS,
            ["address"],
            [address],
            ["bool"],
        )
        return bool(exists)

    # ------------------------------------------------------------------
    # Core actions
    # ------------------------------------------------------------------
    def get_market_price(self, asset: str) -> float:
        """Get the current market price for an asset.

        Returns:
            float: The mid-market price.

        Raises:
            ValueError: If the asset is invalid or price cannot be determined.
        """
        self._ensure_connected()

        try:
            mid_price, _, _ = self._market_price_context(asset)
            return float(mid_price)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    def market_order(
        self,
        asset: str,
        is_buy: bool,
        sz: float,
        slippage: float = 0.05,
        cloid: str | None = None,
    ) -> OrderResponse:
        try:
            mid_price, bid_price, ask_price = self._market_price_context(asset)
            limit_price = self._compute_slippage_price(asset, float(mid_price), is_buy, slippage)
        except (NetworkError, ValidationError) as exc:
            logger.error("Failed to compute market order price for %s: %s", asset, exc)
            return OrderResponse(success=False, cloid=cloid, error=str(exc))

        bid_str = f"{bid_price:.8f}" if bid_price is not None else "n/a"
        ask_str = f"{ask_price:.8f}" if ask_price is not None else "n/a"
        logger.info(
            "Market order BBO for %s: bid=%s ask=%s mid=%.8f",
            asset,
            bid_str,
            ask_str,
            float(mid_price),
        )
        direction = "buy" if is_buy else "sell"
        logger.info(
            "Market order limit for %s %s: slippage=%.4f -> %.8f",
            asset,
            direction,
            slippage,
            limit_price,
        )

        return self.limit_order(
            asset=asset,
            is_buy=is_buy,
            limit_px=limit_price,
            sz=sz,
            reduce_only=False,
            tif="IOC",
            cloid=cloid,
        )

    def market_close_position(
        self,
        asset: str,
        size: float | None = None,
        slippage: float = 0.05,
        cloid: str | None = None,
    ) -> OrderResponse:
        self._ensure_connected()

        try:
            position = self._fetch_user_position(asset)
        except NetworkError as exc:
            logger.error("Failed to fetch position state for %s: %s", asset, exc)
            return OrderResponse(success=False, cloid=cloid, error=str(exc))

        if position is None:
            message = f"No open position found for asset {asset}"
            logger.info(message)
            return OrderResponse(success=False, cloid=cloid, error=message)

        szi_raw = position.get("szi")
        try:
            position_size = float(szi_raw) if szi_raw is not None else 0.0
        except (TypeError, ValueError) as exc:
            error = ValidationError(
                "Unable to parse current position size",
                field="szi",
                value=position.get("szi"),
            )
            logger.error("Failed to parse position size for %s: %s", asset, exc)
            return OrderResponse(success=False, cloid=cloid, error=str(error))

        if position_size == 0:
            message = f"No open position found for asset {asset}"
            logger.info(message)
            return OrderResponse(success=False, cloid=cloid, error=message)

        is_buy = position_size < 0

        if size is None:
            target_size = abs(position_size)
        else:
            try:
                target_size = float(size)
            except (TypeError, ValueError):
                error = ValidationError("Close size must be numeric", field="size", value=size)
                return OrderResponse(success=False, cloid=cloid, error=str(error))

        if target_size <= 0:
            error = ValidationError("Close size must be positive", field="size", value=target_size)
            return OrderResponse(success=False, cloid=cloid, error=str(error))

        try:
            mid_price = self.get_market_price(asset)
            limit_price = self._compute_slippage_price(asset, mid_price, is_buy, slippage)
        except (NetworkError, ValidationError) as exc:
            logger.error("Failed to compute close order price for %s: %s", asset, exc)
            return OrderResponse(success=False, cloid=cloid, error=str(exc))

        return self.limit_order(
            asset=asset,
            is_buy=is_buy,
            limit_px=limit_price,
            sz=target_size,
            reduce_only=True,
            tif="IOC",
            cloid=cloid,
        )

    def limit_order(
        self,
        asset: str,
        is_buy: bool,
        limit_px: float,
        sz: float,
        reduce_only: bool = False,
        tif: str = "GTC",
        cloid: str | None = None,
    ) -> OrderResponse:
        try:
            self._ensure_connected()
            asset_id = self._resolve_asset_id(asset)
            formatted_price = self._format_limit_price(asset_id, limit_px)
            price_uint = price_to_uint64(formatted_price)
            size_uint = size_to_uint64(sz)
            tif_uint = encode_tif(tif)
            cloid_uint = cloid_to_uint128(cloid)

            context = {
                "asset": asset_id,
                "is_buy": is_buy,
                "tif": tif_uint,
                "cloid": cloid_uint,
            }
            payload = self._resolve_verification_payload("limit_order", context)
            fn_name = "placeLimitBuyOrder" if is_buy else "placeLimitSellOrder"
            args: Sequence[Any] = [
                asset_id,
                price_uint,
                size_uint,
                reduce_only,
                tif_uint,
                cloid_uint,
                payload.as_tuple(),
            ]
            tx_result = self._send_contract_transaction(
                fn_name, args, action="limit_order", context=context
            )
            receipt = tx_result.get("receipt")
            status = bool(receipt is None or receipt.get("status", 0) == 1)
            error_text = None if status else "Transaction reverted"
            return OrderResponse(
                success=status,
                order_id=None,
                cloid=cloid,
                transaction_hash=tx_result["tx_hash"],
                error=error_text,
                raw_response=tx_result,
            )
        except ValidationError as exc:
            logger.error("Limit order validation failed: %s", exc)
            return OrderResponse(success=False, cloid=cloid, error=str(exc))
        except NetworkError as exc:
            logger.error("Limit order failed: %s", exc)
            return OrderResponse(
                success=False,
                cloid=cloid,
                error=str(exc),
                raw_response=getattr(exc, "details", None),
            )
        except Exception as exc:  # pragma: no cover - operational safety
            logger.exception("Unexpected limit order failure")
            return OrderResponse(success=False, cloid=cloid, error=str(exc))

    def cancel_order_by_oid(self, asset: str, order_id: int) -> CancelResponse:
        try:
            self._ensure_connected()
            asset_id = self._resolve_asset_id(asset)
            oid = int(order_id)
            context = {"asset": asset_id, "oid": oid}
            payload = self._resolve_verification_payload("cancel_order_by_oid", context)
            args: Sequence[Any] = [asset_id, oid, payload.as_tuple()]
            tx_result = self._send_contract_transaction(
                "cancelOrderByOid", args, action="cancel_order_by_oid", context=context
            )
            receipt = tx_result.get("receipt")
            status = bool(receipt is None or receipt.get("status", 0) == 1)
            error_text = None if status else "Transaction reverted"
            return CancelResponse(
                success=status,
                cancelled_orders=1 if status else 0,
                transaction_hash=tx_result["tx_hash"],
                error=error_text,
                raw_response=tx_result,
            )
        except ValidationError as exc:
            return CancelResponse(success=False, error=str(exc))
        except NetworkError as exc:
            return CancelResponse(
                success=False,
                error=str(exc),
                raw_response=getattr(exc, "details", None),
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected cancel-by-oid failure")
            return CancelResponse(success=False, error=str(exc))

    def cancel_order_by_cloid(self, asset: str, cloid: str) -> CancelResponse:
        try:
            self._ensure_connected()
            asset_id = self._resolve_asset_id(asset)
            cloid_uint = cloid_to_uint128(cloid)
            context = {"asset": asset_id, "cloid": cloid_uint}
            payload = self._resolve_verification_payload("cancel_order_by_cloid", context)
            args: Sequence[Any] = [asset_id, cloid_uint, payload.as_tuple()]
            tx_result = self._send_contract_transaction(
                "cancelOrderByCloid", args, action="cancel_order_by_cloid", context=context
            )
            receipt = tx_result.get("receipt")
            status = bool(receipt is None or receipt.get("status", 0) == 1)
            error_text = None if status else "Transaction reverted"
            return CancelResponse(
                success=status,
                cancelled_orders=1 if status else 0,
                transaction_hash=tx_result["tx_hash"],
                error=error_text,
                raw_response=tx_result,
            )
        except ValidationError as exc:
            return CancelResponse(success=False, error=str(exc))
        except NetworkError as exc:
            return CancelResponse(
                success=False,
                error=str(exc),
                raw_response=getattr(exc, "details", None),
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected cancel-by-cloid failure")
            return CancelResponse(success=False, error=str(exc))

    def vault_transfer(self, vault: str, is_deposit: bool, usd: float) -> TransferResponse:
        message = (
            "Vault transfers are not available via the HyperliquidStrategy contract; "
            "use usd_class_transfer_to_perp/spot instead"
        )
        logger.warning("vault_transfer not supported for vault %s", vault)
        return TransferResponse(success=False, amount=None, error=message)

    def token_delegate(
        self, validator: str, amount: float, is_undelegate: bool = False
    ) -> DelegateResponse:
        message = "Token delegation is not routed through the current strategy"
        return DelegateResponse(success=False, validator=validator, amount=None, error=message)

    def staking_deposit(self, amount: float) -> StakingResponse:
        message = "Staking deposit is not supported by the HyperliquidStrategy contract"
        return StakingResponse(success=False, amount=None, error=message)

    def staking_withdraw(self, amount: float) -> StakingResponse:
        message = "Staking withdrawal is not supported by the HyperliquidStrategy contract"
        return StakingResponse(success=False, amount=None, error=message)

    def spot_send(
        self, recipient: str, token: str, amount: float, destination: str
    ) -> SendResponse:
        try:
            self._ensure_connected()
            amount_uint = size_to_uint64(amount)
            context = {"token": token, "amount": amount_uint, "recipient": recipient}
            payload = self._resolve_verification_payload("spot_send", context)

            if self._is_hype_token(token):
                args: Sequence[Any] = [amount_uint, payload.as_tuple()]
                fn_name = "withdrawHypeToEvm"
            else:
                token_index = self._resolve_token_index(token)
                args = [token_index, amount_uint, payload.as_tuple()]
                fn_name = "withdrawTokenToEvm"

            tx_result = self._send_contract_transaction(
                fn_name, args, action="spot_send", context=context
            )
            receipt = tx_result.get("receipt")
            status = bool(receipt is None or receipt.get("status", 0) == 1)
            error_text = None if status else "Transaction reverted"
            return SendResponse(
                success=status,
                recipient=recipient,
                amount=amount if status else None,
                transaction_hash=tx_result["tx_hash"],
                error=error_text,
                raw_response=tx_result,
            )
        except ValidationError as exc:
            return SendResponse(success=False, recipient=recipient, error=str(exc))
        except NetworkError as exc:
            return SendResponse(success=False, recipient=recipient, error=str(exc))
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected spot_send failure")
            return SendResponse(success=False, recipient=recipient, error=str(exc))

    def perp_send(self, recipient: str, amount: float, destination: str) -> SendResponse:
        message = "Perp collateral send is not exposed by the HyperliquidStrategy contract"
        return SendResponse(success=False, recipient=recipient, amount=None, error=message)

    def usd_class_transfer_to_perp(self, amount: float) -> TransferResponse:
        try:
            self._ensure_connected()
            amount_uint = size_to_uint64(amount)
            context = {"amount": amount_uint}
            payload = self._resolve_verification_payload("usd_class_transfer_to_perp", context)
            args: Sequence[Any] = [amount_uint, payload.as_tuple()]
            tx_result = self._send_contract_transaction(
                "transferSpotToPerp", args, action="usd_class_transfer_to_perp", context=context
            )
            receipt = tx_result.get("receipt")
            status = bool(receipt is None or receipt.get("status", 0) == 1)
            error_text = None if status else "Transaction reverted"
            return TransferResponse(
                success=status,
                amount=amount if status else None,
                transaction_hash=tx_result["tx_hash"],
                error=error_text,
                raw_response=tx_result,
            )
        except ValidationError as exc:
            return TransferResponse(success=False, error=str(exc))
        except NetworkError as exc:
            return TransferResponse(
                success=False,
                error=str(exc),
                raw_response=getattr(exc, "details", None),
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected transferSpotToPerp failure")
            return TransferResponse(success=False, error=str(exc))

    def usd_class_transfer_to_spot(self, amount: float) -> TransferResponse:
        try:
            self._ensure_connected()
            amount_uint = size_to_uint64(amount)
            context = {"amount": amount_uint}
            payload = self._resolve_verification_payload("usd_class_transfer_to_spot", context)
            args: Sequence[Any] = [amount_uint, payload.as_tuple()]
            tx_result = self._send_contract_transaction(
                "transferPerpToSpot", args, action="usd_class_transfer_to_spot", context=context
            )
            receipt = tx_result.get("receipt")
            status = bool(receipt is None or receipt.get("status", 0) == 1)
            error_text = None if status else "Transaction reverted"
            return TransferResponse(
                success=status,
                amount=amount if status else None,
                transaction_hash=tx_result["tx_hash"],
                error=error_text,
                raw_response=tx_result,
            )
        except ValidationError as exc:
            return TransferResponse(success=False, error=str(exc))
        except NetworkError as exc:
            return TransferResponse(
                success=False,
                error=str(exc),
                raw_response=getattr(exc, "details", None),
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected transferPerpToSpot failure")
            return TransferResponse(success=False, error=str(exc))

    def finalize_subaccount(self, subaccount: str) -> FinalizeResponse:
        message = "Subaccount finalization must be executed via CoreWriter directly"
        return FinalizeResponse(success=False, subaccount=subaccount, error=message)

    def approve_builder_fee(self, builder: str, fee: float, nonce: int) -> ApprovalResponse:
        message = "Builder fee approvals are not implemented on the strategy contract"
        return ApprovalResponse(success=False, builder=builder, fee=fee, nonce=nonce, error=message)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _ensure_connected(self) -> None:
        if (
            not self.is_connected()
            or self._web3 is None
            or self._account is None
            or self._strategy_contract is None
        ):
            raise NetworkError("EVM connector is not connected", endpoint=self.rpc_url)

    def _call_l1_read_precompile(
        self,
        address: str,
        input_types: Sequence[str],
        args: Sequence[Any],
        output_types: Sequence[str],
    ) -> tuple[Any, ...]:
        assert self._web3 is not None

        call_data = abi_encode(list(input_types), list(args)) if input_types else b""
        destination = Web3.to_checksum_address(address)

        try:
            result = self._web3.eth.call({"to": destination, "data": call_data})
        except Exception as exc:  # pragma: no cover - defensive
            raise NetworkError(
                "Failed to execute L1 read precompile",
                endpoint=str(destination),
                details={"error": str(exc)},
            ) from exc

        if not output_types:
            return tuple()

        try:
            decoded = abi_decode(list(output_types), result)
        except Exception as exc:  # pragma: no cover - defensive
            raise NetworkError(
                "Failed to decode L1 read precompile response",
                endpoint=str(destination),
                details={"error": str(exc)},
            ) from exc

        return tuple(decoded)

    # best bid and offer
    def _fetch_bbo_prices(self, asset_id: int) -> tuple[int, int]:
        bid_uint, ask_uint = self._call_l1_read_precompile(
            BBO_PRECOMPILE_ADDRESS,
            ["uint32"],
            [asset_id],
            ["uint64", "uint64"],
        )
        return int(bid_uint), int(ask_uint)

    def _read_mark_price(self, asset_id: int) -> int:
        (mark_uint,) = self._call_l1_read_precompile(
            MARK_PX_PRECOMPILE_ADDRESS,
            ["uint32"],
            [asset_id],
            ["uint64"],
        )
        return int(mark_uint)

    def _compute_slippage_price(
        self, asset: str, mid_price: float, is_buy: bool, slippage: float
    ) -> float:
        if mid_price <= 0:
            raise ValidationError("Mid price must be positive", field="mid_price", value=mid_price)

        slip = Decimal(str(slippage))
        if slip < 0:
            raise ValidationError("Slippage must be non-negative", field="slippage", value=slippage)
        if slip >= 1:
            raise ValidationError(
                "Slippage must be less than 1 (100%)",
                field="slippage",
                value=slippage,
            )

        base = Decimal(str(mid_price))
        multiplier = Decimal(1) + slip if is_buy else Decimal(1) - slip

        if multiplier <= 0:
            raise ValidationError(
                "Slippage too large for sell order",
                field="slippage",
                value=slippage,
            )

        raw_price = float(base * multiplier)

        asset_id = self._resolve_asset_id(asset)
        sz_decimals = self._resolve_perp_sz_decimals(asset_id)

        if sz_decimals is None:
            logger.error(f"Could not fetch sz_decimals for asset {asset}, using default 3")
            raise ValidationError(
                "Could not resolve asset metadata",
                field="asset",
                value=asset,
            )

        return format_price_for_api(raw_price, sz_decimals, is_perp=True)

    def _format_limit_price(self, asset_id: int, limit_px: float | Decimal) -> float | Decimal:
        """Format a limit price using asset metadata when available."""

        sz_decimals = self._resolve_perp_sz_decimals(asset_id)
        if sz_decimals is not None:
            return format_price_for_api(limit_px, sz_decimals, is_perp=True)

        base_sz_decimals = self._resolve_spot_base_sz_decimals(asset_id)
        if base_sz_decimals is not None:
            return format_price_for_api(limit_px, base_sz_decimals, is_perp=False)

        logger.debug(
            "Falling back to raw limit price for asset %s because size decimals could not be resolved",
            asset_id,
        )
        return limit_px

    def _market_price_context(self, asset: str) -> tuple[Decimal, Decimal | None, Decimal | None]:
        """Get market price context with bid, ask, and mid prices.

        Returns:
            Tuple of (mid_price, bid_price, ask_price) as Decimal values.
            bid_price and ask_price may be None if unavailable.

        Raises:
            NetworkError: If no prices can be determined.
        """
        asset_id = self._resolve_asset_id(asset)

        try:
            bid_uint, ask_uint = self._fetch_bbo_prices(asset_id)
        except NetworkError as exc:
            logger.warning("BBO precompile unavailable for %s (asset %s): %s", asset, asset_id, exc)
            bid_uint, ask_uint = 0, 0

        if bid_uint and ask_uint:
            mid_uint = (bid_uint + ask_uint) // 2
        elif bid_uint or ask_uint:
            mid_uint = bid_uint or ask_uint

        mid_price, bid_price, ask_price = self._convert_market_prices(
            asset_id, mid_uint, bid_uint, ask_uint
        )

        if mid_price is None or mid_price == Decimal(0):
            raise NetworkError(
                "Failed to convert market price to valid Decimal",
                details={"asset": asset, "asset_id": asset_id, "mid_uint": mid_uint},
            )
        logger.info(
            f"Market price for {asset} (id {asset_id}): mid={mid_price}, bid={bid_price}, ask={ask_price}"
        )
        return mid_price, bid_price, ask_price

    def _convert_market_prices(
        self, asset_id: int, mid_uint: int, bid_uint: int, ask_uint: int
    ) -> tuple[Decimal, Decimal | None, Decimal | None]:
        """Convert uint prices to Decimal based on asset type."""

        sz_decimals = self._resolve_perp_sz_decimals(asset_id)
        logger.info(f"Perp size decimals for asset {asset_id}: {sz_decimals}")

        if sz_decimals is not None:
            return (
                self._convert_perp_price(mid_uint, sz_decimals),
                self._convert_perp_price(bid_uint, sz_decimals) if bid_uint else None,
                self._convert_perp_price(ask_uint, sz_decimals) if ask_uint else None,
            )

        # Try spot conversion
        base_sz_decimals = self._resolve_spot_base_sz_decimals(asset_id)
        if base_sz_decimals is not None:
            return (
                self._convert_spot_price(mid_uint, base_sz_decimals),
                self._convert_spot_price(bid_uint, base_sz_decimals) if bid_uint else None,
                self._convert_spot_price(ask_uint, base_sz_decimals) if ask_uint else None,
            )

        # Fallback to default conversion
        return (
            uint64_to_price(mid_uint),
            uint64_to_price(bid_uint) if bid_uint else None,
            uint64_to_price(ask_uint) if ask_uint else None,
        )

    def _convert_perp_price(self, price_uint: int, sz_decimals: int) -> Decimal:
        exponent = 6 - int(sz_decimals)

        if exponent <= 0:
            raise ValueError("Size decimals too large for perp price conversion")

        return Decimal(price_uint) / (Decimal(10) ** exponent)

    def _resolve_perp_sz_decimals(self, asset_id: int) -> int | None:
        if asset_id in self._perp_sz_decimals:
            return self._perp_sz_decimals[asset_id]

        try:
            logger.debug(f"Calling perpAssetInfo precompile for asset {asset_id}")
            result = self._call_l1_read_precompile(
                PERP_ASSET_INFO_PRECOMPILE_ADDRESS,
                ["uint32"],
                [asset_id],
                ["(string,uint32,uint8,uint8,bool)"],  # Returns a tuple
            )
            # Unpack the tuple - result is ((name, index, sz_decimals, wei_decimals, is_enabled),)
            if result and len(result) > 0:
                result = result[0]  # Extract the inner tuple
            logger.debug(f"perpAssetInfo result for asset {asset_id}: {result}")
        except NetworkError as exc:
            logger.warning(f"perpAssetInfo NetworkError for asset {asset_id}: {exc}")
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"perpAssetInfo call failed for asset {asset_id}: {exc}")
            return None

        if not result:
            logger.error(f"Empty perp asset info for asset {asset_id}")
            return None

        logger.info(f"Perp asset info for asset {asset_id}: {result}")

        try:
            sz_decimals = int(result[2])
        except (TypeError, ValueError, IndexError):
            return None
        logger.info(f"Resolved perp size decimals for asset {asset_id}: {sz_decimals}")
        self._perp_sz_decimals[asset_id] = sz_decimals
        return sz_decimals

    def _convert_spot_price(self, price_uint: int, base_sz_decimals: int) -> Decimal:
        exponent = 8 - int(base_sz_decimals)
        if exponent >= 0:
            return Decimal(price_uint) / (Decimal(10) ** exponent)
        return Decimal(price_uint) * (Decimal(10) ** (-exponent))

    def _resolve_spot_base_sz_decimals(self, asset_id: int) -> int | None:
        if asset_id in self._spot_base_sz_decimals:
            return self._spot_base_sz_decimals[asset_id]

        try:
            spot_info = self._call_l1_read_precompile(
                SPOT_INFO_PRECOMPILE_ADDRESS,
                ["uint32"],
                [asset_id],
                ["(string,uint64[2])"],  # Returns a tuple
            )
            # Unpack the tuple if needed
            if spot_info and len(spot_info) > 0:
                spot_info = spot_info[0]  # Extract the inner tuple
        except NetworkError:
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("spotInfo call failed for %s: %s", asset_id, exc)
            return None

        if not spot_info:
            return None

        try:
            tokens = spot_info[1]
        except (IndexError, TypeError):
            return None

        if not tokens:
            return None

        base_token_id = int(tokens[0])

        try:
            token_info = self._call_l1_read_precompile(
                TOKEN_INFO_PRECOMPILE_ADDRESS,
                ["uint32"],
                [base_token_id],
                [
                    "string",
                    "uint64[]",
                    "uint64",
                    "address",
                    "address",
                    "uint8",
                    "uint8",
                    "int8",
                ],
            )
        except NetworkError:
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("tokenInfo call failed for token %s: %s", base_token_id, exc)
            return None

        if not token_info:
            return None

        try:
            sz_decimals = int(token_info[5])
        except (IndexError, TypeError, ValueError):
            return None

        self._spot_base_sz_decimals[asset_id] = sz_decimals
        return sz_decimals

    def _resolve_trader_address(self) -> str:
        if self._subvault_address is not None:
            return self._subvault_address

        if self._strategy_contract is not None:
            try:
                self._subvault_address = self._load_and_validate_subvault()
                return self._subvault_address
            except ValidationError as exc:
                raise NetworkError(str(exc), endpoint=self.rpc_url, details=exc.details) from exc
            except NetworkError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                raise NetworkError(
                    "Unexpected failure resolving strategy subvault",
                    endpoint=self.rpc_url,
                    details={"error": str(exc)},
                ) from exc

        if self._account is not None:
            return self._account.address

        raise NetworkError("Trading account address unavailable", endpoint=self.rpc_url)

    def _fetch_user_position(self, asset: str) -> Mapping[str, Any] | None:
        trader_address = self._resolve_trader_address()

        payload = {"type": "clearinghouseState", "user": trader_address}
        state = self._post_json(self._info_url, payload)

        if not isinstance(state, Mapping):
            raise NetworkError(
                "Unexpected response format when fetching user state",
                endpoint=self._info_url,
                details={"response": state},
            )

        positions = state.get("assetPositions")
        if not isinstance(positions, Sequence):
            return None

        target_symbol = str(asset).upper()
        for entry in positions:
            if not isinstance(entry, Mapping):
                continue
            position = entry.get("position")
            if not isinstance(position, Mapping):
                continue
            coin = position.get("coin")
            if isinstance(coin, str) and coin.upper() == target_symbol:
                return position

        return None

    def _fetch_strategy_abi(self) -> list[dict[str, Any]]:
        if self._strategy_abi is not None:
            return self._strategy_abi

        self._strategy_abi = HyperliquidStrategy_abi
        return self._strategy_abi

    def load_asset_metadata_from_url(self, url: str) -> None:
        """Fetch asset metadata JSON from a URL and register symbol mappings."""

        payload = self._fetch_json(url)
        self._ingest_asset_metadata(payload)
        if not self._asset_by_symbol and not self._token_index_by_symbol:
            logger.warning("Asset metadata from %s did not produce any symbol mappings", url)
        self._metadata_loaded = True

    def load_asset_metadata_from_info(self) -> None:
        """Fetch asset metadata directly from the HyperLiquid info endpoint."""

        payload = self._post_json(self._info_url, {"type": "meta"})
        universe = payload.get("universe") if isinstance(payload, Mapping) else None
        if isinstance(universe, Sequence):
            for asset_id, entry in enumerate(universe):
                if not isinstance(entry, Mapping):
                    continue
                symbol = entry.get("name")
                if symbol:
                    self._asset_by_symbol[str(symbol).upper()] = asset_id
        else:
            logger.warning("Meta response missing 'universe' array")

        self._metadata_loaded = True
        if not self._asset_by_symbol:
            logger.warning("Meta info call did not produce any symbol mappings")

    def register_asset_metadata(self, payload: Any) -> None:
        """Register asset metadata from a provided object (dict/list/etc)."""

        self._ingest_asset_metadata(payload)
        if not self._asset_by_symbol and not self._token_index_by_symbol:
            logger.warning("Asset metadata payload did not produce any symbol mappings")
        self._metadata_loaded = True

    def _ingest_asset_metadata(self, payload: Any) -> None:
        if isinstance(payload, Mapping):
            for key in ("assets", "perpetuals", "symbols"):
                if key in payload:
                    self._register_asset_entries(payload[key])
            for key in ("tokenIndices", "token_indices", "tokens"):
                if key in payload:
                    self._register_token_entries(payload[key])
            if not self._asset_by_symbol and not self._token_index_by_symbol:
                self._register_asset_entries(payload)
            return

        if isinstance(payload, Sequence) and not isinstance(payload, str | bytes | bytearray):
            self._register_asset_entries(payload)
            return

        logger.debug("Skipping unrecognised metadata payload type %s", type(payload).__name__)

    def _register_asset_entries(self, entries: Any) -> None:
        if isinstance(entries, Mapping):
            for symbol, value in entries.items():
                asset_id = self._coerce_int(value)
                if asset_id is not None:
                    self._asset_by_symbol[str(symbol).upper()] = asset_id
            return

        if isinstance(entries, Sequence):
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                symbol = (
                    entry.get("symbol")
                    or entry.get("name")
                    or entry.get("asset")
                    or entry.get("ticker")
                )
                if not symbol:
                    continue
                asset_id_val = (
                    entry.get("id")
                    or entry.get("assetId")
                    or entry.get("asset_id")
                    or entry.get("index")
                )
                asset_id = self._coerce_int(asset_id_val)
                if asset_id is not None:
                    self._asset_by_symbol[str(symbol).upper()] = asset_id

    def _register_token_entries(self, entries: Any) -> None:
        if isinstance(entries, Mapping):
            for symbol, value in entries.items():
                index = self._coerce_int(value)
                if index is not None:
                    self._token_index_by_symbol[str(symbol).upper()] = index
            return

        if isinstance(entries, Sequence):
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                symbol = (
                    entry.get("symbol")
                    or entry.get("name")
                    or entry.get("token")
                    or entry.get("ticker")
                )
                if not symbol:
                    continue
                index_val = entry.get("index") or entry.get("tokenIndex") or entry.get("id")
                index = self._coerce_int(index_val)
                if index is not None:
                    self._token_index_by_symbol[str(symbol).upper()] = index

    def _resolve_asset_id(self, asset: str) -> int:
        try:
            return int(asset, 0)
        except (TypeError, ValueError):
            symbol = str(asset).upper()
            if symbol in self._asset_by_symbol:
                return self._asset_by_symbol[symbol]
            if not self._metadata_loaded:
                try:
                    self.load_asset_metadata_from_info()
                except NetworkError as exc:
                    logger.warning("Failed to load asset metadata from info endpoint: %s", exc)
                if symbol in self._asset_by_symbol:
                    return self._asset_by_symbol[symbol]
            raise ValidationError(
                f"Unknown asset symbol '{asset}'",
                field="asset",
                value=asset,
            )

    def _resolve_token_index(self, token: str | int) -> int:
        if isinstance(token, int):
            return token
        try:
            return int(token, 0)
        except (TypeError, ValueError):
            symbol = str(token).upper()
            if symbol in self._token_index_by_symbol:
                return self._token_index_by_symbol[symbol]
            raise ValidationError(
                f"Unknown token identifier '{token}'",
                field="token",
                value=token,
            )

    def _resolve_verification_payload(
        self, action: str, context: Mapping[str, Any]
    ) -> VerificationPayload:
        if self._verification_payload_resolver:
            result = self._verification_payload_resolver(action, context)
            if isinstance(result, VerificationPayload):
                return result
            mapped = dict(result) if isinstance(result, Mapping) else None
            return VerificationPayload.from_dict(mapped)

        if self._verification_payload_url:
            url = self._build_verification_url(action, context)
            data = self._fetch_json(url)
            mapped = dict(data) if isinstance(data, Mapping) else None
            return VerificationPayload.from_dict(mapped)

        return VerificationPayload.default()

    def _build_verification_url(self, action: str, context: Mapping[str, Any]) -> str:
        url = self._verification_payload_url or ""
        if "{action}" in url:
            url = url.format(action=action)

        query_params = {
            key: value
            for key, value in context.items()
            if isinstance(value, str | int | float | bool)
        }
        if not query_params:
            return url

        encoded = urlparse.urlencode({k: str(v) for k, v in query_params.items()})
        parsed = urlparse.urlparse(url)
        separator = "&" if parsed.query else "?"
        return f"{url}{separator}{encoded}"

    def _is_hype_token(self, token: str | int) -> bool:
        if isinstance(token, str) and token.upper() == "HYPE":
            return True
        if self._hype_token_index is None:
            return False
        try:
            candidate = int(token, 0) if isinstance(token, str) else int(token)
            return candidate == self._hype_token_index
        except (TypeError, ValueError):
            return False

    def _coerce_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            if isinstance(value, str):
                value = value.strip()
            return int(value, 0) if isinstance(value, str) else int(value)
        except (TypeError, ValueError):
            logger.debug("Failed to coerce value '%s' to int", value)
            return None

    def _fetch_json(self, url: str | None) -> Any:
        if not url:
            raise NetworkError("No URL provided for JSON fetch")

        request = urlrequest.Request(url, headers={"User-Agent": "hl-api/evm"})
        try:
            with urlrequest.urlopen(request, timeout=self._request_timeout) as response:
                body = response.read()
        except urlerror.HTTPError as exc:
            raise NetworkError(
                f"HTTP error {exc.code} while fetching {url}",
                endpoint=url,
                status_code=exc.code,
            ) from exc
        except urlerror.URLError as exc:
            raise NetworkError(f"Failed to fetch {url}: {exc.reason}", endpoint=url) from exc

        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NetworkError("Response was not valid UTF-8", endpoint=url) from exc

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise NetworkError(
                "Failed to decode JSON response", endpoint=url, details={"error": str(exc)}
            ) from exc

    def _post_json(self, url: str, payload: Mapping[str, Any]) -> Any:
        data = json.dumps(payload).encode("utf-8")
        request = urlrequest.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "hl-api/evm"},
            method="POST",
        )
        try:
            with urlrequest.urlopen(request, timeout=self._request_timeout) as response:
                body = response.read()
        except urlerror.HTTPError as exc:
            raise NetworkError(
                f"HTTP error {exc.code} while posting to {url}",
                endpoint=url,
                status_code=exc.code,
            ) from exc
        except urlerror.URLError as exc:
            raise NetworkError(f"Failed to post to {url}: {exc.reason}", endpoint=url) from exc

        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NetworkError("Response was not valid UTF-8", endpoint=url) from exc

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise NetworkError(
                "Failed to decode JSON response", endpoint=url, details={"error": str(exc)}
            ) from exc

    def _send_contract_transaction(
        self,
        function_name: str,
        args: Sequence[Any],
        *,
        action: str,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        assert self._web3 is not None
        assert self._account is not None
        assert self._strategy_contract is not None

        function = getattr(self._strategy_contract.functions, function_name)(*args)
        formatted_args = []
        for i, arg in enumerate(args):
            if function_name in ["placeLimitBuyOrder", "placeLimitSellOrder"]:
                if i == 1:  # Price parameter
                    formatted_args.append(f"{arg} ({arg / 10**8:.8f})")
                elif i == 2:  # Size parameter
                    formatted_args.append(f"{arg} ({arg / 10**8:.8f})")
                else:
                    formatted_args.append(self._summarise_param(arg))
            else:
                formatted_args.append(self._summarise_param(arg))

        formatted_context = {k: self._summarise_param(v) for k, v in context.items()}
        logger.info(
            "Calling strategy %s.%s with args=%s context=%s",
            self.strategy_address,
            function_name,
            formatted_args,
            formatted_context,
        )
        try:
            base_tx = function.build_transaction(
                {
                    "from": self._account.address,
                    "nonce": self._web3.eth.get_transaction_count(self._account.address),
                }
            )

            mutable_tx: dict[str, Any] = dict(base_tx)
            mutable_tx.setdefault("chainId", self._chain_id or self._web3.eth.chain_id)

            gas_price = mutable_tx.pop("gasPrice", None)
            need_dynamic_fees = (
                "maxFeePerGas" not in mutable_tx or "maxPriorityFeePerGas" not in mutable_tx
            )
            if need_dynamic_fees:
                fetched_priority_fee: int | None = None
                try:
                    fetched_priority_fee = int(self._web3.eth.max_priority_fee)  # type: ignore[attr-defined]
                except (AttributeError, ValueError, TypeError):
                    fetched_priority_fee = None

                reference_fee = gas_price if gas_price is not None else self._web3.eth.gas_price
                priority_fee = (
                    fetched_priority_fee
                    if fetched_priority_fee is not None
                    else max(reference_fee // 10, 1)
                )

                max_fee = max(reference_fee, priority_fee * 2)

                mutable_tx.setdefault("maxPriorityFeePerGas", priority_fee)
                mutable_tx.setdefault("maxFeePerGas", max_fee)

            tx_params = cast(TxParams, mutable_tx)
            if "gas" not in mutable_tx:
                gas_estimate = self._web3.eth.estimate_gas(tx_params)
                mutable_tx["gas"] = gas_estimate
                tx_params = cast(TxParams, mutable_tx)

            tx_for_sign: dict[str, Any] = {key: value for key, value in tx_params.items()}
            signed = self._account.sign_transaction(tx_for_sign)
            tx_hash = self._web3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info("Submitted %s transaction %s", action, tx_hash.hex())
            receipt = None
            block_number: Any | None = None
            status_value: Any | None = None
            if self._wait_for_receipt:
                receipt = self._web3.eth.wait_for_transaction_receipt(
                    tx_hash, timeout=self._receipt_timeout
                )
                block_number = getattr(receipt, "blockNumber", None)
                status_value = getattr(receipt, "status", None)
                if block_number is None and isinstance(receipt, Mapping):
                    block_number = receipt.get("blockNumber")
                if status_value is None and isinstance(receipt, Mapping):
                    status_value = receipt.get("status")
                logger.info(
                    "Transaction %s included in block %s with status %s",
                    tx_hash.hex(),
                    block_number,
                    status_value,
                )

            result = {
                "tx_hash": tx_hash.hex(),
                "action": action,
                "context": dict(context),
                "receipt": self._serialise_receipt(receipt) if receipt is not None else None,
                "block_number": block_number if receipt else None,
            }
            return result
        except ContractLogicError as exc:
            raise NetworkError(
                f"Strategy contract reverted during {action}",
                details={"error": str(exc)},
            ) from exc
        except ValueError as exc:
            message = str(exc)
            if exc.args and isinstance(exc.args[0], Mapping):
                message = str(exc.args[0].get("message", message))
            raise NetworkError(
                f"Failed to submit transaction for {action}: {message}",
                details={"error": message},
            ) from exc
        except Exception as exc:  # pragma: no cover
            raise NetworkError(
                f"Unexpected error submitting transaction for {action}",
                details={"error": str(exc)},
            ) from exc

    def _serialise_receipt(self, receipt: Any) -> Any:
        if receipt is None:
            return None
        if isinstance(receipt, Mapping):
            return {key: self._serialise_receipt(value) for key, value in receipt.items()}
        if isinstance(receipt, Sequence) and not isinstance(
            receipt, str | bytes | bytearray | HexBytes
        ):
            return [self._serialise_receipt(item) for item in receipt]
        if isinstance(receipt, bytes | bytearray | HexBytes):
            return HexBytes(receipt).hex()
        return receipt

    def _summarise_param(self, value: Any) -> Any:
        if isinstance(value, bytes | bytearray | HexBytes):
            hexstr = HexBytes(value).hex()
            if len(hexstr) > 70:
                return f"bytes[{len(value)}]={hexstr[:70]}..."
            return f"bytes[{len(value)}]={hexstr}"
        if isinstance(value, list | tuple | set):
            return [self._summarise_param(v) for v in value]
        if isinstance(value, Mapping):
            return {k: self._summarise_param(v) for k, v in value.items()}
        return value
