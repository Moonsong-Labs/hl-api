"""Type definitions and data models for HyperLiquid Unified API."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any

from eth_typing import HexStr
from web3 import Web3


class ActionID(IntEnum):
    """CoreWriter Action IDs."""

    LIMIT_ORDER = 1
    VAULT_TRANSFER = 2
    TOKEN_DELEGATE = 3
    STAKING_DEPOSIT = 4
    STAKING_WITHDRAW = 5
    SPOT_SEND = 6
    PERP_SEND = 7
    USD_CLASS_TRANSFER_TO_PERP = 8
    USD_CLASS_TRANSFER_TO_SPOT = 9
    CANCEL_ORDER = 10
    FINALIZE_SUBACCOUNT = 11
    APPROVE_BUILDER_FEE = 12


class TIF(IntEnum):
    """Time in Force options for orders."""

    ALO = 1  # Add Liquidity Only
    GTC = 2  # Good Till Cancelled
    IOC = 3  # Immediate Or Cancel


class BridgeDirection(Enum):
    """Bridge direction for CCTP operations."""

    MAINNET_TO_HYPER = "mainnet_to_hyper"
    HYPER_TO_MAINNET = "hyper_to_mainnet"


@dataclass
class Response:
    """Generic response for all protocol operations."""

    success: bool
    transaction_hash: str | None = None
    error: str | None = None
    raw_response: dict[str, Any] | None = None
    order_id: str | None = None
    cloid: str | None = None
    cancelled_orders: int = 0
    amount: float | int | None = None
    recipient: str | None = None
    validator: str | None = None
    subaccount: str | None = None
    wallet: str | None = None
    builder: str | None = None
    fee: float | None = None
    nonce: int | None = None
    burn_tx_hash: str | None = None
    claim_tx_hash: str | None = None
    message: str | None = None
    attestation: str | None = None


Price = int | float  # Will be converted to uint64 internally
Size = int | float  # Will be converted to uint64 internally
Address = str  # Ethereum address
Wei = int  # Wei amount for staking/delegation


@dataclass
class VerificationPayload:
    """Serializable representation of IVerifier.VerificationPayload."""

    verification_type: int
    verification_data: bytes | str
    proof: list[bytes | str]

    @classmethod
    def default(cls) -> "VerificationPayload":
        """Return an empty payload using ONCHAIN_COMPACT (0)."""

        return cls(verification_type=0, verification_data=b"", proof=[])

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "VerificationPayload":
        """Construct a payload from a JSON-like dictionary."""

        if data is None:
            return cls.default()

        verification_type = int(
            data.get("verificationType") or data.get("verification_type") or data.get("type") or 0
        )

        raw_data = data.get("verificationData") or data.get("verification_data") or b""
        verification_data = _normalise_payload_value(raw_data)

        proof_items = data.get("proof") or data.get("proofs") or []
        proof = [_normalise_payload_value(item) for item in _iterable(proof_items)]

        return cls(
            verification_type=verification_type, verification_data=verification_data, proof=proof
        )

    def as_tuple(self) -> tuple[int, bytes, list[bytes]]:
        """Return the payload as tuple consumable by web3."""

        return (
            self.verification_type,
            _ensure_bytes(self.verification_data),
            [_ensure_bytes(item) for item in self.proof],
        )


def _normalise_payload_value(value: Any) -> bytes | str:
    """Return bytes or hex string without unnecessary conversion."""

    if value is None:
        return b""

    if isinstance(value, bytes):
        return value

    if isinstance(value, bytearray):
        return bytes(value)

    if isinstance(value, str):
        lower = value.lower()
        if lower.startswith("0x"):
            return lower

        try:
            import base64

            return base64.b64decode(value, validate=False)
        except Exception:
            return value

    if isinstance(value, Iterable):
        return bytes(value)

    if isinstance(value, int):
        length = (value.bit_length() + 7) // 8 or 1
        return value.to_bytes(length, byteorder="big")

    raise TypeError(f"Unsupported type for payload coercion: {type(value)!r}")


def _ensure_bytes(value: bytes | str) -> bytes:
    if isinstance(value, bytes):
        return value

    lower = value.lower()
    if lower.startswith("0x"):
        return Web3.to_bytes(hexstr=HexStr(lower))

    return value.encode("utf-8")


def _iterable(value: Any) -> Iterable:
    if isinstance(value, list | tuple | set):
        return value

    if value is None:
        return []

    return [value]
