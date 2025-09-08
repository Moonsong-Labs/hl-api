"""Vault management example for HyperLiquid Unified API."""

import asyncio
import os

from dotenv import load_dotenv

from hl_api import (
    HLProtocolCore,
)

# Load environment variables from .env file
load_dotenv()


async def example_vault_operations():
    """Example of vault deposit and withdrawal operations."""

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

    # Example vault address (replace with actual vault address)
    vault_address = os.getenv("VAULT_ADDRESS")

    print(f"🏦 Using vault address: {vault_address}")
    print("💡 Replace VAULT_ADDRESS in your .env file with a real vault address")
    print()

    # 1. Vault Deposit Example
    print("1. Vault Deposit Example")
    deposit_amount = 10.0

    deposit_response = await hl_core.vault_transfer(
        vault=vault_address,
        is_deposit=True,
        usd=deposit_amount
    )

    if deposit_response.success:
        print("✅ Vault deposit successful!")
        print(f"   Amount: ${deposit_response.amount}")
        print(f"   Vault: {vault_address[:10]}...{vault_address[-8:]}")
        print(f"   Raw response: {deposit_response.raw_response}")
        print(f"Check deposits at https://app.hyperliquid-testnet.xyz/vaults/${vault_address}")
    else:
        print(f"❌ Vault deposit failed: {deposit_response.error}")
        print("   💡 Ensure you have sufficient balance and valid vault address")


async def main():
    """Run vault management examples."""
    print("=" * 50)
    print("HyperLiquid API - Vault Management")
    print("=" * 50)
    print("💡 View vaults on testnet: https://app.hyperliquid-testnet.xyz/")
    print()

    await example_vault_operations()

    print("\n" + "=" * 50)
    print("Vault Management Examples Completed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
