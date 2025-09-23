"""USD Class Transfers example for HyperLiquid Unified API.

This example demonstrates:
- Transfer USD from perp to spot account
- Transfer USD from spot to perp account
- Capital management between trading venues
- Error handling for transfer operations
"""

import os
import time

from dotenv import load_dotenv

from hl_api import (
    HLProtocolCore,
)

load_dotenv()


def example_usd_transfers():
    """Example of USD transfers between spot and perp accounts."""

    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise ValueError("PRIVATE_KEY not found in environment variables")

    hl_core = HLProtocolCore(
        private_key=private_key,
        testnet=True,
        account_address=os.getenv("ACCOUNT_ADDRESS"),
    )

    hl_core.connect()

    perp_to_spot_response = hl_core.usd_class_transfer_to_spot(4)

    if perp_to_spot_response.success:
        print("✅ Transfer to spot successful!")
        print(f"   Amount: ${perp_to_spot_response.amount}")
        print(f"   Raw response: {perp_to_spot_response.raw_response}")
    else:
        print(f"❌ Transfer to spot failed: {perp_to_spot_response.error}")

    time.sleep(1)

    spot_to_perp_response = hl_core.usd_class_transfer_to_perp(4)

    if spot_to_perp_response.success:
        print("✅ Transfer to perp successful!")
        print(f"   Amount: ${spot_to_perp_response.amount}")
        print(f"   Raw response: {spot_to_perp_response.raw_response}")
    else:
        print(f"❌ Transfer to perp failed: {spot_to_perp_response.error}")

    # Disconnect
    hl_core.disconnect()


def main():
    """Run USD class transfer examples."""

    print("=" * 50)
    print("HyperLiquid API - Example 04")
    print("💸 USD Class Transfers")
    print("=" * 60)

    example_usd_transfers()


if __name__ == "__main__":
    main()
