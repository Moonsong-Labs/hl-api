"""Connection helpers for the HyperLiquid Core SDK client."""

from __future__ import annotations

import logging
from typing import cast

import eth_account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from ..exceptions import NetworkError
from .config import CoreClientConfig

logger = logging.getLogger(__name__)


class CoreConnections:
    """Manage lifecycle of the HyperLiquid SDK clients."""

    def __init__(self, config: CoreClientConfig) -> None:
        self._config = config
        self._exchange: Exchange | None = None
        self._info: Info | None = None
        self._wallet = None
        self._account_address: str | None = config.account_address
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> None:
        api_url = self._config.resolved_base_url()

        wallet = eth_account.Account.from_key(self._config.private_key)  # type: ignore[attr-defined]

        account_address = self._account_address or cast(str, wallet.address)

        exchange = Exchange(
            wallet=wallet,
            base_url=api_url,
            account_address=account_address,
        )
        info = Info(base_url=api_url, skip_ws=self._config.skip_ws)

        self._wallet = wallet
        self._exchange = exchange
        self._info = info
        self._account_address = account_address
        self._connected = True
        logger.info("Connected to HyperLiquid %s", "testnet" if self._config.testnet else "mainnet")

    def disconnect(self) -> None:
        self._exchange = None
        self._info = None
        self._connected = False

    def ensure_connected(self) -> None:
        if not self._connected or self._exchange is None:
            raise NetworkError("Core SDK client is not connected")

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    @property
    def exchange(self) -> Exchange:
        if self._exchange is None:
            raise NetworkError("Exchange client not connected")
        return self._exchange

    @property
    def info(self) -> Info:
        if self._info is None:
            raise NetworkError("Info client not connected")
        return self._info

    @property
    def wallet_address(self) -> str:
        if self._account_address is None:
            raise NetworkError("Wallet address unavailable; connect() first")
        return self._account_address

    @property
    def wallet(self):
        if self._wallet is None:
            raise NetworkError("Wallet not initialised; connect() first")
        return self._wallet

    def is_connected(self) -> bool:
        return self._connected
