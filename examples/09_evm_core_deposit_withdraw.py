"""Example: Deposit and withdraw tokens between HyperEVM and HyperCore."""

from __future__ import annotations

import logging
import os
import time

from dotenv import load_dotenv

from hl_api import HLProtocolEVM
from hl_api.utils import fetch_token_metadata, get_token_evm_address

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOGLEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("core_deposit_withdraw")


def main() -> None:
    """Demonstrate deposit and withdrawal between HyperEVM and HyperCore."""
    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise ValueError("PRIVATE_KEY not found in environment variables")

    hl_rpc_url = os.getenv("HYPER_EVM_RPC", "https://rpc.hyperliquid-testnet.xyz/evm")
    mn_rpc_url = os.getenv("HL_EVM_RPC", "https://sepolia.drpc.org")
    hl_strategy_address = os.getenv("HYPERLIQUID_STRATEGY")
    bridge_address = os.getenv("BRIDGE_STRATEGY")

    if not hl_strategy_address or not bridge_address:
        raise ValueError("HYPERLIQUID_STRATEGY and BRIDGE_STRATEGY must be set")

    testnet = "testnet" in hl_rpc_url

    client = HLProtocolEVM(
        private_key=private_key,
        hl_rpc_url=hl_rpc_url,
        mn_rpc_url=mn_rpc_url,
        testnet=True,
        hl_strategy_address=hl_strategy_address,
        bridge_strategy_address=bridge_address,
        disable_call_verification=True,
        receipt_timeout=300,  # 5 minutes for withdrawals
    )

    logger.info("Connecting to HyperLiquid EVM")
    client.connect()

    try:
        token_metadata = fetch_token_metadata(testnet=testnet)
        usdc_index = token_metadata.get("USDC")
        if usdc_index is None:
            logger.error("USDC not found in token metadata")
            return

        usdc_address = get_token_evm_address("USDC", testnet=testnet)
        if not usdc_address:
            logger.error("Could not find USDC contract address")
            return

        logger.info("USDC token index: %d, address: %s", usdc_index, usdc_address)

        deposit_amount = 1.0
        logger.info("Depositing %.2f USDC to HyperCore", deposit_amount)
        deposit_response = client.deposit_token_to_core(
            token_address=usdc_address,
            token_index=usdc_index,
            amount=deposit_amount,
        )

        if deposit_response.success:
            logger.info("Deposit successful: %s", deposit_response.transaction_hash)
        else:
            logger.error("Deposit failed: %s", deposit_response.error)
            raise RuntimeError("Deposit failed, aborting")

        logger.info("Waiting 5 seconds before withdrawal")
        time.sleep(5)

        withdraw_amount = 1.0
        logger.info("Withdrawing %.2f USDC back to HyperEVM", withdraw_amount)
        logger.info("Note: Withdrawals can take several minutes to confirm")

        withdraw_response = client.withdraw_token_to_evm(
            token_index=usdc_index,
            amount=withdraw_amount,
        )

        if withdraw_response.success:
            logger.info("Withdrawal initiated: %s", withdraw_response.transaction_hash)
            logger.info("Withdrawal will be processed in a few minutes")
        else:
            logger.error("Withdrawal failed: %s", withdraw_response.error)
            raise RuntimeError("Withdrawal failed")

    finally:
        client.disconnect()
        logger.info("Disconnected from HyperLiquid EVM")


if __name__ == "__main__":
    main()
