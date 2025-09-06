"""Abstract base class for HyperLiquid protocol implementations."""

from abc import ABC, abstractmethod

from .types import (
    ApprovalResponse,
    CancelResponse,
    DelegateResponse,
    FinalizeResponse,
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
    async def limit_order(
        self,
        asset: int,
        is_buy: bool,
        limit_px: int,
        sz: int,
        reduce_only: bool = False,
        tif: str = "GTC",
        cloid: int | None = None,
    ) -> OrderResponse:
        """Place a limit order (CoreWriter Action ID 1).

        Args:
            asset: Asset index (e.g., 0 for BTC-PERP)
            is_buy: True for buy order, False for sell
            limit_px: Limit price as uint64
            sz: Order size as uint64
            reduce_only: If True, order can only reduce position
            tif: Time in force - "ALO", "GTC", or "IOC"
            cloid: Client order ID (optional, 0 means no cloid)

        Returns:
            OrderResponse with order details or error
        """
        pass

    @abstractmethod
    async def vault_transfer(self, vault: str, is_deposit: bool, usd: int) -> TransferResponse:
        """Transfer funds to/from vault (CoreWriter Action ID 2).

        Args:
            vault: Vault address
            is_deposit: True for deposit, False for withdrawal
            usd: Amount in USD as uint64

        Returns:
            TransferResponse with transfer details or error
        """
        pass

    @abstractmethod
    async def token_delegate(
        self, validator: str, wei: int, is_undelegate: bool = False
    ) -> DelegateResponse:
        """Delegate or undelegate tokens (CoreWriter Action ID 3).

        Args:
            validator: Validator address
            wei: Amount in wei as uint64
            is_undelegate: True to undelegate, False to delegate

        Returns:
            DelegateResponse with delegation details or error
        """
        pass

    @abstractmethod
    async def staking_deposit(self, wei: int) -> StakingResponse:
        """Deposit tokens for staking (CoreWriter Action ID 4).

        Args:
            wei: Amount to stake in wei as uint64

        Returns:
            StakingResponse with staking details or error
        """
        pass

    @abstractmethod
    async def staking_withdraw(self, wei: int) -> StakingResponse:
        """Withdraw staked tokens (CoreWriter Action ID 5).

        Args:
            wei: Amount to withdraw in wei as uint64

        Returns:
            StakingResponse with withdrawal details or error
        """
        pass

    @abstractmethod
    async def spot_send(
        self, recipient: str, token: str, amount: int, destination: str
    ) -> SendResponse:
        """Send spot tokens (CoreWriter Action ID 6).

        Args:
            recipient: Recipient address
            token: Token identifier
            amount: Amount to send as uint64
            destination: Destination chain/network

        Returns:
            SendResponse with transfer details or error
        """
        pass

    @abstractmethod
    async def perp_send(self, recipient: str, amount: int, destination: str) -> SendResponse:
        """Send perp collateral (CoreWriter Action ID 7).

        Args:
            recipient: Recipient address
            amount: Amount to send as uint64
            destination: Destination chain/network

        Returns:
            SendResponse with transfer details or error
        """
        pass

    @abstractmethod
    async def usd_class_transfer_to_perp(self, amount: int) -> TransferResponse:
        """Transfer USD from spot to perp (CoreWriter Action ID 8).

        Args:
            amount: Amount to transfer as uint64

        Returns:
            TransferResponse with transfer details or error
        """
        pass

    @abstractmethod
    async def usd_class_transfer_to_spot(self, amount: int) -> TransferResponse:
        """Transfer USD from perp to spot (CoreWriter Action ID 9).

        Args:
            amount: Amount to transfer as uint64

        Returns:
            TransferResponse with transfer details or error
        """
        pass

    @abstractmethod
    async def cancel_order(self, asset: int, cloid: int) -> CancelResponse:
        """Cancel an order by cloid (CoreWriter Action ID 10).

        Args:
            asset: Asset index
            cloid: Client order ID to cancel

        Returns:
            CancelResponse with cancellation details or error
        """
        pass

    @abstractmethod
    async def finalize_subaccount(self, subaccount: str) -> FinalizeResponse:
        """Finalize a subaccount (CoreWriter Action ID 11).

        Args:
            subaccount: Subaccount address to finalize

        Returns:
            FinalizeResponse with finalization details or error
        """
        pass

    @abstractmethod
    async def approve_builder_fee(self, builder: str, fee: int, nonce: int) -> ApprovalResponse:
        """Approve builder fee (CoreWriter Action ID 12).

        Args:
            builder: Builder address
            fee: Fee amount as uint64
            nonce: Nonce for the approval

        Returns:
            ApprovalResponse with approval details or error
        """
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the protocol.

        Implementation-specific connection logic.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the protocol.

        Implementation-specific disconnection logic.
        """
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if connected to the protocol.

        Returns:
            True if connected, False otherwise
        """
        pass
