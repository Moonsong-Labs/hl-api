from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from requests import Session

from hl_api.evm.config import FlexibleVaultConfig
from hl_api.evm.connections import Web3Connections
from hl_api.evm.proofs import FlexibleVaultProofResolver, ProofManager
from hl_api.exceptions import ValidationError


class DummyResponse:
    def __init__(
        self, payload: Any, *, status_code: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if not (200 <= self.status_code < 300):
            raise RuntimeError(f"status={self.status_code}")

    def json(self) -> Any:
        return self._payload


class DummySession(Session):
    def __init__(self, response: DummyResponse) -> None:
        super().__init__()
        self._response = response
        self.calls: list[tuple[str, float, bool]] = []

    def get(self, url: str, timeout: float, allow_redirects: bool) -> DummyResponse:  # type: ignore[override]
        self.calls.append((url, timeout, allow_redirects))
        return self._response


class DummyWeb3:
    def __init__(self, root: bytes) -> None:
        self.eth = SimpleNamespace(contract=lambda address, abi: DummyContract(root))


class DummyContract:
    def __init__(self, root: bytes) -> None:
        self.functions = SimpleNamespace(merkleRoot=lambda: DummyCall(root))


class DummyCall:
    def __init__(self, root: bytes) -> None:
        self._root = root

    def call(self) -> bytes:
        return self._root


@pytest.fixture(autouse=True)
def patch_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(hostname: str, *_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
        return [(None, None, None, ("93.184.216.34", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo, raising=False)


def _example_payload() -> dict[str, Any]:
    return {
        "title": "ethereum:tqETH:subvault0",
        "merkle_root": "0x8cacec5a1f3021c50d6e4f4ac80121df88f6fb6f636f981bcbd169eefaed3da3",
        "merkle_proofs": [
            {
                "description": "USDC.approve(TokenMessenger, any)",
                "verificationType": 3,
                "verificationData": "0x01",
                "proof": [
                    "0x309b822df17cf8c5bc2494ec60d9d2b59a75b6b698a6c86a51fcf37a7f7da974",
                ],
            }
        ],
    }


def test_fetch_requires_https() -> None:
    config = FlexibleVaultConfig(proof_url="http://example.com/proof.json")
    session = DummySession(DummyResponse({}))
    manager = ProofManager(session, request_timeout=1.0)

    with pytest.raises(ValidationError):
        manager.fetch(config)


def test_resolver_loads_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _example_payload()
    payload["merkle_proofs"][0]["description"] = "any_action"
    session = DummySession(DummyResponse(payload))
    merkle_root = bytes.fromhex(payload["merkle_root"][2:])
    connections = cast(
        Web3Connections,
        SimpleNamespace(
            hyperliquid_web3=DummyWeb3(merkle_root),
            mainnet_web3=DummyWeb3(merkle_root),
        ),
    )

    config = FlexibleVaultConfig(
        proof_url="https://example.com/proof.json",
        verifier_address="0x0000000000000000000000000000000000000001",
        check_merkle_root=True,
    )

    resolver = FlexibleVaultProofResolver(
        config,
        connections,
        session,
        request_timeout=1.0,
    )

    payload = resolver.resolve("any_action")
    assert payload.verification_type == 3
    assert payload.verification_data == "0x01"
    assert payload.as_tuple()[1] == bytes.fromhex("01")


def test_resolver_missing_description_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _example_payload()
    session = DummySession(DummyResponse(payload))
    connections = cast(
        Web3Connections,
        SimpleNamespace(
            hyperliquid_web3=DummyWeb3(bytes.fromhex(payload["merkle_root"][2:])),
            mainnet_web3=DummyWeb3(bytes.fromhex(payload["merkle_root"][2:])),
        ),
    )

    config = FlexibleVaultConfig(
        proof_url="https://example.com/proof.json",
    )

    resolver = FlexibleVaultProofResolver(
        config,
        connections,
        session,
        request_timeout=1.0,
    )

    with pytest.raises(ValidationError):
        resolver.resolve("special_action")
