"""Basic usage example for HyperLiquid Unified API."""

import asyncio
import os

from dotenv import load_dotenv

from hl_api import (
    HLProtocolCore,
    generate_cloid,
    price_to_uint64,
    size_to_uint64,
)

# Load environment variables from .env file
load_dotenv()


async def example_core_trading():
    """Example of trading using HyperLiquid Core SDK."""

    # Get credentials from environment variables
    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise ValueError("PRIVATE_KEY not found in environment variables")

    # Initialize Core protocol
    hl_core = HLProtocolCore(
        private_key=private_key,
        testnet=True,  # Use testnet for testing
        account_address=os.getenv("ACCOUNT_ADDRESS"),
    )

    # Connect to HyperLiquid
    await hl_core.connect()

    # Place a limit order
    # Example: Buy 0.001 BTC at $60,000
    price_uint64 = price_to_uint64(60000)  # Convert price to uint64
    size_uint64 = size_to_uint64(0.001)  # Convert size to uint64
    cloid = generate_cloid()  # Generate unique client order ID

    response = await hl_core.limit_order(
        asset="FARTCOIN",
        is_buy=True,
        limit_px=price_uint64,
        sz=size_uint64,
        reduce_only=False,
        tif="GTC",
        cloid=cloid,
    )

    if response.success:
        print("Order placed successfully!")
        print(f"Order ID: {response.order_id}")
        print(f"Client Order ID: {response.cloid}")
    else:
        print(f"Order failed: {response.error}")

    # Cancel the order
    # If you have an OID (integer), use it directly:
    # cancel_response = await hl_core.cancel_order(asset="BTC", order_id=12345)
    # If you have a CLOID (hex string), use it:
    cancel_response = await hl_core.cancel_order(asset="BTC", order_id=cloid)

    if cancel_response.success:
        print("Order cancelled successfully!")
    else:
        print(f"Cancel failed: {cancel_response.error}")

    # Transfer USD between perp and spot
    transfer_amount = price_to_uint64(100)  # $100

    transfer_response = await hl_core.usd_class_transfer_to_spot(amount=transfer_amount)

    if transfer_response.success:
        print(f"Transferred ${100} to spot account")
    else:
        print(f"Transfer failed: {transfer_response.error}")

    # Disconnect
    await hl_core.disconnect()


async def main():
    """Run examples."""
    print("=" * 50)
    print("HyperLiquid Unified API Examples")
    print("=" * 50)

    await example_core_trading()


if __name__ == "__main__":
    asyncio.run(main())
