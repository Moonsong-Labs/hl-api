"""Configuration containers for the HyperLiquid Core client."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoreClientConfig:
    """Aggregated configuration for the Core SDK client."""

    private_key: str
    testnet: bool = True
    base_url: str | None = None
    account_address: str | None = None
    skip_ws: bool = True

    def resolved_base_url(self) -> str:
        """Return the API base URL, defaulting to official endpoints."""

        if self.base_url:
            return self.base_url.rstrip("/")

        try:
            from hyperliquid.utils.constants import MAINNET_API_URL, TESTNET_API_URL
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError("hyperliquid-python-sdk is required to resolve API URLs") from exc

        return (TESTNET_API_URL if self.testnet else MAINNET_API_URL).rstrip("/")
