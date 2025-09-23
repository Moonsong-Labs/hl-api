"""Configuration containers for the HyperLiquid EVM client."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from web3.types import ChecksumAddress

from ..types import VerificationPayload

VerificationResolver = Callable[
    [str, Mapping[str, object]], VerificationPayload | Mapping[str, object]
]


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
    verification_payload_url: str | None = None
    verification_payload_resolver: VerificationResolver | None = None
    testnet: bool = True
    info_url: str | None = None
    bridge: BridgeConfig = BridgeConfig()

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

        bridge = self.bridge
        iris_url = bridge.iris_base_url
        if iris_url is None:
            iris_url = IRIS_API_SANDBOX if self.testnet else IRIS_API_PROD
        bridge = BridgeConfig(
            wait_for_receipt=bridge.wait_for_receipt,
            receipt_timeout=bridge.receipt_timeout,
            iris_base_url=iris_url.rstrip("/"),
            iris_poll_interval=bridge.iris_poll_interval,
            iris_max_polls=bridge.iris_max_polls,
            hyperliquid_domain=bridge.hyperliquid_domain,
            mainnet_domain=bridge.mainnet_domain,
            cctp_finality_threshold=bridge.cctp_finality_threshold,
        )

        return EVMClientConfig(
            private_key=self.private_key,
            hl_rpc_url=self.hl_rpc_url,
            mn_rpc_url=self.mn_rpc_url,
            hl_strategy_address=self.hl_strategy_address,
            bridge_strategy_address=self.bridge_strategy_address,
            request_timeout=self.request_timeout,
            verification_payload_url=self.verification_payload_url,
            verification_payload_resolver=self.verification_payload_resolver,
            testnet=self.testnet,
            info_url=info_url,
            bridge=bridge,
        )
