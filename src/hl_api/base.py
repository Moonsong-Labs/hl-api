"""HyperLiquid protocol base interface."""

from abc import ABC, abstractmethod

from .types import (
    CancelResponse,
    OrderResponse,
    SendResponse,
    TransferResponse,
)


class HLProtocolBase(ABC):
    """HyperLiquid protocol interface."""

    @abstractmethod
    def get_market_price(self, asset: str) -> float:
        pass

    @abstractmethod
    def market_order(
        self,
        asset: str,
        is_buy: bool,
        sz: float,
        slippage: float = 0.05,
        cloid: str | None = None,
    ) -> OrderResponse:
        pass

    @abstractmethod
    def market_close_position(
        self,
        asset: str,
        size: float | None = None,
        slippage: float = 0.005,
        cloid: str | None = None,
    ) -> OrderResponse:
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def vault_transfer(self, vault: str, is_deposit: bool, usd: float) -> TransferResponse:
        pass

    @abstractmethod
    def spot_send(
        self, recipient: str, token: str, amount: float, destination: str
    ) -> SendResponse:
        pass

    @abstractmethod
    def perp_send(self, recipient: str, amount: float, destination: str) -> SendResponse:
        pass

    @abstractmethod
    def usd_class_transfer_to_perp(self, amount: float) -> TransferResponse:
        pass

    @abstractmethod
    def usd_class_transfer_to_spot(self, amount: float) -> TransferResponse:
        pass

    @abstractmethod
    def cancel_order_by_oid(self, asset: str, order_id: int) -> CancelResponse:
        pass

    @abstractmethod
    def cancel_order_by_cloid(self, asset: str, cloid: str) -> CancelResponse:
        pass

    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass
