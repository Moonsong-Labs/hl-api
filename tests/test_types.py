"""Tests for hl_api.types utilities."""

from hl_api.types import VerificationPayload


def test_verification_payload_default() -> None:
    payload = VerificationPayload.default()
    assert payload.verification_type == 0
    assert payload.verification_data == b""
    assert payload.proof == []
    assert payload.as_tuple() == (0, b"", [])


def test_verification_payload_from_dict_hex() -> None:
    payload = VerificationPayload.from_dict(
        {
            "verificationType": 2,
            "verificationData": "0x1234",
            "proof": ["0x" + "00" * 32],
        }
    )

    assert payload.verification_type == 2
    assert payload.verification_data == bytes.fromhex("1234")
    assert len(payload.proof) == 1
    assert payload.proof[0] == bytes(32)


def test_verification_payload_from_dict_base64() -> None:
    payload = VerificationPayload.from_dict(
        {
            "verification_type": 3,
            "verification_data": "AQID",
            "proof": "AQID",
        }
    )

    assert payload.verification_type == 3
    assert payload.verification_data == b"\x01\x02\x03"
    assert len(payload.proof) == 1
    assert payload.proof[0] == b"\x01\x02\x03"


def test_verification_payload_from_dict_none() -> None:
    payload = VerificationPayload.from_dict(None)
    assert payload.verification_type == 0
    assert payload.verification_data == b""
    assert payload.proof == []
