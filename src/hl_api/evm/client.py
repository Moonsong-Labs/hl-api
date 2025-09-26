"""HyperLiquid EVM implementation that routes actions through a strategy contract."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import requests
from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.contract import Contract
from web3.types import ChecksumAddress

from ..base import HLProtocolBase
from ..constants import Precompile
from ..exceptions import NetworkError, ValidationError
from ..types import (
    Response,
    VerificationPayload,
)
from ..utils import (
    cloid_to_uint128,
    encode_tif,
    format_price_for_api,
    to_uint64,
)
from .bridge import CCTPBridge
from .config import (
    DEFAULT_CCTP_FINALITY_THRESHOLD,
    DEFAULT_IRIS_MAX_POLLS,
    DEFAULT_IRIS_POLL_INTERVAL,
    DEFAULT_RECEIPT_TIMEOUT,
    DEFAULT_REQUEST_TIMEOUT,
    EVMClientConfig,
)
from .connections import Web3Connections
from .metadata import AssetMetadataCache
from .proofs import FlexibleVaultProofResolver
from .transactions import TransactionDispatcher

logger = logging.getLogger(__name__)


@dataclass
class TxRequest:
    """Transaction request details for clean separation of concerns."""

    function: str
    args: list[Any]
    action: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    response_class: type[Response] = Response
    response_fields: dict[str, Any] = field(default_factory=dict)


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
        wait_for_receipt: bool = True,
        receipt_timeout: float = DEFAULT_RECEIPT_TIMEOUT,
        testnet: bool = True,
        iris_base_url: str | None = None,
        iris_poll_interval: float = DEFAULT_IRIS_POLL_INTERVAL,
        iris_max_polls: int = DEFAULT_IRIS_MAX_POLLS,
        hyperliquid_domain: int | None = None,
        mainnet_domain: int | None = None,
        cctp_finality_threshold: int = DEFAULT_CCTP_FINALITY_THRESHOLD,
        flexible_vault_proof_blob: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
        disable_call_verification: bool = False,
    ) -> None:
        hl_address = Web3.to_checksum_address(hl_strategy_address)
        bridge_address = Web3.to_checksum_address(bridge_strategy_address)

        config = EVMClientConfig(
            private_key=private_key,
            hl_rpc_url=hl_rpc_url,
            mn_rpc_url=mn_rpc_url,
            hl_strategy_address=hl_address,
            bridge_strategy_address=bridge_address,
            request_timeout=request_timeout,
            testnet=testnet,
            wait_for_receipt=wait_for_receipt,
            receipt_timeout=receipt_timeout,
            iris_base_url=iris_base_url,
            iris_poll_interval=iris_poll_interval,
            iris_max_polls=iris_max_polls,
            hyperliquid_domain=hyperliquid_domain,
            mainnet_domain=mainnet_domain,
            cctp_finality_threshold=cctp_finality_threshold,
            flexible_vault_proof_blob=flexible_vault_proof_blob,
        )

        self._config = config
        self._session = requests.Session()
        self._connections = Web3Connections(config)
        self._metadata = AssetMetadataCache(config, self._connections, self._session)
        self._dispatcher = TransactionDispatcher(
            self._connections,
            wait_for_receipt=config.wait_for_receipt,
            receipt_timeout=config.receipt_timeout,
        )
        self._call_verification_disabled = disable_call_verification
        self._flexible_proof_resolver: FlexibleVaultProofResolver | None
        if not self._call_verification_disabled and config.flexible_vault_proof_blob:
            self._flexible_proof_resolver = FlexibleVaultProofResolver(
                config,
                self._connections,
                self._session,
                request_timeout=config.request_timeout,
            )
        else:
            self._flexible_proof_resolver = None
        self._bridge_helper = CCTPBridge(
            config,
            self._connections,
            self._session,
            verification_resolver=self._flexible_proof_resolver,
            disable_call_verification=self._call_verification_disabled,
        )

        self._asset_by_symbol = self._metadata.asset_by_symbol
        self._token_index_by_symbol = self._metadata.token_index_by_symbol
        self._metadata_loaded = self._metadata.metadata_loaded
        self._hype_token_index: int | None = None
        self._connected = False

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> None:
        try:
            self._connections.connect()
            self._metadata.reset()
            self._metadata_loaded = self._metadata.metadata_loaded
            self._hype_token_index = self._connections.hype_token_index

            try:
                from web3.gas_strategies.rpc import rpc_gas_price_strategy  # type: ignore

                self._connections.hyperliquid_web3.eth.set_gas_price_strategy(
                    rpc_gas_price_strategy
                )
                logger.debug("Configured RPC gas price strategy")
            except ImportError:
                logger.debug("RPC gas price strategy not available, using web3.py defaults")

            self._connected = True
        except (ValidationError, NetworkError):
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
        self._connections.disconnect()
        self._metadata.reset()
        self._metadata_loaded = self._metadata.metadata_loaded
        self._hype_token_index = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connections.is_connected()

    def _ensure_connected(self) -> None:
        self._connections.ensure_connected()

    def _execute_transaction(self, tx_request: TxRequest, func_name: str) -> Response:
        """Execute a transaction and return the appropriate response."""
        try:
            self._ensure_connected()

            tx_result = self._send_contract_transaction(
                tx_request.function,
                tx_request.args,
                action=tx_request.action or func_name,
                context=tx_request.context,
            )

            receipt = tx_result.get("receipt")
            status = bool(receipt is None or receipt.get("status", 0) == 1)

            response_data: dict[str, Any] = {
                "success": status,
                "transaction_hash": tx_result["tx_hash"],
                "error": None if status else tx_result.get("error", "Transaction reverted"),
                "raw_response": tx_result,
            }

            for key, value in tx_request.response_fields.items():
                response_data[key] = value

            return tx_request.response_class(**response_data)

        except (ValidationError, NetworkError) as exc:
            return tx_request.response_class(
                success=False,
                error=str(exc),
                **{
                    k: v
                    for k, v in tx_request.response_fields.items()
                    if k not in ["success", "error"]
                },
            )
        except Exception as exc:
            logger.exception(f"Unexpected {func_name} failure")
            return tx_request.response_class(success=False, error=str(exc))

    # ------------------------------------------------------------------
    # Core actions
    # ------------------------------------------------------------------
    def get_market_price(self, asset: str) -> float:
        self._ensure_connected()
        mid_price, _, _ = self._market_price_context(asset)
        return float(mid_price)

    def market_order(
        self,
        asset: str,
        is_buy: bool,
        sz: float,
        slippage: float = 0.05,
        cloid: str | None = None,
    ) -> Response:
        try:
            mid_price, bid_price, ask_price = self._market_price_context(asset)
            limit_price = self._compute_slippage_price(asset, float(mid_price), is_buy, slippage)
        except (NetworkError, ValidationError) as exc:
            logger.error("Failed to compute market order price for %s: %s", asset, exc)
            return Response(success=False, cloid=cloid, error=str(exc))

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
    ) -> Response:
        self._ensure_connected()

        try:
            position = self._fetch_user_position(asset)
        except NetworkError as exc:
            logger.error("Failed to fetch position state for %s: %s", asset, exc)
            return Response(success=False, cloid=cloid, error=str(exc))

        if position is None:
            message = f"No open position found for asset {asset}"
            logger.info(message)
            return Response(success=False, cloid=cloid, error=message)

        szi_raw = position.get("szi")
        try:
            position_size = float(szi_raw) if szi_raw is not None else 0.0
        except (TypeError, ValueError) as exc:
            error = ValidationError(
                "Unable to parse current position size",
                field="szi",
                value=position.get("szi"),
                details={"error": str(exc)},
            )
            return Response(success=False, cloid=cloid, error=str(error))

        if position_size == 0:
            message = f"No open position found for asset {asset}"
            logger.info(message)
            return Response(success=False, cloid=cloid, error=message)

        is_buy = position_size < 0

        if size is None:
            target_size = abs(position_size)
        else:
            try:
                target_size = float(size)
            except (TypeError, ValueError):
                error = ValidationError("Close size must be numeric", field="size", value=size)
                return Response(success=False, cloid=cloid, error=str(error))

        if target_size <= 0:
            error = ValidationError("Close size must be positive", field="size", value=target_size)
            return Response(success=False, cloid=cloid, error=str(error))

        try:
            mid_price = self.get_market_price(asset)
            limit_price = self._compute_slippage_price(asset, mid_price, is_buy, slippage)
        except (NetworkError, ValidationError) as exc:
            logger.error("Failed to compute close order price for %s: %s", asset, exc)
            return Response(success=False, cloid=cloid, error=str(exc))

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
    ) -> Response:
        asset_id = self._resolve_asset_id(asset)
        formatted_price = self._format_limit_price(asset_id, limit_px)
        price_uint = to_uint64(formatted_price, 8)
        size_uint = to_uint64(sz, 8)
        tif_uint = encode_tif(tif)
        cloid_uint = cloid_to_uint128(cloid)

        context = {
            "asset": asset_id,
            "is_buy": is_buy,
            "tif": tif_uint,
            "cloid": cloid_uint,
        }
        json_name = self._get_json_name_for_chain("hyperliquid")
        payload = self._resolve_verification_payload(
            "CoreWriter.sendRawAction{action: limit_order}(anyBytes)", json_name, context
        )
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

        tx_request = TxRequest(
            function=fn_name,
            args=args,
            action="limit_order",
            context=context,
            response_class=Response,
            response_fields={"order_id": None, "cloid": cloid},
        )
        return self._execute_transaction(tx_request, "limit_order")

    def cancel_order_by_oid(self, asset: str, order_id: int) -> Response:
        asset_id = self._resolve_asset_id(asset)
        oid = int(order_id)
        context = {"asset": asset_id, "oid": oid}

        json_name = self._get_json_name_for_chain("hyperliquid")
        payload = self._resolve_verification_payload(
            "CoreWriter.sendRawAction{action: cancel_oid}(anyBytes)", json_name, context
        )
        args = [asset_id, oid, payload.as_tuple()]

        tx_request = TxRequest(
            function="cancelOrderByOid",
            args=args,
            action="cancel_order_by_oid",
            context=context,
            response_class=Response,
            response_fields={"cancelled_orders": 1},
        )
        return self._execute_transaction(tx_request, "cancel_order_by_oid")

    def cancel_order_by_cloid(self, asset: str, cloid: str) -> Response:
        asset_id = self._resolve_asset_id(asset)
        cloid_uint = cloid_to_uint128(cloid)
        context = {"asset": asset_id, "cloid": cloid_uint}
        json_name = self._get_json_name_for_chain("hyperliquid")
        payload = self._resolve_verification_payload(
            "CoreWriter.sendRawAction{action: cancel_cloid}(anyBytes)", json_name, context
        )
        args = [asset_id, cloid_uint, payload.as_tuple()]

        tx_request = TxRequest(
            function="cancelOrderByCloid",
            args=args,
            action="cancel_order_by_cloid",
            context=context,
            response_class=Response,
            response_fields={"cancelled_orders": 1},
        )
        return self._execute_transaction(tx_request, "cancel_order_by_cloid")

    def vault_transfer(self, vault: str, is_deposit: bool, usd: float) -> Response:
        message = (
            "Vault transfers are not available via the HyperliquidStrategy contract; "
            "use usd_class_transfer_to_perp/spot instead"
        )
        logger.warning("vault_transfer not supported for vault %s", vault)
        return Response(success=False, amount=None, error=message)

    def spot_send(self, recipient: str, token: str, amount: float, destination: str) -> Response:
        amount_uint = to_uint64(amount, 8)
        context = {"token": token, "amount": amount_uint, "recipient": recipient}

        json_name = self._get_json_name_for_chain("hyperliquid")
        payload = self._resolve_verification_payload(
            "CoreWriter.sendRawAction{action: spot_send}(anyBytes)", json_name, context
        )

        if self._is_hype_token(token):
            args = [amount_uint, payload.as_tuple()]
            fn_name = "withdrawHypeToEvm"
        else:
            token_index = self._metadata.resolve_token_index(token)
            args = [token_index, amount_uint, payload.as_tuple()]
            fn_name = "withdrawTokenToEvm"

        tx_request = TxRequest(
            function=fn_name,
            args=args,
            action="spot_send",
            context=context,
            response_class=Response,
            response_fields={"recipient": recipient, "amount": amount},
        )
        return self._execute_transaction(tx_request, "spot_send")

    def perp_send(self, recipient: str, amount: float, destination: str) -> Response:
        message = "Perp collateral send is not exposed by the HyperliquidStrategy contract"
        return Response(success=False, recipient=recipient, amount=None, error=message)

    def bridge_mainnet_to_hyperliquid(
        self,
        amount: float,
        *,
        max_fee: int | None = None,
        min_finality_threshold: int | None = None,
    ) -> Response:
        self._ensure_connected()
        return self._bridge_helper.bridge_mainnet_to_hyperliquid(
            amount,
            max_fee=max_fee,
            min_finality_threshold=min_finality_threshold,
        )

    def bridge_hyperliquid_to_mainnet(
        self,
        amount: float,
        *,
        max_fee: int | None = None,
        min_finality_threshold: int | None = None,
    ) -> Response:
        self._ensure_connected()
        return self._bridge_helper.bridge_hyperliquid_to_mainnet(
            amount,
            max_fee=max_fee,
            min_finality_threshold=min_finality_threshold,
        )

    def usd_class_transfer_to_perp(self, amount: float) -> Response:
        amount_uint = to_uint64(amount, 6)
        context = {"amount": amount_uint}

        json_name = self._get_json_name_for_chain("hyperliquid")
        payload = self._resolve_verification_payload(
            "CoreWriter.sendRawAction{action: usd_transfer}(anyBytes)", json_name, context
        )
        args = [amount_uint, payload.as_tuple()]

        tx_request = TxRequest(
            function="transferSpotToPerp",
            args=args,
            action="usd_class_transfer_to_perp",
            context=context,
            response_class=Response,
            response_fields={"amount": amount},
        )
        return self._execute_transaction(tx_request, "usd_class_transfer_to_perp")

    def usd_class_transfer_to_spot(self, amount: float) -> Response:
        amount_uint = to_uint64(amount, 6)
        context = {"amount": amount_uint}

        json_name = self._get_json_name_for_chain("hyperliquid")
        payload = self._resolve_verification_payload(
            "CoreWriter.sendRawAction{action: usd_transfer}(anyBytes)", json_name, context
        )
        args = [amount_uint, payload.as_tuple()]

        tx_request = TxRequest(
            function="transferPerpToSpot",
            args=args,
            action="usd_class_transfer_to_spot",
            context=context,
            response_class=Response,
            response_fields={"amount": amount},
        )
        return self._execute_transaction(tx_request, "usd_class_transfer_to_spot")

    # ------------------------------------------------------------------
    # Market data helpers
    # ------------------------------------------------------------------
    def _market_price_context(self, asset: str) -> tuple[Decimal, Decimal | None, Decimal | None]:
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
        else:
            mid_uint = self._read_mark_price(asset_id)

        mid_price, bid_price, ask_price = self._metadata.convert_market_prices(
            asset_id, mid_uint, bid_uint, ask_uint
        )

        if mid_price is None or mid_price == Decimal(0):
            raise NetworkError(
                "Failed to convert market price to valid Decimal",
                details={"asset": asset, "asset_id": asset_id, "mid_uint": mid_uint},
            )
        logger.info(
            "Market price for %s (id %s): mid=%s, bid=%s, ask=%s",
            asset,
            asset_id,
            mid_price,
            bid_price,
            ask_price,
        )
        return mid_price, bid_price, ask_price

    def _fetch_bbo_prices(self, asset_id: int) -> tuple[int, int]:
        bid_uint, ask_uint = self._connections.call_precompile(
            Precompile.BBO,
            ["uint32"],
            [asset_id],
            ["uint64", "uint64"],
        )
        return int(bid_uint), int(ask_uint)

    def _read_mark_price(self, asset_id: int) -> int:
        (mark_uint,) = self._connections.call_precompile(
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
        formatted = self._format_limit_price(asset_id, raw_price)
        return float(formatted)

    def _format_limit_price(self, asset_id: int, limit_px: float | Decimal) -> float | Decimal:
        """Format price according to asset's tick size requirements."""
        sz_decimals = self._metadata.resolve_perp_sz_decimals(asset_id)
        if sz_decimals is not None:
            formatted = format_price_for_api(limit_px, sz_decimals, is_perp=True)
            return type(limit_px)(formatted) if isinstance(limit_px, Decimal) else formatted

        base_sz_decimals = self._metadata.resolve_spot_base_sz_decimals(asset_id)
        if base_sz_decimals is not None:
            formatted = format_price_for_api(limit_px, base_sz_decimals, is_perp=False)
            return type(limit_px)(formatted) if isinstance(limit_px, Decimal) else formatted

        return limit_px

    # ------------------------------------------------------------------
    # Metadata and verification helpers
    # ------------------------------------------------------------------
    def _resolve_asset_id(self, asset: str) -> int:
        result = self._metadata.resolve_asset_id(asset)
        self._metadata_loaded = self._metadata.metadata_loaded
        return result

    def _get_json_name_for_chain(self, chain: str = "hyperliquid") -> str:
        """Determine the JSON name based on which chain the operation originates from.

        Args:
            chain: Either "hyperliquid" for operations on HyperEVM or "mainnet" for operations on mainnet
        """
        if self._flexible_proof_resolver and hasattr(self._flexible_proof_resolver, "_datasets"):
            if chain == "mainnet":
                for title in self._flexible_proof_resolver._datasets.keys():
                    if "mainnet" in title.lower() or "ethereum" in title.lower():
                        return title
            elif chain == "hyperliquid":  # hyperliquid chain operations
                for title in self._flexible_proof_resolver._datasets.keys():
                    if "hyperevm" in title.lower() or "hyperliquid" in title.lower():
                        return title
            else:
                raise ValidationError(
                    "Chain must be either 'hyperliquid' or 'mainnet'",
                    field="chain",
                    value=chain,
                )

            datasets = self._flexible_proof_resolver._datasets
            if datasets:
                return next(iter(datasets.keys()))

        # Fallback to a default name
        return "default"

    def _resolve_verification_payload(
        self, proof_desc: str, json_name: str, context: Mapping[str, Any]
    ) -> VerificationPayload:
        if self._call_verification_disabled:
            logger.debug(
                "Call verification disabled; returning default payload for '%s'", proof_desc
            )
            return VerificationPayload.default()

        if self._flexible_proof_resolver:
            return self._flexible_proof_resolver.resolve(proof_desc, json_name, context)

        logger.warning(
            "No flexible vault proof resolver configured; returning default payload for description '%s'",
            proof_desc,
        )
        return VerificationPayload.default()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def _resolve_trader_address(self) -> str:
        try:
            return self._connections.subvault_address
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
        state = self._request_json("POST", self._config.info_url, payload)

        if not isinstance(state, Mapping):
            raise NetworkError(
                "Unexpected response format when fetching user state",
                endpoint=self._config.info_url,
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

    def _request_json(
        self,
        method: str,
        url: str | None,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        if not url:
            raise ValueError("No URL provided for HTTP request")

        url_str = url
        response = self._session.request(
            method,
            url_str,
            json=payload,
            timeout=self._config.request_timeout,
        )
        response.raise_for_status()
        return response.json()

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

    def _send_contract_transaction(
        self,
        function_name: str,
        args: Sequence[Any],
        *,
        action: str,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._dispatcher.send(
            function_name,
            args,
            action=action,
            context=context,
        )

    # ------------------------------------------------------------------
    # Connection-backed properties
    # ------------------------------------------------------------------
    @property
    def account(self) -> LocalAccount:  # type: ignore[override]
        return self._connections.account

    @property
    def strategy_contract(self) -> Contract:
        return self._connections.strategy_contract

    @property
    def hyperliquid_web3(self) -> Web3:
        return self._connections.hyperliquid_web3

    @property
    def mainnet_web3(self) -> Web3:
        return self._connections.mainnet_web3

    @property
    def subvault_address(self) -> ChecksumAddress:
        return self._connections.subvault_address

    @property
    def rpc_url(self) -> str:
        return self._config.hl_rpc_url
