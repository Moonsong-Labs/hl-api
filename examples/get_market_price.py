"""Market Price Fetching Example for HyperLiquid Unified API."""

import asyncio
import logging
import os

from dotenv import load_dotenv

from hl_api import HLProtocolCore
from hl_api.exceptions import NetworkError

# Configure logging to see detailed execution
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()


async def basic_price_fetching():
    """Demonstrate basic market price fetching."""

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
    logger.info("Connected to HyperLiquid testnet")

    try:
        print("=" * 60)
        print("Basic Market Price Fetching Examples")
        print("=" * 60)

        # Example 1: Fetch individual prices
        print("\n1. Individual Asset Prices")
        print("-" * 30)

        # Fetch BTC price
        try:
            btc_price = await hl_core.get_market_price("BTC")
            print(f"BTC Price: ${btc_price:,.2f}")
        except Exception as e:
            print(f"Error fetching BTC price: {e}")

        # Fetch ETH price
        try:
            eth_price = await hl_core.get_market_price("ETH")
            print(f"ETH Price: ${eth_price:,.2f}")
        except Exception as e:
            print(f"Error fetching ETH price: {e}")

        # Example 2: Batch price fetching
        print("\n2. Batch Price Fetching")
        print("-" * 30)

        assets = ["BTC", "ETH", "ATOM", "AVAX", "SOL"]
        prices: dict[str, float] = {}

        for asset in assets:
            try:
                price = await hl_core.get_market_price(asset)
                prices[asset] = price
                print(f"{asset:>6}: ${price:>10,.2f}")
            except ValueError as e:
                print(f"{asset:>6}: ❌ {e}")
            except NetworkError as e:
                print(f"{asset:>6}: ❌ Network error: {e}")
            except Exception as e:
                print(f"{asset:>6}: ❌ Unexpected error: {e}")

        # Example 3: Price comparison and analysis
        print("\n3. Price Analysis")
        print("-" * 30)

        if "BTC" in prices and "ETH" in prices:
            btc_eth_ratio = prices["BTC"] / prices["ETH"]
            print(f"BTC/ETH Ratio: {btc_eth_ratio:.2f}")
            print(f"1 BTC = {btc_eth_ratio:.2f} ETH")
            print(f"1 ETH = {1 / btc_eth_ratio:.6f} BTC")

        # Calculate total portfolio value example
        if prices:
            # Example portfolio holdings
            portfolio = {"BTC": 0.1, "ETH": 2.0, "ATOM": 100.0, "SOL": 10.0}

            total_value = 0.0
            print("\nExample Portfolio Value:")

            for asset, holding in portfolio.items():
                if asset in prices:
                    asset_value = holding * prices[asset]
                    total_value += asset_value
                    print(f"  {asset}: {holding} × ${prices[asset]:,.2f} = ${asset_value:,.2f}")

            print(f"\nTotal Portfolio Value: ${total_value:,.2f}")

        # Example 4: Error handling demonstration
        print("\n4. Error Handling Examples")
        print("-" * 30)

        # Try fetching an invalid asset
        try:
            invalid_price = await hl_core.get_market_price("INVALID_ASSET")
            print(f"Invalid asset price: {invalid_price}")
        except ValueError as e:
            print(f"✅ Correctly caught error for invalid asset: {e}")
        except Exception as e:
            print(f"❌ Unexpected error type: {e}")

        # Try fetching with empty string
        try:
            empty_price = await hl_core.get_market_price("")
            print(f"Empty asset price: {empty_price}")
        except ValueError as e:
            print(f"✅ Correctly caught error for empty asset: {e}")
        except Exception as e:
            print(f"❌ Unexpected error type: {e}")

    except Exception as e:
        logger.error(f"Error in basic price fetching: {e}")
    finally:
        # Always disconnect when done
        await hl_core.disconnect()
        logger.info("Disconnected from HyperLiquid")


async def main():
    """Run all market price examples."""
    try:
        print("🔍 HyperLiquid Market Price Examples")
        print("=" * 60)

        # Run example
        await basic_price_fetching()

    except Exception as e:
        logger.error(f"Error in main: {e}")
        print("❌ Make sure you have PRIVATE_KEY set in your .env file")
        print("❌ Ensure you're using testnet for these examples")


if __name__ == "__main__":
    asyncio.run(main())
