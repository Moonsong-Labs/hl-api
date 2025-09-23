"""Example: Place and cancel a limit order via HyperLiquid EVM connector."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from hl_api import HLProtocolEVM, generate_cloid

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

ASSET_SYMBOL = "ETH"
LIMIT_PRICE = "2000.0"
SIZE = "0.01"


def main() -> None:
    """Place and cancel a limit order on HyperLiquid EVM via strategy contract."""

    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise ValueError("PRIVATE_KEY not found in environment variables")

    hl_rpc_url = os.getenv("HYPER_EVM_RPC", "https://rpc.hyperliquid-testnet.xyz/evm")
    mn_rpc_url = os.getenv("HL_EVM_RPC", "https://sepolia.drpc.org")
    strategy_address = os.getenv("HYPERLIQUID_STRATEGY")
    if not strategy_address:
        raise ValueError("HYPERLIQUID_STRATEGY not found in environment variables")
    bridge_address = os.getenv("BRIDGE_STRATEGY")
    if not bridge_address:
        raise ValueError("BRIDGE_STRATEGY not found in environment variables")

    hl = HLProtocolEVM(
        private_key=private_key,
        hl_rpc_url=hl_rpc_url,
        mn_rpc_url=mn_rpc_url,
        hl_strategy_address=strategy_address,
        bridge_strategy_address=bridge_address,
    )

    hl.connect()
    try:
        cloid = generate_cloid()
        print(
            f"Placing limit order: asset={ASSET_SYMBOL} size={SIZE} at ${LIMIT_PRICE} (cloid={cloid})"
        )

        order_response = hl.limit_order(
            asset=ASSET_SYMBOL,
            is_buy=True,
            limit_px=float(LIMIT_PRICE),
            sz=float(SIZE),
            tif="GTC",
            cloid=cloid,
        )
        if not order_response.success:
            print(f"Order placement failed: {order_response.error}")
            if order_response.raw_response:
                print("Details:", order_response.raw_response)
            return

        order_tx = order_response.raw_response or {}
        print(f"Order tx hash: {order_tx.get('tx_hash')}")
        if order_tx.get("block_number") is not None:
            print(f"Order included in block: {order_tx.get('block_number')}")

        cancel_response = hl.cancel_order_by_cloid(ASSET_SYMBOL, cloid)
        if cancel_response.success:
            print("Order cancelled successfully")
            cancel_tx = cancel_response.raw_response or {}
            print(f"Cancel tx hash: {cancel_tx.get('tx_hash')}")
            if cancel_tx.get("block_number") is not None:
                print(f"Cancel included in block: {cancel_tx.get('block_number')}")
        else:
            print(f"Order cancellation failed: {cancel_response.error}")
            if cancel_response.raw_response:
                print("Details:", cancel_response.raw_response)
    finally:
        hl.disconnect()


if __name__ == "__main__":
    main()
