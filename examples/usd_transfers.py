"""USD Class Transfers example for HyperLiquid Unified API.

This example demonstrates:
- Transfer USD from perp to spot account
- Transfer USD from spot to perp account  
- Capital management between trading venues
- Error handling for transfer operations
"""

import asyncio
import os

from dotenv import load_dotenv

from hl_api import (
    HLProtocolCore,
)

# Load environment variables from .env file
load_dotenv()


async def example_usd_transfers():
    """Example of USD transfers between spot and perp accounts."""

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
    
    perp_to_spot_response = await hl_core.usd_class_transfer_to_spot(50.0)
    
    if perp_to_spot_response.success:
        print("✅ Transfer to spot successful!")
        print(f"   Amount: ${perp_to_spot_response.amount}")
        print(f"   Raw response: {perp_to_spot_response.raw_response}")
    else:
        print(f"❌ Transfer to spot failed: {perp_to_spot_response.error}")

    await asyncio.sleep(1)

    spot_to_perp_response = await hl_core.usd_class_transfer_to_perp(100.0)
    
    if spot_to_perp_response.success:
        print("✅ Transfer to perp successful!")
        print(f"   Amount: ${spot_to_perp_response.amount}")
        print(f"   Raw response: {spot_to_perp_response.raw_response}")
    else:
        print(f"❌ Transfer to perp failed: {spot_to_perp_response.error}")

    # Disconnect
    await hl_core.disconnect()

async def main():
    """Run USD class transfer examples."""
    print("=" * 60)
    print("HyperLiquid API - USD Class Transfers")
    print("=" * 60)
    print("💡 View account balances on testnet: https://app.hyperliquid-testnet.xyz/")
    print()

    await example_usd_transfers()

    print("\n" + "=" * 60)
    print("USD Transfer Examples Completed!")
    print("=" * 60)
    
if __name__ == "__main__":
    asyncio.run(main())