"""Market Order Example for HyperLiquid Unified API."""

import asyncio
import os

from dotenv import load_dotenv

from hl_api import HLProtocolCore, generate_cloid

load_dotenv()


async def example_market_orders():
    """Demonstrate native market order functionality."""

    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise ValueError("PRIVATE_KEY not found in environment variables")

    hl_core = HLProtocolCore(
        private_key=private_key,
        testnet=True,
        account_address=os.getenv("ACCOUNT_ADDRESS"),
    )

    await hl_core.connect()

    try:
        try:
            current_btc_price = await hl_core.get_market_price("BTC")
            print(f"Current BTC price: ${current_btc_price:,.2f}")
        except Exception as e:
            print(f"Could not fetch current price: {e}")
            current_btc_price = None

        cloid = generate_cloid()

        # Execute native market order with built-in slippage protection
        print("\nPlacing native market buy order...")
        print("- Asset: BTC")
        print("- Size: 0.0001 BTC")
        print("- Slippage: 0.5% (0.005)")
        print(f"- Client Order ID: {cloid}")

        response = await hl_core.market_order(
            asset="BTC",
            is_buy=True,
            sz=0.0001,
            slippage=0.005,  # 0.5% slippage protection
            cloid=cloid,
        )

        if response.success:
            print("\n✅ Market order placed successfully!")
            print(f"   Order ID: {response.order_id}")
            print(f"   Client Order ID: {response.cloid}")

            if current_btc_price:
                order_value = 0.0001 * current_btc_price
                print(f"   Estimated Order Value: ${order_value:.2f}")

        else:
            print(f"\n❌ Market order failed: {response.error}")

        # Example 2: Market sell order
        print("\n" + "-" * 30)
        print("Market Sell Order Example")
        print("-" * 30)

        sell_cloid = generate_cloid()

        print("Placing market sell order...")
        print("- Asset: BTC")
        print("- Size: 0.00005 BTC (smaller size)")
        print("- Slippage: 1% (0.01)")

        sell_response = await hl_core.market_order(
            asset="BTC",
            is_buy=False,  # Sell order
            sz=0.00005,
            slippage=0.01,  # 1% slippage protection
            cloid=sell_cloid,
        )

        if sell_response.success:
            print("\n✅ Market sell order placed successfully!")
            print(f"   Order ID: {sell_response.order_id}")
            print(f"   Client Order ID: {sell_response.cloid}")
        else:
            print(f"\n❌ Market sell order failed: {sell_response.error}")

        # Example 3: Position closing
        print("\n" + "-" * 30)
        print("Position Closing Example")
        print("-" * 30)

        print("Attempting to close BTC position...")

        close_response = await hl_core.market_close_position(
            asset="BTC",
            size=None,  # Close entire position
            slippage=0.02,  # 2% slippage for position closing
            cloid=generate_cloid(),
        )

        if close_response.success:
            print("✅ Position close order placed successfully!")
            print(f"   Order ID: {close_response.order_id}")
        else:
            print(f"❌ Position close failed: {close_response.error}")

        print("\n" + "=" * 50)

    except Exception as e:
        print(f"Error in market order example: {e}")

    finally:
        await hl_core.disconnect()


async def main():
    """Run market order examples."""

    print("=" * 50)
    print("HyperLiquid API - Example 03")
    print("🏧 Market Orders")
    print("=" * 60)

    try:
        await example_market_orders()
    except Exception as e:
        print(f"L Error: {e}")
        print("=� Make sure you have PRIVATE_KEY set in your .env file")
        print("=� Ensure you're using testnet for these examples")


if __name__ == "__main__":
    asyncio.run(main())
