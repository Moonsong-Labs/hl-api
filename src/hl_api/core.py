"""HyperLiquid Core implementation using the official SDK."""

from __future__ import annotations

import logging
from typing import Any

import eth_account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils.types import Cloid

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
from .utils import size_to_uint64

logger = logging.getLogger(__name__)


class HLProtocolCore(HLProtocolBase):
    """HyperLiquid Core implementation using the official Python SDK.

    This implementation connects directly to HyperLiquid Core via the
    official hyperliquid-python-sdk.
    """

    def __init__(
        self,
        private_key: str,
        testnet: bool = True,
        base_url: str | None = None,
        account_address: str | None = None,
    ):
        """Initialize HyperLiquid Core protocol.

        Args:
            private_key: Private key for authentication
            testnet: If True, connect to testnet (default: mainnet)
            base_url: Optional custom API endpoint
        """
        self.private_key = private_key
        self.testnet = testnet
        self.base_url = base_url
        self._exchange: Exchange | None = None
        self._info: Info | None = None
        self._connected = False

        try:
            account = eth_account.Account.from_key(private_key)  # type: ignore[attr-defined]
            self.account_address = account_address if account_address else account.address
        except Exception as e:
            raise AuthenticationError(f"Invalid private key: {e}")

    async def connect(self) -> None:
        """Establish connection to HyperLiquid Core."""
        try:
            from hyperliquid.utils.constants import MAINNET_API_URL, TESTNET_API_URL

            wallet = eth_account.Account.from_key(self.private_key)  # type: ignore[attr-defined]

            # Use testnet URL if testnet is True, otherwise use mainnet or custom URL
            api_url = self.base_url
            if api_url is None:
                api_url = TESTNET_API_URL if self.testnet else MAINNET_API_URL

            self._exchange = Exchange(
                wallet=wallet,
                base_url=api_url,
                account_address=self.account_address,
            )

            self._info = Info(base_url=api_url, skip_ws=True)

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
        asset: str,
        is_buy: bool,
        limit_px: float,
        sz: float,
        reduce_only: bool = False,
        tif: str = "GTC",
        cloid: str | None = None,
    ) -> OrderResponse:
        """Place a limit order via HyperLiquid SDK."""
        if not await self.is_connected():
            await self.connect()

        try:
            order_request: dict[str, Any] = {
                "name": asset,
                "is_buy": is_buy,
                "sz": sz,
                "limit_px": limit_px,
                "order_type": {
                    "limit": {"tif": tif.capitalize()}
                },  # TIF should be capitalized (e.g., "Gtc")
                "reduce_only": reduce_only,
            }

            if cloid:
                order_request["cloid"] = Cloid.from_str(cloid)

            assert self._exchange is not None, (
                "Exchange client unexpectedly None after connection check"
            )

            result = self._exchange.order(**order_request)
            if result["status"] == "err":
                logger.error(f"Order request failed: {result['response']}")

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

    async def cancel_order_by_oid(self, asset: str, order_id: int) -> CancelResponse:
        """Cancel an order by OID.

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            order_id: OID (int)
        """
        if not await self.is_connected():
            await self.connect()

        try:
            assert self._info is not None and self._exchange is not None, (
                "Client unexpectedly None after connection check"
            )

            result = self._exchange.cancel(asset, order_id)
            return CancelResponse(
                success=True,
                cancelled_orders=1,
                raw_response=result,
            )

        except Exception as e:
            logger.error(f"Failed to cancel order by OID: {e}")
            return CancelResponse(success=False, error=str(e))

    async def cancel_order_by_cloid(self, asset: str, cloid: str) -> CancelResponse:
        """Cancel an order by CLOID.

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            cloid: CLOID (hex string starting with 0x)
        """
        if not await self.is_connected():
            await self.connect()

        try:
            assert self._info is not None and self._exchange is not None, (
                "Client unexpectedly None after connection check"
            )

            if not cloid.startswith("0x"):
                return CancelResponse(
                    success=False,
                    error=f"Invalid CLOID format: must start with 0x, got {cloid}",
                )

            # CLOID cancellation - SDK expects Cloid type and asset name directly
            cloid_obj = Cloid(cloid)
            result = self._exchange.cancel_by_cloid(asset, cloid_obj)
            return CancelResponse(
                success=True,
                cancelled_orders=1,
                raw_response=result,
            )

        except Exception as e:
            logger.error(f"Failed to cancel order by CLOID: {e}")
            return CancelResponse(success=False, error=str(e))

    # Backward compatibility - single method that dispatches
    async def cancel_order(self, asset: str, order_id: int | str) -> CancelResponse:
        """Cancel an order by OID or CLOID.

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            order_id: Either an OID (int) or CLOID (hex string starting with 0x)
        """
        if isinstance(order_id, int):
            return await self.cancel_order_by_oid(asset, order_id)
        elif isinstance(order_id, str):
            return await self.cancel_order_by_cloid(asset, order_id)
        else:
            return CancelResponse(
                success=False,
                error=f"Invalid order_id type: must be int (OID) or str (CLOID), got {type(order_id).__name__}",
            )

    async def vault_transfer(self, vault: str, is_deposit: bool, usd: float) -> TransferResponse:
        """Transfer funds to/from vault."""
        if not await self.is_connected():
            await self.connect()

        try:
            # Transfer to/from vault
            assert self._exchange is not None, (
                "Exchange client unexpectedly None after connection check"
            )
            result = self._exchange.vault_usd_transfer(
                vault_address=vault,
                is_deposit=is_deposit,
                usd=size_to_uint64(usd, 6),  # USDC uses 6 decimals
            )

            return TransferResponse(success=True, amount=usd, raw_response=result)

        except Exception as e:
            logger.error(f"Failed vault transfer: {e}")
            return TransferResponse(success=False, error=str(e))

    async def token_delegate(
        self, validator: str, amount: float, is_undelegate: bool = False
    ) -> DelegateResponse:
        """Delegate or undelegate tokens."""
        return DelegateResponse(
            success=False, error="Token delegation not yet implemented for Core SDK"
        )

    async def staking_deposit(self, amount: float) -> StakingResponse:
        """Deposit tokens for staking."""
        return StakingResponse(
            success=False, error="Staking deposit not yet implemented for Core SDK"
        )

    async def staking_withdraw(self, amount: float) -> StakingResponse:
        """Withdraw staked tokens."""
        return StakingResponse(
            success=False, error="Staking withdrawal not yet implemented for Core SDK"
        )

    async def spot_send(
        self, recipient: str, token: str, amount: float, destination: str
    ) -> SendResponse:
        """Send spot tokens."""
        if not await self.is_connected():
            await self.connect()

        try:
            assert self._exchange is not None, (
                "Exchange client unexpectedly None after connection check"
            )
            result = self._exchange.send_asset(
                destination=recipient,
                source_dex="perp",
                destination_dex="perp",
                token=token,
                amount=amount,
            )

            return SendResponse(
                success=True, recipient=recipient, amount=amount, raw_response=result
            )

        except Exception as e:
            logger.error(f"Failed spot send: {e}")
            return SendResponse(success=False, error=str(e))

    async def perp_send(self, recipient: str, amount: float, destination: str) -> SendResponse:
        """Send perp collateral."""
        if not await self.is_connected():
            await self.connect()

        try:
            assert self._exchange is not None, (
                "Exchange client unexpectedly None after connection check"
            )
            result = self._exchange.usd_transfer(
                destination=recipient,
                amount=amount,
            )

            return SendResponse(
                success=True, recipient=recipient, amount=amount, raw_response=result
            )

        except Exception as e:
            logger.error(f"Failed perp send: {e}")
            return SendResponse(success=False, error=str(e))

    async def usd_class_transfer_to_perp(self, amount: float) -> TransferResponse:
        """Transfer USD from spot to perp."""
        if not await self.is_connected():
            await self.connect()

        try:
            # USD class transfer via SDK
            assert self._exchange is not None, (
                "Exchange client unexpectedly None after connection check"
            )
            result = self._exchange.usd_class_transfer(
                amount=amount,
                to_perp=True,
            )

            return TransferResponse(success=True, amount=amount, raw_response=result)

        except Exception as e:
            logger.error(f"Failed USD transfer to perp: {e}")
            return TransferResponse(success=False, error=str(e))

    async def usd_class_transfer_to_spot(self, amount: float) -> TransferResponse:
        """Transfer USD from perp to spot."""
        if not await self.is_connected():
            await self.connect()

        try:
            assert self._exchange is not None, (
                "Exchange client unexpectedly None after connection check"
            )
            print(f"Transferring ${amount} from perp to spot for {self._exchange.account_address}")

            result = self._exchange.usd_class_transfer(
                amount=amount,
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

    async def approve_builder_fee(self, builder: str, fee: float, nonce: int) -> ApprovalResponse:
        """Approve builder fee."""
        if not await self.is_connected():
            await self.connect()

        try:
            # Approve builder fee via SDK
            assert self._exchange is not None, (
                "Exchange client unexpectedly None after connection check"
            )
            result = self._exchange.approve_builder_fee(
                builder=builder,
                max_fee_rate=str(fee),  # SDK expects string, direct float input
                # Note: nonce not directly supported in SDK
            )

            return ApprovalResponse(
                success=True, builder=builder, fee=fee, nonce=nonce, raw_response=result
            )

        except Exception as e:
            logger.error(f"Failed builder fee approval: {e}")
            return ApprovalResponse(success=False, error=str(e))

    async def get_market_price(self, asset: str) -> float:
        """Get current market price for an asset.

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH", "ATOM"). Must be a valid
                   asset available on HyperLiquid.

        Returns:
            Current mid price as float. The price represents the midpoint between
            the best bid and ask prices.

        Raises:
            ValueError: If the asset is not found in market data or if the price
                       is invalid (≤ 0).
            NetworkError: If there's a network error while fetching price data
                         or if the connection to HyperLiquid fails.
        """
        if not await self.is_connected():
            await self.connect()

        try:
            assert self._info is not None, "Info client unexpectedly None after connection check"

            # Get all mid prices from the SDK
            all_mids = self._info.all_mids()

            if asset not in all_mids:
                raise ValueError(f"Asset {asset} not found in market data")

            price = float(all_mids[asset])

            # Validate price
            if price <= 0:
                raise ValueError(f"Invalid price {price} for asset {asset}")

            logger.info(f"Retrieved market price for {asset}: ${price:,.2f}")
            return price

        except ValueError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            logger.error(f"Failed to get market price for {asset}: {e}")
            raise NetworkError(f"Failed to fetch market price: {e}")

    async def market_order(
        self,
        asset: str,
        is_buy: bool,
        sz: float,
        slippage: float = 0.05,
        cloid: str | None = None,
    ) -> OrderResponse:
        """Place a market order with built-in slippage protection.

        This method places a market order using the hyperliquid-python-sdk's market_open()
        function. Market orders execute immediately at the best available price.

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH", "ATOM"). Must be a valid
                   perpetual contract available on HyperLiquid.
            is_buy: Direction of the order. True for buy (long), False for sell (short).
            sz: Order size as a float. Represents the number of units to trade
                (e.g., 0.1 for 0.1 BTC).
            slippage: Maximum acceptable slippage as a decimal (default: 0.05 = 5%).
                     This protects against excessive price movement during execution.
                     Must be between 0 and 1.
            cloid: Optional client order ID as a hex string (e.g., "0x123...").
                   If provided, allows tracking the order with your own identifier.

        Returns:
            OrderResponse

        Raises:
            No exceptions are raised. All errors are captured and returned in the
            OrderResponse.error field.
        """
        if not await self.is_connected():
            await self.connect()

        try:
            assert self._exchange is not None, (
                "Exchange client unexpectedly None after connection check"
            )

            # Prepare cloid if provided
            cloid_obj = None
            if cloid:
                cloid_obj = Cloid.from_str(cloid)

            # Use SDK's market_open method
            result = self._exchange.market_open(
                name=asset, is_buy=is_buy, sz=sz, slippage=slippage, cloid=cloid_obj
            )

            if result.get("status") == "err":
                logger.error(f"Market order request failed: {result['response']}")

            # Extract order info from response
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
            error_msg = str(e)
            logger.error(f"Failed to place market order: {error_msg}")
            return OrderResponse(success=False, cloid=cloid, error=error_msg)

    async def market_close_position(
        self,
        asset: str,
        size: float | None = None,
        slippage: float = 0.05,
        cloid: str | None = None,
    ) -> OrderResponse:
        """Close a position using a market order with slippage protection.

        It can close either the entire position or a
        specific amount, executing immediately at the best available market price.

        The position closing order will execute in the opposite direction of the
        current position.

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH", "ATOM"). Must match an asset
                   for which you have an open position.
            size: Amount to close as a float. If None (default), closes the entire
                  position. If specified, must be positive and not exceed the
                  current position size.
            slippage: Maximum acceptable slippage as a decimal (default: 0.05 = 5%).
                     This protects against excessive price movement during execution.
                     Must be between 0 and 1.
            cloid: Optional client order ID as a hex string (e.g., "0x123...").
                   If provided, allows tracking the order with your own identifier.

        Returns:
            OrderResponse
        """
        if not await self.is_connected():
            await self.connect()

        try:
            assert self._exchange is not None, (
                "Exchange client unexpectedly None after connection check"
            )

            # Prepare cloid if provided
            cloid_obj = None
            if cloid:
                cloid_obj = Cloid.from_str(cloid)

            # Use SDK's market_close method
            result = self._exchange.market_close(
                coin=asset,
                sz=size,  # None means close entire position
                slippage=slippage,
                cloid=cloid_obj,
            )

            if result.get("status") == "err":
                logger.error(f"Market close position request failed: {result['response']}")

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
            error_msg = str(e)
            logger.error(f"Failed to close position: {error_msg}")
            return OrderResponse(success=False, cloid=cloid, error=error_msg)
