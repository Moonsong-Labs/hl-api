"""Basic usage example for HyperLiquid Unified API."""

import asyncio

from hyperliquid_unified import (
    HLProtocolCore,
    generate_cloid,
    price_to_uint64,
    size_to_uint64,
)


async def example_core_trading():
    """Example of trading using HyperLiquid Core SDK."""

    # Initialize Core protocol
    # Replace with your actual private key
    hl_core = HLProtocolCore(
        private_key="YOUR_PRIVATE_KEY_HERE",
        testnet=True,  # Use testnet for testing
    )

    # Connect to HyperLiquid
    await hl_core.connect()

    # Place a limit order
    # Example: Buy 0.1 BTC at $65,000
    price_uint64 = price_to_uint64(65000)  # Convert price to uint64
    size_uint64 = size_to_uint64(0.1)  # Convert size to uint64
    cloid = generate_cloid()  # Generate unique client order ID

    response = await hl_core.limit_order(
        asset=0,  # BTC-PERP (asset index 0)
        is_buy=True,
        limit_px=price_uint64,
        sz=size_uint64,
        reduce_only=False,
        tif="GTC",  # Good Till Cancelled
        cloid=cloid,
    )

    if response.success:
        print("Order placed successfully!")
        print(f"Order ID: {response.order_id}")
        print(f"Client Order ID: {response.cloid}")
    else:
        print(f"Order failed: {response.error}")

    # Cancel the order
    cancel_response = await hl_core.cancel_order(asset=0, cloid=cloid)

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

    # Uncomment the example you want to run:

    # await example_core_trading()
    # await example_evm_trading()
    # await example_unified_interface()

    print("\nNote: Replace private keys and RPC URLs with actual values to run these examples.")


if __name__ == "__main__":
    asyncio.run(main())
