#!/usr/bin/env python3
"""Integration test for market order price precision."""

import os
import sys
from decimal import Decimal
from typing import TypedDict
from unittest.mock import MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hl_api.evm import HLProtocolEVM


def test_market_order_price_formatting():
    """Test that market orders correctly format slippage prices."""

    # Create instance with dummy values (we'll mock everything anyway)
    api = HLProtocolEVM(
        private_key="0x" + "0" * 64,  # Dummy private key
        rpc_url="http://localhost:8545",  # Dummy RPC URL
        strategy_address="0x" + "0" * 40,  # Dummy address
    )

    # Mock the internal methods to avoid actual network calls
    api._ensure_connected = MagicMock()
    api._resolve_asset_id = MagicMock(return_value=4)  # ETH asset ID
    api._resolve_perp_sz_decimals = MagicMock(return_value=4)  # ETH has 4 sz_decimals

    print("Testing Market Order Price Formatting")
    print("=" * 60)

    class MarketOrderTestCase(TypedDict):
        asset: str
        asset_id: int
        mid_price: float
        is_buy: bool
        slippage: float
        sz_decimals: int
        expected_price: float
        description: str

    # Test cases with different assets and prices
    test_cases: list[MarketOrderTestCase] = [
        {
            "asset": "ETH",
            "asset_id": 4,
            "mid_price": 2500.123456,
            "is_buy": True,
            "slippage": 0.05,
            "sz_decimals": 4,
            "expected_price": 2625.13,  # 2500.123456 * 1.05 = 2625.13 (rounded to 2 decimals for ETH)
            "description": "ETH buy with 5% slippage",
        },
        {
            "asset": "ETH",
            "asset_id": 4,
            "mid_price": 2500.123456,
            "is_buy": False,
            "slippage": 0.05,
            "sz_decimals": 4,
            "expected_price": 2375.12,  # 2500.123456 * 0.95 = 2375.12 (rounded to 2 decimals)
            "description": "ETH sell with 5% slippage",
        },
        {
            "asset": "BTC",
            "asset_id": 1,
            "mid_price": 45678.987654,
            "is_buy": True,
            "slippage": 0.03,
            "sz_decimals": 5,
            "expected_price": 47049.0,  # 45678.987654 * 1.03 = 47049.4 -> 47049 (1 decimal for BTC, but 5 sig figs)
            "description": "BTC buy with 3% slippage",
        },
        {
            "asset": "SOL",
            "asset_id": 2,
            "mid_price": 123.456789,
            "is_buy": True,
            "slippage": 0.10,
            "sz_decimals": 3,
            "expected_price": 135.8,  # 123.456789 * 1.10 = 135.80 (3 decimals for SOL, 4 sig figs)
            "description": "SOL buy with 10% slippage",
        },
    ]

    for test in test_cases:
        # Configure mocks for this test
        api._resolve_asset_id = MagicMock(return_value=test["asset_id"])
        api._resolve_perp_sz_decimals = MagicMock(return_value=test["sz_decimals"])

        # Call the method
        formatted_price = api._compute_slippage_price(
            asset=test["asset"],
            mid_price=test["mid_price"],
            is_buy=test["is_buy"],
            slippage=test["slippage"],
        )

        # Check result
        success = abs(formatted_price - test["expected_price"]) < 0.01
        symbol = "✓" if success else "✗"

        print(f"{symbol} {test['description']}")
        print(f"  Mid price: {test['mid_price']}")
        print(f"  Direction: {'BUY' if test['is_buy'] else 'SELL'}")
        print(f"  Slippage: {test['slippage'] * 100}%")
        print(
            f"  Raw slippage price: {test['mid_price'] * (1 + test['slippage'] if test['is_buy'] else 1 - test['slippage']):.8f}"
        )
        print(f"  Formatted price: {formatted_price}")
        print(f"  Expected: {test['expected_price']}")

        if not success:
            print(f"  ERROR: Difference of {abs(formatted_price - test['expected_price'])}")

        print()

    print("=" * 60)
    print("Market order price formatting test complete!")

    # Test that the limit_order method is called with the correctly formatted price
    print("\nTesting full market_order flow:")
    print("-" * 60)

    # Mock additional required methods
    api._market_price_context = MagicMock(
        return_value=(Decimal("2500"), Decimal("2499"), Decimal("2501"))
    )
    api.limit_order = MagicMock(return_value={"success": True})

    # Call market_order
    api.market_order(asset="ETH", is_buy=True, sz=0.01, slippage=0.05)

    # Check that limit_order was called with the correctly formatted price
    call_args = api.limit_order.call_args
    if call_args:
        limit_price = call_args.kwargs.get(
            "limit_px", call_args.args[2] if len(call_args.args) > 2 else None
        )
        print(f"✓ limit_order called with price: {limit_price}")

        # Verify it's properly formatted (should have at most 2 decimals for ETH)
        price_str = str(limit_price)
        if "." in price_str:
            decimal_places = len(price_str.split(".")[1])
            if decimal_places <= 2:  # ETH with sz_decimals=4 allows max 2 decimals
                print(f"✓ Price has {decimal_places} decimal places (max 2 for ETH)")
            else:
                print(f"✗ Price has {decimal_places} decimal places (exceeds max 2 for ETH)")
    else:
        print("✗ limit_order was not called")

    print("\n✅ All market order precision tests complete!")


if __name__ == "__main__":
    test_market_order_price_formatting()
