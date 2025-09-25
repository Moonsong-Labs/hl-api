"""HyperLiquid protocol base interface."""

from abc import ABC, abstractmethod

from .types import Response


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
    ) -> Response:
        pass

    @abstractmethod
    def market_close_position(
        self,
        asset: str,
        size: float | None = None,
        slippage: float = 0.005,
        cloid: str | None = None,
    ) -> Response:
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
    ) -> Response:
        pass

    @abstractmethod
    def vault_transfer(self, vault: str, is_deposit: bool, usd: float) -> Response:
        pass

    @abstractmethod
    def spot_send(self, recipient: str, token: str, amount: float, destination: str) -> Response:
        pass

    @abstractmethod
    def perp_send(self, recipient: str, amount: float, destination: str) -> Response:
        pass

    @abstractmethod
    def usd_class_transfer_to_perp(self, amount: float) -> Response:
        pass

    @abstractmethod
    def usd_class_transfer_to_spot(self, amount: float) -> Response:
        pass

    @abstractmethod
    def cancel_order_by_oid(self, asset: str, order_id: int) -> Response:
        pass

    @abstractmethod
    def cancel_order_by_cloid(self, asset: str, cloid: str) -> Response:
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
