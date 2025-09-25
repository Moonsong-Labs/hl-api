"""Configuration containers for the HyperLiquid EVM client."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from web3.types import ChecksumAddress

DEFAULT_FLEXIBLE_VAULT_PROOF_URL = (
    "https://raw.githubusercontent.com/mellow-finance/flexible-vaults/"
    "test-deployments/scripts/jsons/ethereum%3AtqETH%3Asubvault0.json"
)


@dataclass(frozen=True)
class FlexibleVaultConfig:
    """Configuration for fetching Mellow flexible vault proof blobs."""

    proof_url: str = DEFAULT_FLEXIBLE_VAULT_PROOF_URL
    verifier_address: str | None = None
    verifier_network: str = "hyper"
    check_merkle_root: bool = False
    proof_blob: Mapping[str, Any] | None = None


DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_RECEIPT_TIMEOUT = 120.0
DEFAULT_IRIS_POLL_INTERVAL = 2.0
DEFAULT_IRIS_MAX_POLLS = 100
DEFAULT_CCTP_FINALITY_THRESHOLD = 1000
IRIS_API_SANDBOX = "https://iris-api-sandbox.circle.com"
IRIS_API_PROD = "https://iris-api.circle.com"


@dataclass(frozen=True)
class BridgeConfig:
    """Configuration for CCTPv2 bridge helpers."""

    wait_for_receipt: bool = True
    receipt_timeout: float = DEFAULT_RECEIPT_TIMEOUT
    iris_base_url: str | None = None
    iris_poll_interval: float = DEFAULT_IRIS_POLL_INTERVAL
    iris_max_polls: int = DEFAULT_IRIS_MAX_POLLS
    hyperliquid_domain: int | None = None
    mainnet_domain: int | None = None
    cctp_finality_threshold: int = DEFAULT_CCTP_FINALITY_THRESHOLD


@dataclass(frozen=True)
class EVMClientConfig:
    """Aggregated configuration used to construct the EVM protocol client."""

    private_key: str
    hl_rpc_url: str
    mn_rpc_url: str
    hl_strategy_address: ChecksumAddress
    bridge_strategy_address: ChecksumAddress
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    testnet: bool = True
    info_url: str | None = None
    bridge: BridgeConfig = BridgeConfig()
    flexible_vault: FlexibleVaultConfig | None = None

    def with_defaulted_urls(self) -> EVMClientConfig:
        """Return a copy with default info/iris URLs based on network selection."""

        if self.info_url is None:
            info_url = (
                "https://api.hyperliquid-testnet.xyz/info"
                if self.testnet
                else "https://api.hyperliquid.xyz/info"
            )
        else:
            info_url = self.info_url.rstrip("/")

        iris_url = self.bridge.iris_base_url
        if iris_url is None:
            iris_url = IRIS_API_SANDBOX if self.testnet else IRIS_API_PROD
        bridge = replace(self.bridge, iris_base_url=iris_url.rstrip("/"))

        return replace(
            self,
            info_url=info_url,
            bridge=bridge,
        )
