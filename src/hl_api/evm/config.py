"""Configuration for the HyperLiquid EVM client."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from web3.types import ChecksumAddress

DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_RECEIPT_TIMEOUT = 120.0
DEFAULT_IRIS_POLL_INTERVAL = 2.0
DEFAULT_IRIS_MAX_POLLS = 100
DEFAULT_CCTP_FINALITY_THRESHOLD = 1000
DEFAULT_FLEXIBLE_VAULT_PROOF_URL = (
    "https://raw.githubusercontent.com/mellow-finance/flexible-vaults/"
    "test-deployments/scripts/jsons/ethereum%3AtqETH%3Asubvault0.json"
)
IRIS_API_SANDBOX = "https://iris-api-sandbox.circle.com"
IRIS_API_PROD = "https://iris-api.circle.com"


@dataclass
class EVMClientConfig:
    """Configuration for the EVM protocol client."""

    private_key: str
    hl_rpc_url: str
    mn_rpc_url: str
    hl_strategy_address: ChecksumAddress
    bridge_strategy_address: ChecksumAddress

    testnet: bool = True
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT

    wait_for_receipt: bool = True
    receipt_timeout: float = DEFAULT_RECEIPT_TIMEOUT
    iris_poll_interval: float = DEFAULT_IRIS_POLL_INTERVAL
    iris_max_polls: int = DEFAULT_IRIS_MAX_POLLS
    hyperliquid_domain: int | None = None
    mainnet_domain: int | None = None
    cctp_finality_threshold: int = DEFAULT_CCTP_FINALITY_THRESHOLD

    flexible_vault_proof_url: str | Sequence[str] = DEFAULT_FLEXIBLE_VAULT_PROOF_URL
    flexible_vault_verifier_address: str | None = None
    flexible_vault_verifier_network: str = "hyper"
    flexible_vault_check_merkle_root: bool = False
    flexible_vault_proof_blob: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None

    info_url: str | None = None
    iris_base_url: str | None = None

    def __post_init__(self):
        """Set default URLs based on testnet flag."""
        if self.info_url is None:
            self.info_url = (
                "https://api.hyperliquid-testnet.xyz/info"
                if self.testnet
                else "https://api.hyperliquid.xyz/info"
            )
        else:
            self.info_url = self.info_url.rstrip("/")

        if self.iris_base_url is None:
            self.iris_base_url = IRIS_API_SANDBOX if self.testnet else IRIS_API_PROD
        else:
            self.iris_base_url = self.iris_base_url.rstrip("/")
