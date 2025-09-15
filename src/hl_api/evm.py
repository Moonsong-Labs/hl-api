"""HyperLiquid EVM implementation for CoreWriter precompile interaction."""

import logging
from typing import Any

from web3 import Web3

from .base import HLProtocolBase
from .types import (
    ActionID,
    ApprovalResponse,
    CancelResponse,
    DelegateResponse,
    FinalizeResponse,
    OrderResponse,
    SendResponse,
    StakingResponse,
    TransferResponse,
)
from .utils import price_to_uint64, size_to_uint64

logger = logging.getLogger(__name__)

# CoreWriter precompile address on HyperLiquid EVM
COREWRITER_ADDRESS = "0x3333333333333333333333333333333333333333"


class HLProtocolEVM(HLProtocolBase):
    """HyperLiquid EVM implementation for CoreWriter precompile interaction.

    This implementation connects to HyperLiquid EVM and interacts with
    the CoreWriter precompile at address 0x3333333333333333333333333333333333333333.

    Note: This is a stub implementation. Full implementation requires
    deployed smart contracts and web3.py integration.
    """

    def __init__(
        self,
        private_key: str,
        rpc_url: str,
        contract_address: str | None = None,
        gas_price_strategy: str | None = None,
    ):
        """Initialize HyperLiquid EVM protocol.

        Args:
            private_key: Private key for signing transactions
            rpc_url: RPC endpoint URL for HyperLiquid EVM
            contract_address: Optional custom CoreWriter address (defaults to 0x3333...)
            gas_price_strategy: Optional gas price strategy
        """
        self.private_key = private_key
        self.rpc_url = rpc_url
        self.contract_address = contract_address or COREWRITER_ADDRESS
        self.gas_price_strategy = gas_price_strategy

        self._web3: Web3 | None = None
        self._account = None
        self._connected = False

    async def connect(self) -> None:
        """Establish connection to HyperLiquid EVM."""
        raise NotImplementedError("EVM connect not yet implemented")

    async def disconnect(self) -> None:
        """Close connection to HyperLiquid EVM."""
        raise NotImplementedError("EVM disconnect not yet implemented")

    async def is_connected(self) -> bool:
        """Check if connected to HyperLiquid EVM."""
        raise NotImplementedError("EVM is_connected not yet implemented")

    def _encode_action(self, action_id: ActionID, params: bytes) -> bytes:
        """Encode an action for CoreWriter precompile.

        Args:
            action_id: The CoreWriter action ID
            params: Encoded parameters for the action

        Returns:
            Encoded action data
        """
        raise NotImplementedError("EVM _encode_action not yet implemented")

    async def _send_transaction(self, action_data: bytes) -> dict[str, Any]:
        """Send a transaction to CoreWriter precompile.

        Args:
            action_data: Encoded action data

        Returns:
            Transaction receipt
        """
        raise NotImplementedError("EVM _send_transaction not yet implemented")

    async def limit_order(
        self,
        asset: str,
        is_buy: bool,
        limit_px: float,
        sz: float,
        reduce_only: bool = False,
        tif: str = "GTC",
        cloid: str | None = None,
    ) -> OrderResponse:
        """Place a limit order via CoreWriter precompile."""
        _limit_px_uint64 = price_to_uint64(limit_px)
        _sz_uint64 = size_to_uint64(sz)
        # TODO: Implement CoreWriter precompile interaction with uint64 values (_limit_px_uint64, _sz_uint64)
        raise NotImplementedError("EVM limit_order not yet implemented")

    async def cancel_order_by_oid(self, asset: str, order_id: int) -> CancelResponse:
        """Cancel an order by OID via CoreWriter precompile."""
        raise NotImplementedError("EVM cancel_order_by_oid not yet implemented")

    async def cancel_order_by_cloid(self, asset: str, cloid: str) -> CancelResponse:
        """Cancel an order by CLOID via CoreWriter precompile."""
        raise NotImplementedError("EVM cancel_order_by_cloid not yet implemented")

    async def vault_transfer(self, vault: str, is_deposit: bool, usd: float) -> TransferResponse:
        """Transfer funds to/from vault via CoreWriter precompile."""
        _usd_uint64 = size_to_uint64(usd)  # USD amount, use size conversion
        # TODO: Implement CoreWriter precompile interaction with uint64 value (_usd_uint64)
        raise NotImplementedError("EVM vault_transfer not yet implemented")

    async def token_delegate(
        self, validator: str, amount: float, is_undelegate: bool = False
    ) -> DelegateResponse:
        """Delegate tokens via CoreWriter precompile."""
        _amount_uint64 = size_to_uint64(amount)
        # TODO: Implement CoreWriter precompile interaction with uint64 value (_amount_uint64)
        raise NotImplementedError("EVM token_delegate not yet implemented")

    async def staking_deposit(self, amount: float) -> StakingResponse:
        """Deposit for staking via CoreWriter precompile."""
        _amount_uint64 = size_to_uint64(amount)  # USD amount for staking, use size conversion
        # TODO: Implement CoreWriter precompile interaction with uint64 value (_amount_uint64)
        raise NotImplementedError("EVM staking_deposit not yet implemented")

    async def staking_withdraw(self, amount: float) -> StakingResponse:
        """Withdraw from staking via CoreWriter precompile."""
        _amount_uint64 = size_to_uint64(amount)  # USD amount for staking, use size conversion
        # TODO: Implement CoreWriter precompile interaction with uint64 value (_amount_uint64)
        raise NotImplementedError("EVM staking_withdraw not yet implemented")

    async def spot_send(
        self, recipient: str, token: str, amount: float, destination: str
    ) -> SendResponse:
        """Send spot tokens via CoreWriter precompile."""
        _amount_uint64 = size_to_uint64(amount)
        # TODO: Implement CoreWriter precompile interaction with uint64 value (_amount_uint64)
        raise NotImplementedError("EVM spot_send not yet implemented")

    async def perp_send(self, recipient: str, amount: float, destination: str) -> SendResponse:
        """Send perp collateral via CoreWriter precompile."""
        _amount_uint64 = size_to_uint64(amount)  # USD collateral amount, use size conversion
        # TODO: Implement CoreWriter precompile interaction with uint64 value (_amount_uint64)
        raise NotImplementedError("EVM perp_send not yet implemented")

    async def usd_class_transfer_to_perp(self, amount: float) -> TransferResponse:
        """Transfer USD to perp via CoreWriter precompile."""
        _amount_uint64 = size_to_uint64(amount)  # USD amount, use size conversion
        # TODO: Implement CoreWriter precompile interaction with uint64 value (_amount_uint64)
        raise NotImplementedError("EVM usd_class_transfer_to_perp not yet implemented")

    async def usd_class_transfer_to_spot(self, amount: float) -> TransferResponse:
        """Transfer USD to spot via CoreWriter precompile."""
        _amount_uint64 = size_to_uint64(amount)  # USD amount, use size conversion
        # TODO: Implement CoreWriter precompile interaction with uint64 value (_amount_uint64)
        raise NotImplementedError("EVM usd_class_transfer_to_spot not yet implemented")

    async def finalize_subaccount(self, subaccount: str) -> FinalizeResponse:
        """Finalize subaccount via CoreWriter precompile."""
        raise NotImplementedError("EVM finalize_subaccount not yet implemented")

    async def approve_builder_fee(self, builder: str, fee: float, nonce: int) -> ApprovalResponse:
        """Approve builder fee via CoreWriter precompile."""
        _fee_uint64 = size_to_uint64(fee)  # Fee amount, use size conversion
        # TODO: Implement CoreWriter precompile interaction with uint64 value (_fee_uint64)
        raise NotImplementedError("EVM approve_builder_fee not yet implemented")
