"""Example: Transfer USD between perp and spot via HyperLiquid strategy."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Mapping
from typing import Any

from dotenv import load_dotenv

from hl_api import HLProtocolEVM

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOGLEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

TRANSFER_AMOUNT = 5.0
SLEEP_SECONDS = 5


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} not found in environment variables")
    return value


def _log_transfer_response(
    prefix: str,
    success: bool,
    response: Mapping[str, Any] | None,
    error: str | None,
) -> None:
    if success:
        logging.info(
            "%s successful; tx hash: %s", prefix, response.get("tx_hash") if response else None
        )
        if response and response.get("block_number") is not None:
            logging.info("%s included in block: %s", prefix, response.get("block_number"))
    else:
        logging.error("%s failed: %s", prefix, error)
        if response:
            logging.error("Raw response: %s", response)


def main() -> None:
    """Move USD from perp to spot and back via HyperLiquid strategy contract."""

    private_key = _require_env("PRIVATE_KEY")
    hl_rpc_url = os.getenv("HYPER_EVM_RPC", "https://rpc.hyperliquid-testnet.xyz/evm")
    mn_rpc_url = os.getenv("HL_EVM_RPC", "https://sepolia.drpc.org")
    hl_strategy_address = _require_env("HYPERLIQUID_STRATEGY")
    bridge_address = _require_env("BRIDGE_STRATEGY")

    client = HLProtocolEVM(
        private_key=private_key,
        hl_rpc_url=hl_rpc_url,
        mn_rpc_url=mn_rpc_url,
        hl_strategy_address=hl_strategy_address,
        bridge_strategy_address=bridge_address,
        disable_call_verification=True,  # Skip call verification for this example
    )

    logging.info("Connecting to HyperLiquid EVM at %s", hl_rpc_url)
    client.connect()
    try:
        logging.info("Transferring $%s from perp to spot", TRANSFER_AMOUNT)
        to_spot = client.usd_class_transfer_to_spot(TRANSFER_AMOUNT)
        _log_transfer_response(
            "Perp -> Spot transfer",
            to_spot.success,
            to_spot.raw_response,
            to_spot.error,
        )
        if not to_spot.success:
            return

        logging.info("Sleeping %s seconds before reversing transfer", SLEEP_SECONDS)
        time.sleep(SLEEP_SECONDS)

        logging.info("Transferring $%s from spot back to perp", TRANSFER_AMOUNT)
        to_perp = client.usd_class_transfer_to_perp(TRANSFER_AMOUNT)
        _log_transfer_response(
            "Spot -> Perp transfer",
            to_perp.success,
            to_perp.raw_response,
            to_perp.error,
        )
    finally:
        client.disconnect()
        logging.info("Disconnected from HyperLiquid EVM")


if __name__ == "__main__":
    main()
