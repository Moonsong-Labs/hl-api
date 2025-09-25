"""Abstract base class for HyperLiquid protocol implementations."""

from abc import ABC, abstractmethod

from .types import (
    ApprovalResponse,
    CancelResponse,
    DelegateResponse,
    OrderResponse,
    SendResponse,
    StakingResponse,
    TransferResponse,
)


class HLProtocolBase(ABC):
    """Abstract base class defining the interface for HyperLiquid protocol implementations.

    All methods correspond to CoreWriter precompile actions available at
    address 0x3333333333333333333333333333333333333333 on HyperLiquid EVM.
    """

    @abstractmethod
    def get_market_price(self, asset: str) -> float:
        """Fetch the current market price for an asset.

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")

        Returns:
            Mid price as a float
        """
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
        """Place a market order that executes immediately at the best price.

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            is_buy: True for buy order, False for sell
            sz: Order size as float (e.g., 0.1 for 0.1 BTC)
            slippage: Slippage tolerance expressed as a decimal (e.g., 0.05 = 5%)
            cloid: Client order ID (optional, 0 means no cloid)

        Returns:
            OrderResponse with order details or error
        """
        pass

    @abstractmethod
    def market_close_position(
        self,
        asset: str,
        size: float | None = None,
        slippage: float = 0.005,
        cloid: str | None = None,
    ) -> OrderResponse:
        """Close an open position using a market order.

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            size: Optional position size to close (None closes entire position)
            slippage: Slippage tolerance expressed as a decimal (e.g., 0.005 = 0.5%)
            cloid: Client order ID (optional, 0 means no cloid)

        Returns:
            OrderResponse with order details or error
        """
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
        """Place a limit order (CoreWriter Action ID 1).

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            is_buy: True for buy order, False for sell
            limit_px: Limit price as float (e.g., 65000.0 for $65,000)
            sz: Order size as float (e.g., 0.1 for 0.1 BTC)
            reduce_only: If True, order can only reduce position
            tif: Time in force - "ALO", "GTC", or "IOC"
            cloid: Client order ID (optional, 0 means no cloid)

        Returns:
            OrderResponse with order details or error
        """
        pass

    @abstractmethod
    def vault_transfer(self, vault: str, is_deposit: bool, usd: float) -> TransferResponse:
        """Transfer funds to/from vault (CoreWriter Action ID 2).

        Args:
            vault: Vault address
            is_deposit: True for deposit, False for withdrawal
            usd: Amount in USD as float (e.g., 1000.0 for $1000)

        Returns:
            TransferResponse with transfer details or error
        """
        pass

    @abstractmethod
    def spot_send(
        self, recipient: str, token: str, amount: float, destination: str
    ) -> SendResponse:
        """Send spot tokens (CoreWriter Action ID 6).

        Args:
            recipient: Recipient address
            token: Token identifier
            amount: Amount to send as float
            destination: Destination chain/network

        Returns:
            SendResponse with transfer details or error
        """
        pass

    @abstractmethod
    def perp_send(self, recipient: str, amount: float, destination: str) -> SendResponse:
        """Send perp collateral (CoreWriter Action ID 7).

        Args:
            recipient: Recipient address
            amount: Amount to send as float
            destination: Destination chain/network

        Returns:
            SendResponse with transfer details or error
        """
        pass

    @abstractmethod
    def usd_class_transfer_to_perp(self, amount: float) -> TransferResponse:
        """Transfer USD from spot to perp (CoreWriter Action ID 8).

        Args:
            amount: Amount to transfer as float

        Returns:
            TransferResponse with transfer details or error
        """
        pass

    @abstractmethod
    def usd_class_transfer_to_spot(self, amount: float) -> TransferResponse:
        """Transfer USD from perp to spot (CoreWriter Action ID 9).

        Args:
            amount: Amount to transfer as float

        Returns:
            TransferResponse with transfer details or error
        """
        pass

    @abstractmethod
    def cancel_order_by_oid(self, asset: str, order_id: int) -> CancelResponse:
        """Cancel an order by OID (CoreWriter Action ID 10).

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            order_id: OID (int)

        Returns:
            CancelResponse with cancellation details or error
        """
        pass

    @abstractmethod
    def cancel_order_by_cloid(self, asset: str, cloid: str) -> CancelResponse:
        """Cancel an order by CLOID (CoreWriter Action ID 11).

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            client_order_id: CLOID (hex string starting with 0x)

        Returns:
            CancelResponse with cancellation details or error
        """
        pass

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the protocol.

        Implementation-specific connection logic.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the protocol.

        Implementation-specific disconnection logic.
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected to the protocol.

        Returns:
            True if connected, False otherwise
        """
        pass
