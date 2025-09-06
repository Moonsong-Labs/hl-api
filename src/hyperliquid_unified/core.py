"""HyperLiquid Core implementation using the official SDK."""

import logging

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from .base import HLProtocolBase
from .exceptions import (
    AuthenticationError,
    NetworkError,
)
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

logger = logging.getLogger(__name__)


class HLProtocolCore(HLProtocolBase):
    """HyperLiquid Core implementation using the official Python SDK.

    This implementation connects directly to HyperLiquid Core via the
    official hyperliquid-python-sdk.
    """

    def __init__(self, private_key: str, testnet: bool = False, base_url: str | None = None):
        """Initialize HyperLiquid Core protocol.

        Args:
            private_key: Private key for authentication
            testnet: If True, connect to testnet (default: mainnet)
            base_url: Optional custom API endpoint
        """
        self.private_key = private_key
        self.testnet = testnet
        self.base_url = base_url

        # Initialize SDK components
        self._exchange: Exchange | None = None
        self._info: Info | None = None
        self._connected = False

        # Derive address from private key
        try:
            account = Account.from_key(private_key)
            self.address = account.address
        except Exception as e:
            raise AuthenticationError(f"Invalid private key: {e}")

    async def connect(self) -> None:
        """Establish connection to HyperLiquid Core."""
        try:
            # Create wallet from private key
            wallet = Account.from_key(self.private_key)

            # Initialize the Exchange and Info clients
            self._exchange = Exchange(wallet=wallet, base_url=self.base_url)

            self._info = Info(base_url=self.base_url)

            self._connected = True
            logger.info(f"Connected to HyperLiquid {'testnet' if self.testnet else 'mainnet'}")

        except Exception as e:
            self._connected = False
            raise NetworkError(f"Failed to connect to HyperLiquid: {e}")

    async def disconnect(self) -> None:
        """Close connection to HyperLiquid Core."""
        self._exchange = None
        self._info = None
        self._connected = False
        logger.info("Disconnected from HyperLiquid")

    async def is_connected(self) -> bool:
        """Check if connected to HyperLiquid Core."""
        return self._connected and self._exchange is not None

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
        """Place a limit order via HyperLiquid SDK."""
        if not await self.is_connected():
            await self.connect()

        try:
            # Convert parameters to SDK format
            # Note: SDK expects different format than our uint64 representation
            # This is a simplified implementation - production would need proper conversion

            order_request = {
                "coin": asset,  # Asset index to coin symbol mapping needed
                "is_buy": is_buy,
                "sz": sz / 1e8,  # Convert from uint64 to float
                "limit_px": limit_px / 1e8,  # Convert from uint64 to float
                "order_type": {"limit": {"tif": tif.lower()}},
                "reduce_only": reduce_only,
            }

            if cloid:
                order_request["cloid"] = str(cloid)

            # Place order via SDK
            result = self._exchange.order(**order_request)

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

        except Exception as e:
            logger.error(f"Failed to place limit order: {e}")
            return OrderResponse(success=False, cloid=cloid, error=str(e))

    async def cancel_order(self, asset: int, cloid: int) -> CancelResponse:
        """Cancel an order by cloid."""
        if not await self.is_connected():
            await self.connect()

        try:
            # Cancel order via SDK - needs name and oid
            # Note: SDK uses (name, oid) not (asset, cloid) for cancellation
            # This is a limitation - we'd need to track oid from order placement
            # For now, return error
            return CancelResponse(
                success=False,
                error="Cancel by cloid not supported in SDK - requires oid",
            )

        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return CancelResponse(success=False, error=str(e))

    async def vault_transfer(self, vault: str, is_deposit: bool, usd: int) -> TransferResponse:
        """Transfer funds to/from vault."""
        if not await self.is_connected():
            await self.connect()

        try:
            # Transfer to/from vault
            result = self._exchange.vault_usd_transfer(
                vault_address=vault,
                is_deposit=is_deposit,
                usd=int(usd / 1e8),  # Convert from uint64 to int
            )

            return TransferResponse(success=True, amount=usd, raw_response=result)

        except Exception as e:
            logger.error(f"Failed vault transfer: {e}")
            return TransferResponse(success=False, error=str(e))

    async def token_delegate(
        self, validator: str, wei: int, is_undelegate: bool = False
    ) -> DelegateResponse:
        """Delegate or undelegate tokens."""
        # Token delegation not directly supported in SDK
        # Would need custom implementation
        return DelegateResponse(
            success=False, error="Token delegation not yet implemented for Core SDK"
        )

    async def staking_deposit(self, wei: int) -> StakingResponse:
        """Deposit tokens for staking."""
        # Staking not directly supported in current SDK
        return StakingResponse(
            success=False, error="Staking deposit not yet implemented for Core SDK"
        )

    async def staking_withdraw(self, wei: int) -> StakingResponse:
        """Withdraw staked tokens."""
        # Staking not directly supported in current SDK
        return StakingResponse(
            success=False, error="Staking withdrawal not yet implemented for Core SDK"
        )

    async def spot_send(
        self, recipient: str, token: str, amount: int, destination: str
    ) -> SendResponse:
        """Send spot tokens."""
        if not await self.is_connected():
            await self.connect()

        try:
            # Send spot tokens via SDK
            # Note: send_asset requires source_dex and destination_dex
            # We'll use "perp" as default for both as it's the main dex
            result = self._exchange.send_asset(
                destination=recipient,
                source_dex="perp",
                destination_dex="perp",
                token=token,
                amount=amount / 1e8,  # Convert from uint64 to float
            )

            return SendResponse(
                success=True, recipient=recipient, amount=amount, raw_response=result
            )

        except Exception as e:
            logger.error(f"Failed spot send: {e}")
            return SendResponse(success=False, error=str(e))

    async def perp_send(self, recipient: str, amount: int, destination: str) -> SendResponse:
        """Send perp collateral."""
        if not await self.is_connected():
            await self.connect()

        try:
            # Send perp collateral via SDK - using usd_transfer
            result = self._exchange.usd_transfer(
                destination=recipient,
                amount=amount / 1e8,  # Convert from uint64
                # Note: destination chain parameter not directly supported
            )

            return SendResponse(
                success=True, recipient=recipient, amount=amount, raw_response=result
            )

        except Exception as e:
            logger.error(f"Failed perp send: {e}")
            return SendResponse(success=False, error=str(e))

    async def usd_class_transfer_to_perp(self, amount: int) -> TransferResponse:
        """Transfer USD from spot to perp."""
        if not await self.is_connected():
            await self.connect()

        try:
            # USD class transfer via SDK
            result = self._exchange.usd_class_transfer(
                amount=amount / 1e8,  # Convert from uint64
                to_perp=True,
            )

            return TransferResponse(success=True, amount=amount, raw_response=result)

        except Exception as e:
            logger.error(f"Failed USD transfer to perp: {e}")
            return TransferResponse(success=False, error=str(e))

    async def usd_class_transfer_to_spot(self, amount: int) -> TransferResponse:
        """Transfer USD from perp to spot."""
        if not await self.is_connected():
            await self.connect()

        try:
            # USD class transfer via SDK
            result = self._exchange.usd_class_transfer(
                amount=amount / 1e8,  # Convert from uint64
                to_perp=False,
            )

            return TransferResponse(success=True, amount=amount, raw_response=result)

        except Exception as e:
            logger.error(f"Failed USD transfer to spot: {e}")
            return TransferResponse(success=False, error=str(e))

    async def finalize_subaccount(self, subaccount: str) -> FinalizeResponse:
        """Finalize a subaccount."""
        # Subaccount finalization not in current SDK
        return FinalizeResponse(
            success=False, error="Subaccount finalization not yet implemented for Core SDK"
        )

    async def approve_builder_fee(self, builder: str, fee: int, nonce: int) -> ApprovalResponse:
        """Approve builder fee."""
        if not await self.is_connected():
            await self.connect()

        try:
            # Approve builder fee via SDK
            result = self._exchange.approve_builder_fee(
                builder=builder,
                max_fee_rate=str(fee / 1e8),  # SDK expects string for fee rate
                # Note: nonce not directly supported in SDK
            )

            return ApprovalResponse(
                success=True, builder=builder, fee=fee, nonce=nonce, raw_response=result
            )

        except Exception as e:
            logger.error(f"Failed builder fee approval: {e}")
            return ApprovalResponse(success=False, error=str(e))
