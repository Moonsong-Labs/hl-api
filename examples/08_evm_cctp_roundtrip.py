"""Example: Bridge USDC between Ethereum and HyperEVM using HLProtocolEVM helpers."""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv

from hl_api import HLProtocolEVM
from hl_api.types import BridgeResponse

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOGLEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("cctp_roundtrip")

DEFAULT_AMOUNT = float(os.getenv("BRIDGE_AMOUNT_USDC", "10"))


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} not found in environment variables")
    return value


def _log_bridge_result(label: str, response: BridgeResponse) -> None:
    context: dict[str, Any] = response.raw_response or {}
    if response.success:
        logger.info("%s succeeded (amount %.6f USDC)", label, response.amount or 0.0)
        logger.info("  burn tx: %s", response.burn_tx_hash)
        logger.info("  claim tx: %s", response.claim_tx_hash)
        logger.debug("  attestation: %s", response.attestation)
        logger.debug("  message: %s", response.message)
    else:
        logger.error("%s failed: %s", label, response.error)
        if response.burn_tx_hash:
            logger.error("  burn tx hash: %s", response.burn_tx_hash)
        if context:
            logger.debug("  context: %s", context)


def main() -> None:
    private_key = _require_env("PRIVATE_KEY")
    hl_strategy_address = _require_env("HYPERLIQUID_STRATEGY")
    hyper_bridge_address = os.getenv("BRIDGE_STRATEGY_HYPER") or _require_env("BRIDGE_STRATEGY")
    mainnet_bridge_address = _require_env("BRIDGE_STRATEGY_MAINNET")

    hl_rpc_url = os.getenv("HYPER_EVM_RPC", "https://rpc.hyperliquid-testnet.xyz/evm")
    mn_rpc_url = os.getenv("HL_EVM_RPC", "https://sepolia.drpc.org")
    testnet = os.getenv("HL_API_TESTNET", "true").lower() != "false"

    amount = float(os.getenv("BRIDGE_AMOUNT_USDC", str(DEFAULT_AMOUNT)))

    client = HLProtocolEVM(
        private_key=private_key,
        hl_rpc_url=hl_rpc_url,
        mn_rpc_url=mn_rpc_url,
        hl_strategy_address=hl_strategy_address,
        bridge_strategy_address=hyper_bridge_address,
        mainnet_bridge_strategy_address=mainnet_bridge_address,
        testnet=testnet,
    )

    client.connect()
    try:
        logger.info("Bridging %.6f USDC from mainnet to HyperEVM", amount)
        forward = client.bridge_mainnet_to_hyperliquid(amount)
        _log_bridge_result("Mainnet -> HyperEVM", forward)
        if not forward.success:
            return

        logger.info("Bridging %.6f USDC from HyperEVM back to mainnet", amount)
        reverse = client.bridge_hyperliquid_to_mainnet(amount)
        _log_bridge_result("HyperEVM -> Mainnet", reverse)
    finally:
        client.disconnect()
        logger.info("Disconnected")


if __name__ == "__main__":
    main()
