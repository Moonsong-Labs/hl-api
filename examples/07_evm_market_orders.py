"""Example: Execute market buy/sell orders via HyperLiquid EVM connector."""

from __future__ import annotations

import logging
import os
from decimal import Decimal

from dotenv import load_dotenv

from hl_api import HLProtocolEVM, generate_cloid

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOGLEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

ASSET_SYMBOL = "ETH"
DEFAULT_SLIPPAGE = 0.01  # 1%
SIZE = 0.005  # 0.005 ETH


def main() -> None:
    """Demonstrate market buy/sell via HLProtocolEVM."""

    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise ValueError("PRIVATE_KEY not found in environment variables")

    rpc_url = os.getenv("HYPER_EVM_RPC", "https://rpc.hyperliquid-testnet.xyz/evm")
    strategy_address = os.getenv("HYPERLIQUID_STRATEGY")
    if not strategy_address:
        raise ValueError("HYPERLIQUID_STRATEGY not found in environment variables")

    client = HLProtocolEVM(
        private_key=private_key,
        rpc_url=rpc_url,
        strategy_address=strategy_address,
    )

    client.connect()
    try:
        client.load_asset_metadata_from_info()

        mid_price = Decimal(str(client.get_market_price(ASSET_SYMBOL)))
        approx_usd = (mid_price * Decimal(str(SIZE))).quantize(Decimal("0.01"))

        logging.info(
            "Placing market buy on %s for ~%s USD (size=%s)",
            ASSET_SYMBOL,
            approx_usd,
            SIZE,
        )

        buy_response = client.market_order(
            asset=ASSET_SYMBOL,
            is_buy=True,
            sz=SIZE,
            slippage=DEFAULT_SLIPPAGE,
            cloid=generate_cloid(),
        )
        if not buy_response.success:
            logging.error("Market buy failed: %s", buy_response.error)
            return

        logging.info("Market buy complete; response: %s", buy_response.raw_response)

        logging.info("Submitting market sell to flatten position")
        close_response = client.market_close_position(
            asset=ASSET_SYMBOL,
            size=SIZE,
            slippage=DEFAULT_SLIPPAGE,
            cloid=generate_cloid(),
        )
        if not close_response.success:
            logging.error("Market sell failed: %s", close_response.error)
            return

        logging.info("Market sell complete; response: %s", close_response.raw_response)

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
