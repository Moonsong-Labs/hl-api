"""Connection helpers for the HyperLiquid EVM client."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, cast

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import HTTPProvider, Web3
from web3.contract import Contract
from web3.middleware import SignAndSendRawMiddlewareBuilder
from web3.types import ChecksumAddress

from ..abi import HyperliquidBridgeStrategy_abi, HyperliquidStrategy_abi
from ..constants import Precompile
from ..exceptions import NetworkError, ValidationError
from .config import EVMClientConfig

logger = logging.getLogger(__name__)


class Web3Connections:
    """Manage Web3 providers, account middleware, and contract handles."""

    def __init__(self, config: EVMClientConfig):
        self.config = config
        self._hl_provider: HTTPProvider | None = None
        self._mn_provider: HTTPProvider | None = None
        self._web3: Web3 | None = None
        self._mainnet_web3: Web3 | None = None
        self._account: LocalAccount | None = None
        self._strategy_contract: Contract | None = None
        self._bridge_strategy_contract: Contract | None = None
        self._chain_id: int | None = None
        self._connected = False
        self._subvault_address: ChecksumAddress | None = None
        self._hype_token_index: int | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Initialise providers, contract handles and signing middleware."""

        try:
            signer = cast(LocalAccount, Account.from_key(self.config.private_key))  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover - defensive
            raise ValidationError(
                "Failed to derive signer account from provided private key",
                field="private_key",
                details={"error": str(exc)},
            ) from exc

        self._account = signer

        hl_provider, hl_web3 = self._build_web3_provider(
            self.config.hl_rpc_url, network_name="HyperLiquid"
        )
        self._hl_provider = hl_provider
        self._web3 = hl_web3
        self._apply_account_middleware(hl_web3, signer)

        contract = hl_web3.eth.contract(
            address=self.config.hl_strategy_address,
            abi=HyperliquidStrategy_abi,
        )
        self._strategy_contract = contract
        self._chain_id = hl_web3.eth.chain_id
        self._bridge_strategy_contract = None
        self._subvault_address = None

        mn_provider, mn_web3 = self._build_web3_provider(
            self.config.mn_rpc_url, network_name="Mainnet"
        )
        self._mn_provider = mn_provider
        self._mainnet_web3 = mn_web3
        self._apply_account_middleware(mn_web3, signer)

        try:
            self._hype_token_index = contract.functions.hypeTokenIndex().call()
        except Exception:  # pragma: no cover - defensive
            self._hype_token_index = None

        self._connected = True
        logger.info("Connected to HyperLiquid RPC at %s", self.config.hl_rpc_url)
        logger.info("Connected to mainnet RPC at %s", self.config.mn_rpc_url)

    def disconnect(self) -> None:
        self._hl_provider = None
        self._mn_provider = None
        self._web3 = None
        self._mainnet_web3 = None
        self._account = None
        self._strategy_contract = None
        self._bridge_strategy_contract = None
        self._chain_id = None
        self._connected = False
        self._subvault_address = None

    def is_connected(self) -> bool:
        return self._connected and self._web3 is not None and self._strategy_contract is not None

    def ensure_connected(self) -> None:
        if not self.is_connected():
            raise NetworkError("EVM connector is not connected", endpoint=self.config.hl_rpc_url)

        try:
            self.hyperliquid_web3
            self.account
            self.strategy_contract
        except NetworkError as exc:  # pragma: no cover - defensive
            raise NetworkError(
                "EVM connector is not connected", endpoint=self.config.hl_rpc_url
            ) from exc

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    @property
    def account(self) -> LocalAccount:
        if self._account is None:
            raise NetworkError(
                "Signer account is not initialised; call connect() first",
                endpoint=self.config.hl_rpc_url,
            )
        return self._account

    @property
    def strategy_contract(self) -> Contract:
        if self._strategy_contract is None:
            raise NetworkError(
                "Strategy contract not available; call connect() first",
                endpoint=self.config.hl_rpc_url,
            )
        return self._strategy_contract

    @property
    def hyperliquid_web3(self) -> Web3:
        if self._web3 is None:
            raise NetworkError(
                "HyperLiquid RPC provider not connected",
                endpoint=self.config.hl_rpc_url,
            )
        return self._web3

    @property
    def mainnet_web3(self) -> Web3:
        if self._mainnet_web3 is None:
            raise NetworkError(
                "Mainnet RPC provider not connected",
                endpoint=self.config.mn_rpc_url,
            )
        return self._mainnet_web3

    @property
    def hype_token_index(self) -> int | None:
        return self._hype_token_index

    @property
    def subvault_address(self) -> ChecksumAddress:
        if self._subvault_address is not None:
            return self._subvault_address

        self._subvault_address = self._load_and_validate_subvault()
        return self._subvault_address

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def ensure_bridge_contract(self, chain: str) -> Contract:
        if chain == "hyper":
            return self.strategy_contract

        if chain == "mainnet":
            if self._bridge_strategy_contract is None:
                web3 = self.mainnet_web3
                self._bridge_strategy_contract = web3.eth.contract(
                    address=self.config.bridge_strategy_address,
                    abi=HyperliquidBridgeStrategy_abi,
                )
            return self._bridge_strategy_contract

        raise ValidationError("Unknown bridge chain", field="chain", value=chain)

    def call_precompile(
        self,
        address: str | Precompile,
        input_types: Sequence[str],
        args: Sequence[Any],
        output_types: Sequence[str],
    ) -> tuple[Any, ...]:
        web3 = self.hyperliquid_web3
        call_data = abi_encode(list(input_types), list(args)) if input_types else b""
        addr_str = address.value if isinstance(address, Precompile) else address
        destination = Web3.to_checksum_address(addr_str)

        try:
            result = web3.eth.call({"to": destination, "data": call_data})
        except Exception as exc:  # pragma: no cover - defensive
            raise NetworkError(
                "Failed to execute L1 read precompile",
                endpoint=str(destination),
                details={"error": str(exc)},
            ) from exc

        if not output_types:
            return tuple()

        try:
            decoded = abi_decode(list(output_types), result)
        except Exception as exc:  # pragma: no cover - defensive
            raise NetworkError(
                "Failed to decode L1 read precompile response",
                endpoint=str(destination),
                details={"error": str(exc)},
            ) from exc

        return tuple(decoded)

    # ------------------------------------------------------------------
    # Internal wiring
    # ------------------------------------------------------------------
    def _build_web3_provider(self, rpc_url: str, *, network_name: str) -> tuple[HTTPProvider, Web3]:
        provider = HTTPProvider(rpc_url, request_kwargs={"timeout": self.config.request_timeout})
        web3 = Web3(provider)
        if not web3.is_connected():
            raise NetworkError(f"Unable to connect to {network_name} RPC", endpoint=rpc_url)
        return provider, web3

    def _apply_account_middleware(self, web3: Web3, account: LocalAccount) -> None:
        web3.middleware_onion.add(SignAndSendRawMiddlewareBuilder.build(account))  # type: ignore[arg-type]
        web3.eth.default_account = account.address

    def _load_and_validate_subvault(self) -> ChecksumAddress:
        contract = self.strategy_contract

        try:
            raw_subvault = contract.functions.subvault().call()
        except Exception as exc:  # pragma: no cover - defensive
            raise ValidationError(
                "Unable to read strategy subvault address",
                field="subvault",
                details={"error": str(exc)},
            ) from exc

        try:
            normalized = Web3.to_checksum_address(raw_subvault)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValidationError(
                "Strategy contract returned an invalid subvault",
                field="subvault",
                value=raw_subvault,
                details={"error": str(exc)},
            ) from exc

        subvault = Web3.to_checksum_address(normalized)
        if int(subvault, 16) == 0:
            raise ValidationError(
                "Strategy contract does not define a subvault address",
                field="subvault",
                value=subvault,
            )

        if not self._core_user_exists(subvault):
            raise ValidationError(
                "Strategy subvault is not registered on HyperLiquid core",
                field="subvault",
                value=subvault,
            )

        return subvault

    def _core_user_exists(self, address: ChecksumAddress) -> bool:
        (exists,) = self.call_precompile(
            Precompile.CORE_USER_EXISTS,
            ["address"],
            [address],
            ["bool"],
        )
        return bool(exists)
