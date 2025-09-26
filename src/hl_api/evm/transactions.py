"""Transaction dispatch helpers for the HyperLiquid EVM client."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from ..exceptions import NetworkError
from ..utils import serialise_receipt
from .connections import Web3Connections

logger = logging.getLogger(__name__)


class TransactionDispatcher:
    """Encapsulate contract transaction submission and receipt handling."""

    def __init__(
        self,
        connections: Web3Connections,
        *,
        wait_for_receipt: bool,
        receipt_timeout: float,
    ) -> None:
        self._connections = connections
        self._wait_for_receipt = wait_for_receipt
        self._receipt_timeout = receipt_timeout

    def send(
        self,
        function_name: str,
        args: Sequence[Any],
        *,
        action: str,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._connections.ensure_connected()

        web3 = self._connections.hyperliquid_web3
        contract = self._connections.strategy_contract
        self._connections.account  # Ensure signer is hydrated before dispatching

        contract_function = getattr(contract.functions, function_name)(*args)
        logger.info("Dispatching %s via %s", action, function_name)

        try:
            tx_hash = contract_function.transact()
        except Exception as exc:  # pragma: no cover - defensive
            raise NetworkError(
                f"Failed to submit transaction for {action}",
                endpoint=function_name,
                details={"args": list(args), "error": str(exc)},
            ) from exc

        tx_hex = tx_hash.to_0x_hex()
        logger.info("Transaction sent for action=%s hash=%s", action, tx_hex)

        if self._wait_for_receipt:
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=self._receipt_timeout)
            if receipt:
                logger.info(
                    "Transaction confirmed for action=%s hash=%s block=%s",
                    action,
                    tx_hex,
                    getattr(receipt, "blockNumber", None),
                )
                serialised_receipt = serialise_receipt(receipt)
                block_number = getattr(receipt, "blockNumber", None)
            else:
                serialised_receipt = None
                block_number = None
        else:
            receipt = None
            serialised_receipt = None
            block_number = None

        return {
            "tx_hash": tx_hex,
            "action": action,
            "context": dict(context),
            "receipt": serialised_receipt,
            "block_number": block_number,
        }
