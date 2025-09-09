"""Market Order Example for HyperLiquid Unified API.

This example demonstrates how to execute aggressive market orders using IOC (Immediate or Cancel)
orders with slippage protection and calculation.
"""

import asyncio
import os

from dotenv import load_dotenv

from hl_api import (
    HLProtocolCore,
    generate_cloid,
)

# Load environment variables from .env file
load_dotenv()

def calculate_slippage_price(
    market_price: float,
    is_buy: bool,
    max_slippage_percent: float
) -> float:
    if is_buy:
        return market_price * (100 + max_slippage_percent) / 100
    else:
        return market_price * (100 - max_slippage_percent) / 100

async def example_market_orders():
    """Demonstrate various market order scenarios."""

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

    cloid = generate_cloid()  # Generate unique client order ID

    market_price = 125000.0

    # Calculate the limit price with slippage protection
    limit_price_with_slippage = calculate_slippage_price(
        market_price=market_price,
        is_buy=True,
        max_slippage_percent=0.5
    )

    print(f"Market price:        ${market_price}")
    print(f"Price with slippage: ${limit_price_with_slippage}")

    # Execute the aggressive IOC order
    response = await hl_core.limit_order(
        asset="BTC",
        is_buy=True,
        limit_px=limit_price_with_slippage,
        sz=0.0001,
        reduce_only=False,
        tif="IOC",  # Immediate or Cancel - behaves like a market order with price protection
        cloid=cloid,
    )

    if response.success:
        print("Market order placed successfully!")
        print(f"Order ID: {response.order_id}")
        print(f"Client Order ID: {response.cloid}")
    else:
        print(f"Order failed: {response.error}")

    # Disconnect
    await hl_core.disconnect()

async def main():
    """Run market order examples."""
    try:
        await example_market_orders()
    except Exception as e:
        print(f"L Error: {e}")
        print("=� Make sure you have PRIVATE_KEY set in your .env file")
        print("=� Ensure you're using testnet for these examples")


if __name__ == "__main__":
    asyncio.run(main())
