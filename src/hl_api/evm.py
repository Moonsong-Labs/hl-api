"""HyperLiquid EVM implementation that routes actions through a strategy contract."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

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
    price_to_uint64,
    size_to_uint64,
    validate_address,
)

logger = logging.getLogger(__name__)

COREWRITER_ADDRESS = "0x3333333333333333333333333333333333333333"

DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_RECEIPT_TIMEOUT = 120.0

VerificationResolver = Callable[[str, Mapping[str, Any]], VerificationPayload | Mapping[str, Any] | None]


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

        self._web3: Web3 | None = None
        self._account: LocalAccount | None = None
        self._strategy_contract: Contract | None = None
        self._chain_id: int | None = None
        self._connected = False

        self._asset_by_symbol: dict[str, int] = {}
        self._token_index_by_symbol: dict[str, int] = {}
        self._hype_token_index: int | None = None

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
            self._connected = True

            logger.info("Connected to HyperLiquid EVM at %s", self.rpc_url)

            try:
                self._hype_token_index = contract.functions.hypeTokenIndex().call()
            except Exception:
                self._hype_token_index = None

        except NetworkError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            self._connected = False
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

    def is_connected(self) -> bool:
        return self._connected and self._web3 is not None and self._strategy_contract is not None

    # ------------------------------------------------------------------
    # Core actions
    # ------------------------------------------------------------------
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
            price_uint = price_to_uint64(limit_px)
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
            tx_result = self._send_contract_transaction(fn_name, args, action="limit_order", context=context)
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
            return OrderResponse(success=False, cloid=cloid, error=str(exc))
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
            return CancelResponse(success=False, error=str(exc))
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
            return CancelResponse(success=False, error=str(exc))
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

            tx_result = self._send_contract_transaction(fn_name, args, action="spot_send", context=context)
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
            return TransferResponse(success=False, error=str(exc))
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
            return TransferResponse(success=False, error=str(exc))
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
        if not self.is_connected() or self._web3 is None or self._account is None or self._strategy_contract is None:
            raise NetworkError("EVM connector is not connected", endpoint=self.rpc_url)

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

    def register_asset_metadata(self, payload: Any) -> None:
        """Register asset metadata from a provided object (dict/list/etc)."""

        self._ingest_asset_metadata(payload)
        if not self._asset_by_symbol and not self._token_index_by_symbol:
            logger.warning("Asset metadata payload did not produce any symbol mappings")

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
            raise NetworkError("Failed to decode JSON response", endpoint=url, details={"error": str(exc)}) from exc

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
        try:
            base_tx = function.build_transaction(
                {
                    "from": self._account.address,
                    "nonce": self._web3.eth.get_transaction_count(self._account.address),
                }
            )

            mutable_tx: dict[str, Any] = dict(base_tx)
            if "chainId" not in mutable_tx:
                mutable_tx["chainId"] = self._chain_id or self._web3.eth.chain_id
            if "gasPrice" not in mutable_tx:
                mutable_tx["gasPrice"] = self._web3.eth.gas_price

            tx_params = cast(TxParams, mutable_tx)
            if "gas" not in mutable_tx:
                gas_estimate = self._web3.eth.estimate_gas(tx_params)
                mutable_tx["gas"] = gas_estimate
                tx_params = cast(TxParams, mutable_tx)

            tx_for_sign: dict[str, Any] = {key: value for key, value in tx_params.items()}
            signed = self._account.sign_transaction(tx_for_sign)
            tx_hash = self._web3.eth.send_raw_transaction(signed.rawTransaction)
            receipt = None
            if self._wait_for_receipt:
                receipt = self._web3.eth.wait_for_transaction_receipt(
                    tx_hash, timeout=self._receipt_timeout
                )

            result = {
                "tx_hash": tx_hash.hex(),
                "action": action,
                "context": dict(context),
                "receipt": self._serialise_receipt(receipt) if receipt is not None else None,
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
        if isinstance(receipt, Sequence) and not isinstance(receipt, str | bytes | bytearray | HexBytes):
            return [self._serialise_receipt(item) for item in receipt]
        if isinstance(receipt, bytes | bytearray | HexBytes):
            return HexBytes(receipt).hex()
        return receipt
