"""HyperLiquid EVM implementation that routes actions through a strategy contract."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from functools import lru_cache
from typing import Any, cast

import requests
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import HTTPProvider, Web3
from web3.contract import Contract
from web3.middleware import SignAndSendRawMiddlewareBuilder
from web3.types import ChecksumAddress

from .abi import HyperliquidBridgeStrategy_abi, HyperliquidStrategy_abi
from .base import HLProtocolBase
from .constants import Precompile
from .evm_utils import (
    build_verification_url,
    convert_perp_price,
    convert_spot_price,
    serialise_receipt,
    transaction_method,
)
from .exceptions import NetworkError, ValidationError
from .types import (
    ApprovalResponse,
    BridgeResponse,
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

DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_RECEIPT_TIMEOUT = 120.0
DEFAULT_IRIS_POLL_INTERVAL = 2.0
DEFAULT_IRIS_MAX_POLLS = 600
DEFAULT_CCTP_FINALITY_THRESHOLD = 1000
USDC_SCALING = Decimal("1000000")
IRIS_API_PROD = "https://iris-api.circle.com"
IRIS_API_SANDBOX = "https://iris-api-sandbox.circle.com"

VerificationResolver = Callable[
    [str, Mapping[str, Any]], VerificationPayload | Mapping[str, Any] | None
]


class HLProtocolEVM(HLProtocolBase):
    """Interact with HyperLiquid via the HyperliquidStrategy contract."""

    def __init__(
        self,
        private_key: str,
        hl_rpc_url: str,
        mn_rpc_url: str,
        hl_strategy_address: str,
        bridge_strategy_address: str,
        *,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        verification_payload_url: str | None = None,
        verification_payload_resolver: VerificationResolver | None = None,
        wait_for_receipt: bool = True,
        receipt_timeout: float = DEFAULT_RECEIPT_TIMEOUT,
        testnet: bool = True,
        mainnet_bridge_strategy_address: str | None = None,
        iris_poll_interval: float = DEFAULT_IRIS_POLL_INTERVAL,
        iris_max_polls: int = DEFAULT_IRIS_MAX_POLLS,
        hyperliquid_domain: int | None = None,
        mainnet_domain: int | None = None,
        cctp_finality_threshold: int = DEFAULT_CCTP_FINALITY_THRESHOLD,
    ) -> None:
        self.private_key = private_key
        self.hl_rpc_url = hl_rpc_url
        self.mn_rpc_url = mn_rpc_url
        self.hl_strategy_address = cast(ChecksumAddress, validate_address(hl_strategy_address))
        self.bridge_strategy_address = cast(
            ChecksumAddress, validate_address(bridge_strategy_address)
        )
        self._mainnet_bridge_address: ChecksumAddress | None = (
            cast(ChecksumAddress, validate_address(mainnet_bridge_strategy_address))
            if mainnet_bridge_strategy_address
            else None
        )
        self.corewriter_address = cast(ChecksumAddress, validate_address(Precompile.COREWRITER))

        self._verification_payload_url = verification_payload_url
        self._verification_payload_resolver: VerificationResolver | None = (
            verification_payload_resolver
        )
        self._request_timeout = request_timeout
        self._wait_for_receipt = wait_for_receipt
        self._receipt_timeout = receipt_timeout
        self._testnet = testnet
        self._hyper_domain = hyperliquid_domain if hyperliquid_domain is not None else 19
        self._mainnet_domain = mainnet_domain if mainnet_domain is not None else 0
        self._cctp_finality_threshold = cctp_finality_threshold
        self._iris_base_url = IRIS_API_SANDBOX if self._testnet else IRIS_API_PROD
        self._iris_poll_interval = iris_poll_interval
        self._iris_max_polls = iris_max_polls

        self._hl_provider: HTTPProvider | None = None
        self._mn_provider: HTTPProvider | None = None
        self._web3: Web3 | None = None
        self._mainnet_web3: Web3 | None = None
        self._account: LocalAccount | None = None
        self._strategy_contract: Contract | None = None
        self._chain_id: int | None = None
        self._connected = False
        self._subvault_address: ChecksumAddress | None = None
        self._hyper_bridge_contract: Contract | None = None
        self._mainnet_bridge_contract: Contract | None = None
        self._session = requests.Session()
        self._asset_by_symbol: dict[str, int] = {}
        self._token_index_by_symbol: dict[str, int] = {}
        self._hype_token_index: int | None = None
        self._metadata_loaded = False

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
            account = cast(LocalAccount, Account.from_key(self.private_key))  # type: ignore[arg-type]

            hl_provider, hl_web3 = self._build_web3_provider(
                self.hl_rpc_url, network_name="HyperLiquid"
            )
            self._hl_provider = hl_provider
            self._web3 = hl_web3
            self._account = account
            self._apply_account_middleware(hl_web3, account)
            abi = self._fetch_strategy_abi()
            contract = hl_web3.eth.contract(address=self.hl_strategy_address, abi=abi)

            self._strategy_contract = contract
            self._chain_id = hl_web3.eth.chain_id
            self._subvault_address = None
            self._hyper_bridge_contract = None
            self._mainnet_bridge_contract = None

            mn_provider, mn_web3 = self._build_web3_provider(
                self.mn_rpc_url, network_name="Mainnet"
            )
            self._mn_provider = mn_provider
            self._mainnet_web3 = mn_web3
            self._apply_account_middleware(mn_web3, account)

            # Clear any cached metadata from previous connection
            if hasattr(self._resolve_perp_sz_decimals, "cache_clear"):
                self._resolve_perp_sz_decimals.cache_clear()
            if hasattr(self._resolve_spot_base_sz_decimals, "cache_clear"):
                self._resolve_spot_base_sz_decimals.cache_clear()

            # Configure gas strategy for automatic gas pricing
            try:
                from web3.gas_strategies.rpc import rpc_gas_price_strategy

                hl_web3.eth.set_gas_price_strategy(rpc_gas_price_strategy)
                logger.debug("Configured RPC gas price strategy")
            except ImportError:
                logger.debug("RPC gas price strategy not available, using web3.py defaults")

            logger.info("Connected to HyperLiquid EVM at %s", self.hl_rpc_url)
            logger.info("Connected to Mainnet RPC at %s", self.mn_rpc_url)

            try:
                self._hype_token_index = contract.functions.hypeTokenIndex().call()
            except Exception:
                self._hype_token_index = None

            self._subvault_address = self.subvault_address
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
        """Clear cached web3 state and invalidate caches."""

        self._hl_provider = None
        self._mn_provider = None
        self._web3 = None
        self._mainnet_web3 = None
        self._account = None
        self._strategy_contract = None
        self._chain_id = None
        self._connected = False
        self._subvault_address = None
        self._hyper_bridge_contract = None
        self._mainnet_bridge_contract = None
        # Clear lru_cache for metadata methods
        self._resolve_perp_sz_decimals.cache_clear()
        self._resolve_spot_base_sz_decimals.cache_clear()

    def is_connected(self) -> bool:
        return self._connected and self._web3 is not None and self._strategy_contract is not None

    def _build_web3_provider(self, rpc_url: str, *, network_name: str) -> tuple[HTTPProvider, Web3]:
        provider = HTTPProvider(rpc_url, request_kwargs={"timeout": self._request_timeout})
        web3 = Web3(provider)
        if not web3.is_connected():
            raise NetworkError(f"Unable to connect to {network_name} RPC", endpoint=rpc_url)
        return provider, web3

    def _apply_account_middleware(self, web3: Web3, account: LocalAccount) -> None:
        web3.middleware_onion.add(cast(Any, SignAndSendRawMiddlewareBuilder.build(account)))
        web3.eth.default_account = account.address

    def _load_and_validate_subvault(self) -> ChecksumAddress:
        try:
            contract = self.strategy_contract
        except NetworkError as exc:
            raise NetworkError(
                "Strategy contract unavailable while fetching subvault",
                endpoint=self.rpc_url,
            ) from exc

        try:
            raw_subvault = contract.functions.subvault().call()
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
            Precompile.CORE_USER_EXISTS,
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

    @transaction_method("limit_order", OrderResponse)
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
        """Place a limit order using the decorator pattern."""
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
        args = [
            asset_id,
            price_uint,
            size_uint,
            reduce_only,
            tif_uint,
            cloid_uint,
            payload.as_tuple(),
        ]

        return fn_name, args, context, {"order_id": None, "cloid": cloid}  # type: ignore[return-value]

    @transaction_method("cancel_order_by_oid", CancelResponse)
    def cancel_order_by_oid(self, asset: str, order_id: int) -> CancelResponse:
        """Cancel an order by its order ID."""
        asset_id = self._resolve_asset_id(asset)
        oid = int(order_id)
        context = {"asset": asset_id, "oid": oid}
        payload = self._resolve_verification_payload("cancel_order_by_oid", context)
        args = [asset_id, oid, payload.as_tuple()]

        return "cancelOrderByOid", args, context, {"cancelled_orders": 1}  # type: ignore[return-value]

    @transaction_method("cancel_order_by_cloid", CancelResponse)
    def cancel_order_by_cloid(self, asset: str, cloid: str) -> CancelResponse:
        """Cancel an order by its client order ID."""
        asset_id = self._resolve_asset_id(asset)
        cloid_uint = cloid_to_uint128(cloid)
        context = {"asset": asset_id, "cloid": cloid_uint}
        payload = self._resolve_verification_payload("cancel_order_by_cloid", context)
        args = [asset_id, cloid_uint, payload.as_tuple()]

        return "cancelOrderByCloid", args, context, {"cancelled_orders": 1}  # type: ignore[return-value]

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

    @transaction_method("spot_send", SendResponse)
    def spot_send(
        self, recipient: str, token: str, amount: float, destination: str
    ) -> SendResponse:
        """Send spot tokens to EVM."""
        amount_uint = size_to_uint64(amount)
        context = {"token": token, "amount": amount_uint, "recipient": recipient}
        payload = self._resolve_verification_payload("spot_send", context)

        if self._is_hype_token(token):
            args = [amount_uint, payload.as_tuple()]
            fn_name = "withdrawHypeToEvm"
        else:
            token_index = self._resolve_token_index(token)
            args = [token_index, amount_uint, payload.as_tuple()]
            fn_name = "withdrawTokenToEvm"

        return fn_name, args, context, {"recipient": recipient, "amount": amount}  # type: ignore[return-value]

    def perp_send(self, recipient: str, amount: float, destination: str) -> SendResponse:
        message = "Perp collateral send is not exposed by the HyperliquidStrategy contract"
        return SendResponse(success=False, recipient=recipient, amount=None, error=message)

    def bridge_mainnet_to_hyperliquid(
        self,
        amount: float,
        *,
        max_fee: int | None = None,
        min_finality_threshold: int | None = None,
    ) -> BridgeResponse:
        """Bridge USDC from Ethereum mainnet to HyperEVM via CCTPv2."""

        try:
            self._ensure_connected()
            source_contract = self._ensure_bridge_contract("mainnet")
            destination_contract = self._ensure_bridge_contract("hyper")
        except (ValidationError, NetworkError) as exc:
            return BridgeResponse(
                success=False,
                error=str(exc),
                raw_response={
                    "field": getattr(exc, "field", None),
                    "value": getattr(exc, "value", None),
                    "details": getattr(exc, "details", None),
                    "direction": "mainnet_to_hyper",
                },
            )

        return self._bridge_via_cctp(
            amount=amount,
            source_contract=source_contract,
            destination_contract=destination_contract,
            source_domain=self._mainnet_domain,
            destination_domain=self._hyper_domain,
            direction="mainnet_to_hyper",
            max_fee_override=max_fee,
            min_finality_threshold=min_finality_threshold,
            source_web3=self.mainnet_web3,
            destination_web3=self.hyperliquid_web3,
        )

    def bridge_hyperliquid_to_mainnet(
        self,
        amount: float,
        *,
        max_fee: int | None = None,
        min_finality_threshold: int | None = None,
    ) -> BridgeResponse:
        """Bridge USDC from HyperEVM back to Ethereum mainnet via CCTPv2."""

        try:
            self._ensure_connected()
            source_contract = self._ensure_bridge_contract("hyper")
            destination_contract = self._ensure_bridge_contract("mainnet")
        except (ValidationError, NetworkError) as exc:
            return BridgeResponse(
                success=False,
                error=str(exc),
                raw_response={
                    "field": getattr(exc, "field", None),
                    "value": getattr(exc, "value", None),
                    "details": getattr(exc, "details", None),
                    "direction": "hyper_to_mainnet",
                },
            )

        return self._bridge_via_cctp(
            amount=amount,
            source_contract=source_contract,
            destination_contract=destination_contract,
            source_domain=self._hyper_domain,
            destination_domain=self._mainnet_domain,
            direction="hyper_to_mainnet",
            max_fee_override=max_fee,
            min_finality_threshold=min_finality_threshold,
            source_web3=self.hyperliquid_web3,
            destination_web3=self.mainnet_web3,
        )

    @transaction_method("usd_class_transfer_to_perp", TransferResponse)
    def usd_class_transfer_to_perp(self, amount: float) -> TransferResponse:
        """Transfer USD from spot to perpetual account."""
        amount_uint = size_to_uint64(amount, 6)
        context = {"amount": amount_uint}
        payload = self._resolve_verification_payload("usd_class_transfer_to_perp", context)
        args = [amount_uint, payload.as_tuple()]

        return "transferSpotToPerp", args, context, {"amount": amount}  # type: ignore[return-value]

    @transaction_method("usd_class_transfer_to_spot", TransferResponse)
    def usd_class_transfer_to_spot(self, amount: float) -> TransferResponse:
        """Transfer USD from perpetual to spot account."""
        amount_uint = size_to_uint64(amount, 6)
        context = {"amount": amount_uint}
        payload = self._resolve_verification_payload("usd_class_transfer_to_spot", context)
        args = [amount_uint, payload.as_tuple()]

        return "transferPerpToSpot", args, context, {"amount": amount}  # type: ignore[return-value]

    def finalize_subaccount(self, subaccount: str) -> FinalizeResponse:
        message = "Subaccount finalization must be executed via CoreWriter directly"
        return FinalizeResponse(success=False, subaccount=subaccount, error=message)

    def approve_builder_fee(self, builder: str, fee: float, nonce: int) -> ApprovalResponse:
        message = "Builder fee approvals are not implemented on the strategy contract"
        return ApprovalResponse(success=False, builder=builder, fee=fee, nonce=nonce, error=message)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _bridge_via_cctp(
        self,
        *,
        amount: float,
        source_contract: Contract,
        destination_contract: Contract,
        source_domain: int,
        destination_domain: int,
        direction: str,
        max_fee_override: int | None,
        min_finality_threshold: int | None,
        source_web3: Web3,
        destination_web3: Web3,
    ) -> BridgeResponse:
        try:
            amount_units, amount_decimal, truncated = self._normalise_usdc_amount(amount)
        except ValidationError as exc:
            return BridgeResponse(
                success=False,
                error=str(exc),
                raw_response={
                    "direction": direction,
                    "field": exc.field,
                    "value": exc.value,
                    "details": exc.details,
                },
            )

        if truncated:
            logger.warning(
                "Truncating bridge amount to 6 decimals (%s request on %s)", amount, direction
            )

        if max_fee_override is not None and max_fee_override < 0:
            return BridgeResponse(
                success=False,
                amount=float(amount_decimal),
                error="max_fee must be non-negative",
                raw_response={"direction": direction, "max_fee": max_fee_override},
            )

        finality_threshold = (
            min_finality_threshold
            if min_finality_threshold is not None
            else self._cctp_finality_threshold
        )
        if finality_threshold <= 0:
            return BridgeResponse(
                success=False,
                amount=float(amount_decimal),
                error="Finality threshold must be positive",
                raw_response={"direction": direction, "finality_threshold": finality_threshold},
            )

        try:
            max_fee = (
                max_fee_override
                if max_fee_override is not None
                else self._fetch_cctp_fee(amount_units, source_domain, destination_domain)
            )
        except ValidationError as exc:
            return BridgeResponse(
                success=False,
                amount=float(amount_decimal),
                error=str(exc),
                raw_response={
                    "direction": direction,
                    "field": exc.field,
                    "value": exc.value,
                    "details": exc.details,
                },
            )
        except requests.RequestException as exc:
            logger.error("Failed to fetch CCTP fee quote: %s", exc)
            return BridgeResponse(
                success=False,
                amount=float(amount_decimal),
                error=f"Failed to fetch CCTP fee quote: {exc}",
                raw_response={"direction": direction},
            )

        if max_fee >= amount_units:
            return BridgeResponse(
                success=False,
                amount=float(amount_decimal),
                error="Quoted max fee exceeds or equals bridge amount",
                raw_response={
                    "direction": direction,
                    "max_fee": max_fee,
                    "amount_units": amount_units,
                },
            )

        payload_entry = VerificationPayload.default().as_tuple()
        payload = [payload_entry, payload_entry]
        logger.info(
            "Initiating CCTP bridge %(dir)s: amount=%(amt).6f, domains %(src)s->%(dst)s",
            {
                "dir": direction,
                "amt": float(amount_decimal),
                "src": source_domain,
                "dst": destination_domain,
            },
        )

        try:
            burn_tx = source_contract.functions.bridgeUSDCViaCCTPv2(
                amount_units,
                max_fee,
                finality_threshold,
                payload,
            ).transact()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to submit CCTP burn on %s", direction)
            return BridgeResponse(
                success=False,
                amount=float(amount_decimal),
                error=str(exc),
                raw_response={
                    "direction": direction,
                    "max_fee": max_fee,
                    "amount_units": amount_units,
                },
            )

        burn_tx_hash = burn_tx.hex()
        logger.info("Submitted CCTP burn (%s): %s", direction, burn_tx_hash)
        burn_receipt = (
            source_web3.eth.wait_for_transaction_receipt(burn_tx, timeout=self._receipt_timeout)
            if self._wait_for_receipt
            else None
        )

        try:
            message, attestation = self._poll_iris_attestation(source_domain, burn_tx_hash)
        except TimeoutError as exc:
            logger.error("IRIS attestation timed out for %s", direction)
            return BridgeResponse(
                success=False,
                amount=float(amount_decimal),
                error=str(exc),
                burn_tx_hash=burn_tx_hash,
                raw_response={
                    "direction": direction,
                    "max_fee": max_fee,
                    "amount_units": amount_units,
                    "burn_receipt": serialise_receipt(burn_receipt) if burn_receipt else None,
                },
            )

        try:
            claim_tx = destination_contract.functions.receiveUSDCViaCCTPv2(
                message, attestation
            ).transact()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to submit CCTP claim on %s", direction)
            return BridgeResponse(
                success=False,
                amount=float(amount_decimal),
                error=str(exc),
                burn_tx_hash=burn_tx_hash,
                message=message,
                attestation=attestation,
                raw_response={
                    "direction": direction,
                    "max_fee": max_fee,
                    "amount_units": amount_units,
                    "burn_receipt": serialise_receipt(burn_receipt) if burn_receipt else None,
                },
            )

        claim_tx_hash = claim_tx.hex()
        logger.info("Submitted CCTP claim (%s): %s", direction, claim_tx_hash)
        claim_receipt = (
            destination_web3.eth.wait_for_transaction_receipt(
                claim_tx, timeout=self._receipt_timeout
            )
            if self._wait_for_receipt
            else None
        )

        amount_float = float(Decimal(amount_units) / USDC_SCALING)
        return BridgeResponse(
            success=True,
            amount=amount_float,
            burn_tx_hash=burn_tx_hash,
            claim_tx_hash=claim_tx_hash,
            message=message,
            attestation=attestation,
            raw_response={
                "direction": direction,
                "max_fee": max_fee,
                "amount_units": amount_units,
                "finality_threshold": finality_threshold,
                "burn_receipt": serialise_receipt(burn_receipt) if burn_receipt else None,
                "claim_receipt": serialise_receipt(claim_receipt) if claim_receipt else None,
                "source_domain": source_domain,
                "destination_domain": destination_domain,
            },
        )

    def _normalise_usdc_amount(self, amount: float | str | Decimal) -> tuple[int, Decimal, bool]:
        if isinstance(amount, Decimal):
            quantity = amount
        else:
            try:
                quantity = Decimal(str(amount))
            except (ValueError, InvalidOperation) as exc:
                raise ValidationError(
                    "Invalid USDC amount",
                    field="amount",
                    value=amount,
                    details={"error": str(exc)},
                ) from exc

        if quantity <= 0:
            raise ValidationError(
                "Bridge amount must be positive", field="amount", value=float(quantity)
            )

        scaled_decimal = quantity * USDC_SCALING
        scaled_integral = scaled_decimal.to_integral_value(rounding=ROUND_DOWN)
        truncated = scaled_integral != scaled_decimal

        return int(scaled_integral), scaled_integral / USDC_SCALING, truncated

    def _fetch_cctp_fee(self, amount_units: int, src_domain: int, dest_domain: int) -> int:
        url = f"{self._iris_base_url}/v2/burn/USDC/fees/{src_domain}/{dest_domain}"
        response = self._session.get(url, timeout=self._request_timeout)
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, list):
            raise ValidationError(
                "Unexpected fee response format",
                field="iris_response",
                value=payload,
            )

        chosen_entry: Mapping[str, Any] | None = None
        for entry in payload:
            if (
                isinstance(entry, Mapping)
                and entry.get("finalityThreshold") == self._cctp_finality_threshold
            ):
                chosen_entry = entry
                break
        if chosen_entry is None:
            for entry in payload:
                if isinstance(entry, Mapping):
                    chosen_entry = entry
                    break

        if not chosen_entry:
            logger.warning(
                "Fee response missing usable entries for domains %s -> %s", src_domain, dest_domain
            )
            return 0

        try:
            bps = int(chosen_entry.get("minimumFee", 0))
        except (TypeError, ValueError):
            bps = 0

        fee = (amount_units * bps + 9999) // 10000
        logger.info(
            "CCTP fee quote %s -> %s: bps=%s maxFee=%s",
            src_domain,
            dest_domain,
            bps,
            fee,
        )
        return fee

    def _poll_iris_attestation(self, domain: int, tx_hash: str) -> tuple[str, str]:
        url = f"{self._iris_base_url}/v2/messages/{domain}?transactionHash={tx_hash}"
        for attempt in range(1, self._iris_max_polls + 1):
            try:
                response = self._session.get(
                    url,
                    timeout=self._request_timeout,
                    headers={"Cache-Control": "no-cache"},
                )
            except requests.RequestException as exc:
                logger.debug("IRIS poll attempt %s failed: %s", attempt, exc)
                time.sleep(self._iris_poll_interval)
                continue

            if response.status_code == 200:
                payload = response.json()
                messages = self._extract_iris_messages(payload)
                if messages:
                    entry = messages[0]
                    attestation = entry.get("attestation")
                    message = entry.get("message")
                    if attestation and attestation != "PENDING" and message:
                        logger.info("IRIS attestation ready on attempt %s", attempt)
                        return str(message), str(attestation)
                    logger.debug("IRIS message pending on attempt %s", attempt)
            elif response.status_code != 404:
                logger.debug(
                    "IRIS poll attempt %s returned status %s",
                    attempt,
                    response.status_code,
                )

            time.sleep(self._iris_poll_interval)

        raise TimeoutError(
            f"Timed out waiting for IRIS attestation after {self._iris_max_polls * self._iris_poll_interval:.0f} seconds"
        )

    def _extract_iris_messages(self, payload: Any) -> list[Mapping[str, Any]]:
        if isinstance(payload, Mapping):
            direct = payload.get("messages")
            if isinstance(direct, list):
                return [entry for entry in direct if isinstance(entry, Mapping)]
            data = payload.get("data")
            if isinstance(data, Mapping):
                nested = data.get("messages")
                if isinstance(nested, list):
                    return [entry for entry in nested if isinstance(entry, Mapping)]
        return []

    def _ensure_bridge_contract(self, chain: str) -> Contract:
        if chain == "hyper":
            if self._hyper_bridge_contract is None:
                web3 = self.hyperliquid_web3
                self._hyper_bridge_contract = web3.eth.contract(
                    address=self.bridge_strategy_address,
                    abi=HyperliquidBridgeStrategy_abi,
                )
            return self._hyper_bridge_contract

        if chain == "mainnet":
            if self._mainnet_bridge_address is None:
                raise ValidationError(
                    "Mainnet bridge strategy address is not configured",
                    field="bridge_strategy_address",
                )
            if self._mainnet_bridge_contract is None:
                web3 = self.mainnet_web3
                self._mainnet_bridge_contract = web3.eth.contract(
                    address=self._mainnet_bridge_address,
                    abi=HyperliquidBridgeStrategy_abi,
                )
            return self._mainnet_bridge_contract

        raise ValidationError("Unknown bridge chain", field="chain", value=chain)

    def _ensure_connected(self) -> None:
        if not self.is_connected():
            raise NetworkError("EVM connector is not connected", endpoint=self.rpc_url)

        try:
            self.hyperliquid_web3
            self.account
            self.strategy_contract
        except NetworkError as exc:
            raise NetworkError("EVM connector is not connected", endpoint=self.rpc_url) from exc

    def _call_l1_read_precompile(
        self,
        address: str | Precompile,
        input_types: Sequence[str],
        args: Sequence[Any],
        output_types: Sequence[str],
    ) -> tuple[Any, ...]:
        web3 = self.hyperliquid_web3

        call_data = abi_encode(list(input_types), list(args)) if input_types else b""
        addr_str = address.value if isinstance(address, Precompile) else address
        destination = Web3.to_checksum_address(addr_str)

        try:
            result = web3.eth.call({"to": destination, "data": call_data})
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
            Precompile.BBO,
            ["uint32"],
            [asset_id],
            ["uint64", "uint64"],
        )
        return int(bid_uint), int(ask_uint)

    def _read_mark_price(self, asset_id: int) -> int:
        (mark_uint,) = self._call_l1_read_precompile(
            Precompile.MARK_PX,
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
                convert_perp_price(mid_uint, sz_decimals),
                convert_perp_price(bid_uint, sz_decimals) if bid_uint else None,
                convert_perp_price(ask_uint, sz_decimals) if ask_uint else None,
            )

        # Try spot conversion
        base_sz_decimals = self._resolve_spot_base_sz_decimals(asset_id)
        if base_sz_decimals is not None:
            return (
                convert_spot_price(mid_uint, base_sz_decimals),
                convert_spot_price(bid_uint, base_sz_decimals) if bid_uint else None,
                convert_spot_price(ask_uint, base_sz_decimals) if ask_uint else None,
            )

        # Fallback to default conversion
        return (
            uint64_to_price(mid_uint),
            uint64_to_price(bid_uint) if bid_uint else None,
            uint64_to_price(ask_uint) if ask_uint else None,
        )

    @lru_cache(maxsize=128)
    def _resolve_perp_sz_decimals(self, asset_id: int) -> int | None:
        """Cached retrieval of perpetual size decimals for a given asset."""
        try:
            logger.debug(f"Calling perpAssetInfo precompile for asset {asset_id}")
            result = self._call_l1_read_precompile(
                Precompile.PERP_ASSET_INFO,
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
        return sz_decimals

    @lru_cache(maxsize=128)
    def _resolve_spot_base_sz_decimals(self, asset_id: int) -> int | None:
        """Cached retrieval of spot base size decimals for a given asset."""
        try:
            spot_info = self._call_l1_read_precompile(
                Precompile.SPOT_INFO,
                ["uint32"],
                [asset_id],
                ["(string,uint64[2])"],  # Returns a tuple
            )
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
                Precompile.TOKEN_INFO,
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

        return sz_decimals

    def _resolve_trader_address(self) -> str:
        if self._subvault_address is not None:
            return self._subvault_address

        try:
            return self.subvault_address
        except ValidationError as exc:
            raise NetworkError(str(exc), endpoint=self.rpc_url, details=exc.details) from exc
        except NetworkError:
            pass
        except Exception as exc:  # pragma: no cover - defensive
            raise NetworkError(
                "Unexpected failure resolving strategy subvault",
                endpoint=self.rpc_url,
                details={"error": str(exc)},
            ) from exc

        try:
            return self.account.address
        except NetworkError:
            pass

        raise NetworkError("Trading account address unavailable", endpoint=self.rpc_url)

    def _fetch_user_position(self, asset: str) -> Mapping[str, Any] | None:
        trader_address = self._resolve_trader_address()

        payload = {"type": "clearinghouseState", "user": trader_address}
        state = self._request_json("POST", self._info_url, payload)

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
        # eventually fetch from etherscan

        _strategy_abi = HyperliquidStrategy_abi
        return _strategy_abi

    def load_asset_metadata_from_info(self) -> None:
        """Fetch asset metadata directly from the HyperLiquid info endpoint."""

        payload = self._request_json("POST", self._info_url, {"type": "meta"})
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
            url = build_verification_url(self._verification_payload_url, action, context)
            data = self._request_json("GET", url)
            mapped = dict(data) if isinstance(data, Mapping) else None
            return VerificationPayload.from_dict(mapped)

        return VerificationPayload.default()

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

    def _request_json(
        self,
        method: str,
        url: str | None,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        if not url:
            raise ValueError("No URL provided for HTTP request")

        response = self._session.request(
            method,
            url,
            json=payload,
            timeout=self._request_timeout,
        )
        response.raise_for_status()
        return response.json()

    def _send_contract_transaction(
        self,
        function_name: str,
        args: Sequence[Any],
        *,
        action: str,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Send a transaction to the strategy contract using web3.py's built-in methods."""
        web3 = self.hyperliquid_web3
        contract = self.strategy_contract
        self.account  # Ensure signer is hydrated before dispatching

        contract_function = getattr(contract.functions, function_name)(*args)
        logger.info("Dispatching %s via %s", action, function_name)

        tx_hash = contract_function.transact()
        logger.info("Transaction sent for action=%s hash=%s", action, tx_hash.hex())

        receipt = (
            web3.eth.wait_for_transaction_receipt(tx_hash, timeout=self._receipt_timeout)
            if self._wait_for_receipt
            else None
        )

        if receipt:
            logger.info(
                "Transaction confirmed for action=%s hash=%s block=%s",
                action,
                tx_hash.hex(),
                getattr(receipt, "blockNumber", None),
            )

        return {
            "tx_hash": tx_hash.hex(),
            "action": action,
            "context": dict(context),
            "receipt": serialise_receipt(receipt) if receipt else None,
            "block_number": getattr(receipt, "blockNumber", None) if receipt else None,
        }

    @property
    def account(self) -> LocalAccount:
        if self._account is None:
            raise NetworkError(
                "Signer account is not initialized; call connect() first",
                endpoint=self.hl_rpc_url,
            )
        return self._account

    @property
    def strategy_contract(self) -> Contract:
        if self._strategy_contract is None:
            raise NetworkError(
                "Strategy contract is not connected; call connect() first",
                endpoint=self.hl_rpc_url,
            )
        return self._strategy_contract

    @property
    def hyperliquid_web3(self) -> Web3:
        if self._web3 is None:
            raise NetworkError(
                "HyperLiquid Web3 provider is not connected", endpoint=self.hl_rpc_url
            )
        return self._web3

    @property
    def mainnet_web3(self) -> Web3:
        if self._mainnet_web3 is None:
            raise NetworkError("Mainnet Web3 provider is not connected", endpoint=self.mn_rpc_url)
        return self._mainnet_web3

    @property
    def subvault_address(self) -> ChecksumAddress:
        if self._subvault_address is not None:
            return self._subvault_address

        self._subvault_address = self._load_and_validate_subvault()
        return self._subvault_address

    @property
    def rpc_url(self) -> str:
        return self.hl_rpc_url
