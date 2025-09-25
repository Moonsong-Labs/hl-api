"""HyperLiquid Core implementation using the official SDK."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info

from hyperliquid.utils.types import Cloid

from ..base import HLProtocolBase
from ..exceptions import AuthenticationError, NetworkError
from ..types import (
    CancelResponse,
    OrderResponse,
    SendResponse,
    TransferResponse,
)
from ..utils import size_to_uint64
from .config import CoreClientConfig
from .connections import CoreConnections

logger = logging.getLogger(__name__)


class HLProtocolCore(HLProtocolBase):
    """HyperLiquid Core implementation using the official Python SDK."""

    def __init__(
        self,
        private_key: str,
        testnet: bool = True,
        base_url: str | None = None,
        account_address: str | None = None,
        *,
        skip_ws: bool = True,
    ) -> None:
        self._config = CoreClientConfig(
            private_key=private_key,
            testnet=testnet,
            base_url=base_url,
            account_address=account_address,
            skip_ws=skip_ws,
        )
        self._connections = CoreConnections(self._config)

        self.private_key = private_key
        self.testnet = testnet
        self.base_url = base_url
        self.account_address = account_address
        self._exchange: Exchange | None = None
        self._info: Info | None = None
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> None:
        try:
            self._connections.connect()
            self._connected = True
            self._exchange = self._connections.exchange
            self._info = self._connections.info
            self.account_address = self._connections.wallet_address
        except AuthenticationError:
            self.disconnect()
            raise
        except NetworkError:
            self.disconnect()
            raise

    def disconnect(self) -> None:
        self._connections.disconnect()
        self._connected = False
        self._exchange = None
        self._info = None

    def is_connected(self) -> bool:
        return self._connections.is_connected()

    def _ensure_connected(self) -> None:
        self._connections.ensure_connected()

    # ------------------------------------------------------------------
    # Order placement
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
        self._ensure_connected()

        try:
            order_request: dict[str, Any] = {
                "name": asset,
                "is_buy": is_buy,
                "sz": sz,
                "limit_px": limit_px,
                "order_type": {"limit": {"tif": tif.capitalize()}},
                "reduce_only": reduce_only,
            }

            if cloid:
                order_request["cloid"] = Cloid.from_str(cloid)

            result = self._connections.exchange.order(**order_request)
            if result["status"] == "err":
                logger.error("Order request failed: %s", result["response"])

            return OrderResponse(
                success=True,
                order_id=result.get("response", {})
                .get("data", {})
                .get("statuses", [{}])[0]
                .get("resting", {})
                .get("oid"),
                cloid=cloid,
                raw_response=result,
            )

        except Exception as exc:
            logger.error("Failed to place limit order: %s", exc)
            return OrderResponse(success=False, cloid=cloid, error=str(exc))

    def get_market_price(self, asset: str) -> float:
        self._ensure_connected()

        try:
            info = self._connections.info
            data = info.all_mids()
            asset_upper = asset.upper()
            if asset_upper not in data:
                raise ValueError(f"Asset '{asset}' not found in market data")
            return float(data[asset_upper])
        except Exception as exc:
            raise NetworkError(f"Failed to fetch market price for {asset}: {exc}") from exc

    def market_order(
        self,
        asset: str,
        is_buy: bool,
        sz: float,
        slippage: float = 0.05,
        cloid: str | None = None,
    ) -> OrderResponse:
        self._ensure_connected()

        try:
            exchange = self._connections.exchange

            cloid_obj = Cloid.from_str(cloid) if cloid else None

            result = exchange.market_open(
                name=asset,
                is_buy=is_buy,
                sz=sz,
                slippage=slippage,
                cloid=cloid_obj,
            )

            if result.get("status") == "err":
                logger.error("Market order request failed: %s", result["response"])

            return OrderResponse(
                success=True,
                order_id=result.get("response", {})
                .get("data", {})
                .get("statuses", [{}])[0]
                .get("resting", {})
                .get("oid"),
                cloid=cloid,
                raw_response=result,
            )

        except Exception as exc:
            error_msg = str(exc)
            logger.error("Failed to place market order: %s", error_msg)
            return OrderResponse(success=False, cloid=cloid, error=error_msg)

    def market_close_position(
        self,
        asset: str,
        size: float | None = None,
        slippage: float = 0.005,
        cloid: str | None = None,
    ) -> OrderResponse:
        self._ensure_connected()

        try:
            exchange = self._connections.exchange

            cloid_obj = Cloid.from_str(cloid) if cloid else None

            result = exchange.market_close(
                coin=asset,
                sz=size,
                slippage=slippage,
                cloid=cloid_obj,
            )

            if result.get("status") == "err":
                logger.error("Market close position request failed: %s", result["response"])

            return OrderResponse(
                success=True,
                order_id=result.get("response", {})
                .get("data", {})
                .get("statuses", [{}])[0]
                .get("resting", {})
                .get("oid"),
                cloid=cloid,
                raw_response=result,
            )

        except Exception as exc:
            error_msg = str(exc)
            logger.error("Failed to close position: %s", error_msg)
            return OrderResponse(success=False, cloid=cloid, error=error_msg)

    # ------------------------------------------------------------------
    # Cancellations
    # ------------------------------------------------------------------
    def cancel_order_by_oid(self, asset: str, order_id: int) -> CancelResponse:
        self._ensure_connected()

        try:
            result = self._connections.exchange.cancel(asset, order_id)
            return CancelResponse(success=True, cancelled_orders=1, raw_response=result)
        except Exception as exc:
            logger.error("Failed to cancel order by OID: %s", exc)
            return CancelResponse(success=False, error=str(exc))

    def cancel_order_by_cloid(self, asset: str, cloid: str) -> CancelResponse:
        self._ensure_connected()

        if not cloid.startswith("0x"):
            return CancelResponse(
                success=False,
                error=f"Invalid CLOID format: must start with 0x, got {cloid}",
            )

        try:
            result = self._connections.exchange.cancel_by_cloid(asset, Cloid(cloid))
            return CancelResponse(success=True, cancelled_orders=1, raw_response=result)
        except Exception as exc:
            logger.error("Failed to cancel order by CLOID: %s", exc)
            return CancelResponse(success=False, error=str(exc))

    def cancel_order(self, asset: str, order_id: int | str) -> CancelResponse:
        if isinstance(order_id, int):
            return self.cancel_order_by_oid(asset, order_id)
        if isinstance(order_id, str):
            return self.cancel_order_by_cloid(asset, order_id)
        return CancelResponse(
            success=False,
            error=f"Invalid order_id type: {type(order_id).__name__}",
        )

    # ------------------------------------------------------------------
    # Transfers
    # ------------------------------------------------------------------
    def vault_transfer(self, vault: str, is_deposit: bool, usd: float) -> TransferResponse:
        self._ensure_connected()

        try:
            result = self._connections.exchange.vault_usd_transfer(
                vault_address=vault,
                is_deposit=is_deposit,
                usd=size_to_uint64(usd, 6),
            )
            return TransferResponse(success=True, amount=usd, raw_response=result)
        except Exception as exc:
            logger.error("Failed vault transfer: %s", exc)
            return TransferResponse(success=False, error=str(exc))

    def usd_class_transfer_to_perp(self, amount: float) -> TransferResponse:
        self._ensure_connected()

        try:
            result = self._connections.exchange.usd_class_transfer(amount=amount, to_perp=True)
            return TransferResponse(success=True, amount=amount, raw_response=result)
        except Exception as exc:
            logger.error("Failed USD transfer to perp: %s", exc)
            return TransferResponse(success=False, error=str(exc))

    def usd_class_transfer_to_spot(self, amount: float) -> TransferResponse:
        self._ensure_connected()

        try:
            result = self._connections.exchange.usd_class_transfer(amount=amount, to_perp=False)
            return TransferResponse(success=True, amount=amount, raw_response=result)
        except Exception as exc:
            logger.error("Failed USD transfer to spot: %s", exc)
            return TransferResponse(success=False, error=str(exc))

    def spot_send(
        self, recipient: str, token: str, amount: float, destination: str
    ) -> SendResponse:
        self._ensure_connected()

        try:
            result = self._connections.exchange.send_asset(
                destination=recipient,
                source_dex="perp",
                destination_dex="perp",
                token=token,
                amount=amount,
            )
            return SendResponse(
                success=True, recipient=recipient, amount=amount, raw_response=result
            )
        except Exception as exc:
            logger.error("Failed spot send: %s", exc)
            return SendResponse(success=False, error=str(exc))

    def perp_send(self, recipient: str, amount: float, destination: str) -> SendResponse:
        self._ensure_connected()

        try:
            result = self._connections.exchange.usd_transfer(destination=recipient, amount=amount)
            return SendResponse(
                success=True, recipient=recipient, amount=amount, raw_response=result
            )
        except Exception as exc:
            logger.error("Failed perp send: %s", exc)
            return SendResponse(success=False, error=str(exc))
