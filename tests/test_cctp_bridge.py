from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from requests import Session
from web3.types import ChecksumAddress

from hl_api.evm.bridge import CCTPBridge
from hl_api.evm.config import EVMClientConfig
from hl_api.evm.connections import Web3Connections
from hl_api.exceptions import ValidationError
from hl_api.types import VerificationPayload

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from hl_api.evm.proofs import FlexibleVaultProofResolver


_BRIDGE_DESCRIPTIONS = (
    "USDC.approve(TokenMessenger, anyInt)",
    "TokenMessenger.depositForBurn(anyInt)",
)


class DummyResolver:
    def __init__(self, payloads: dict[str, VerificationPayload]) -> None:
        self._payloads = payloads
        self.calls: list[tuple[str, Any]] = []

    def resolve(self, description: str, context: Any) -> VerificationPayload:
        self.calls.append((description, context))
        payload = self._payloads.get(description)
        if payload is None:
            raise ValidationError("missing", field="description", value=description)
        return payload


class FailingResolver:
    def resolve(self, description: str, context: Any) -> VerificationPayload:  # type: ignore[override]
        raise ValidationError(
            "boom", field="description", value=description, details={"ctx": context}
        )


def _bridge_config() -> EVMClientConfig:
    return EVMClientConfig(
        private_key="0x00",
        hl_rpc_url="https://hyper",
        mn_rpc_url="https://mainnet",
        hl_strategy_address=cast(ChecksumAddress, "0x0000000000000000000000000000000000000001"),
        bridge_strategy_address=cast(ChecksumAddress, "0x0000000000000000000000000000000000000002"),
        request_timeout=1.0,
        iris_base_url="https://iris",
    )


def _bridge_instance(
    *,
    resolver: Any,
    disable_call_verification: bool,
) -> CCTPBridge:
    config = _bridge_config()
    connections = cast(Web3Connections, SimpleNamespace())
    session = Session()
    typed_resolver = cast("FlexibleVaultProofResolver | None", resolver)
    return CCTPBridge(
        config,
        connections,
        session,
        verification_resolver=typed_resolver,
        disable_call_verification=disable_call_verification,
    )


def test_verification_disabled_skips_resolver() -> None:
    payloads = {
        desc: VerificationPayload(verification_type=1, verification_data=b"", proof=[])
        for desc in _BRIDGE_DESCRIPTIONS
    }
    resolver = DummyResolver(payloads)
    bridge = _bridge_instance(resolver=resolver, disable_call_verification=True)

    payload_tuples = bridge._resolve_cctp_verification_payloads("mainnet_to_hyper", 1)

    assert len(payload_tuples) == len(_BRIDGE_DESCRIPTIONS)
    assert resolver.calls == []


def test_verification_fetches_payloads_when_enabled() -> None:
    payloads = {
        desc: VerificationPayload.from_dict(
            {
                "verificationType": index,
                "verificationData": f"0x{index:02x}",
                "proof": [f"0x{index:064x}"],
            }
        )
        for index, desc in enumerate(_BRIDGE_DESCRIPTIONS, start=1)
    }
    resolver = DummyResolver(payloads)
    bridge = _bridge_instance(resolver=resolver, disable_call_verification=False)

    payload_tuples = bridge._resolve_cctp_verification_payloads("mainnet_to_hyper", 25)

    assert [entry[0] for entry in payload_tuples] == [1, 2]
    assert len(resolver.calls) == len(_BRIDGE_DESCRIPTIONS)
    for (description, context), expected in zip(resolver.calls, _BRIDGE_DESCRIPTIONS):
        assert description == expected
        assert context["direction"] == "mainnet_to_hyper"
        assert context["amount_units"] == 25


def test_verification_error_wraps_details() -> None:
    resolver = FailingResolver()
    bridge = _bridge_instance(resolver=resolver, disable_call_verification=False)

    with pytest.raises(ValidationError) as excinfo:
        bridge._resolve_cctp_verification_payloads("mainnet_to_hyper", 10)

    err = excinfo.value
    assert err.value == _BRIDGE_DESCRIPTIONS[0]
    ctx = err.details.get("ctx")
    assert isinstance(ctx, dict)
    assert ctx["direction"] == "mainnet_to_hyper"
    assert ctx["amount_units"] == 10
