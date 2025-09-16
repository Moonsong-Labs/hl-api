"""Basic usage example for HyperLiquid Unified API."""

import asyncio
import os

from dotenv import load_dotenv

from hl_api import (
    HLProtocolCore,
    generate_cloid,
)

load_dotenv()


async def example_core_trading():
    """Example of trading using HyperLiquid Core SDK."""

    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise ValueError("PRIVATE_KEY not found in environment variables")

    hl_core = HLProtocolCore(
        private_key=private_key,
        testnet=True,
        account_address=os.getenv("ACCOUNT_ADDRESS"),
    )

    await hl_core.connect()

    # Place a limit order
    # Example: Buy 0.001 BTC at $60,000
    cloid = generate_cloid()  # Generate unique client order ID

    response = await hl_core.limit_order(
        asset="BTC",
        is_buy=True,
        limit_px=60000.0,
        sz=0.001,
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

    await hl_core.disconnect()


async def main():
    """Run examples."""
    print("=" * 50)
    print("HyperLiquid API - Example 01")
    print("📈 Place & Cancel Limit Orders")
    print("=" * 50)

    await example_core_trading()


if __name__ == "__main__":
    asyncio.run(main())
