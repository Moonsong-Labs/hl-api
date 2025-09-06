"""Type definitions and data models for HyperLiquid Unified API."""

from dataclasses import dataclass
from enum import IntEnum


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


@dataclass
class OrderResponse:
    """Response from placing an order."""

    success: bool
    order_id: str | None = None
    cloid: str | None = None
    transaction_hash: str | None = None
    error: str | None = None
    raw_response: dict | None = None


@dataclass
class CancelResponse:
    """Response from cancelling an order."""

    success: bool
    cancelled_orders: int = 0
    transaction_hash: str | None = None
    error: str | None = None
    raw_response: dict | None = None


@dataclass
class TransferResponse:
    """Response from vault or USD class transfers."""

    success: bool
    amount: int | None = None
    transaction_hash: str | None = None
    error: str | None = None
    raw_response: dict | None = None


@dataclass
class DelegateResponse:
    """Response from token delegation."""

    success: bool
    validator: str | None = None
    amount: int | None = None
    transaction_hash: str | None = None
    error: str | None = None
    raw_response: dict | None = None


@dataclass
class StakingResponse:
    """Response from staking operations."""

    success: bool
    amount: int | None = None
    transaction_hash: str | None = None
    error: str | None = None
    raw_response: dict | None = None


@dataclass
class SendResponse:
    """Response from spot/perp send operations."""

    success: bool
    recipient: str | None = None
    amount: int | None = None
    transaction_hash: str | None = None
    error: str | None = None
    raw_response: dict | None = None


@dataclass
class FinalizeResponse:
    """Response from finalizing subaccount."""

    success: bool
    subaccount: str | None = None
    transaction_hash: str | None = None
    error: str | None = None
    raw_response: dict | None = None


@dataclass
class WalletResponse:
    """Response from adding API wallet."""

    success: bool
    wallet: str | None = None
    transaction_hash: str | None = None
    error: str | None = None
    raw_response: dict | None = None


@dataclass
class ApprovalResponse:
    """Response from builder fee approval."""

    success: bool
    builder: str | None = None
    fee: int | None = None
    nonce: int | None = None
    transaction_hash: str | None = None
    error: str | None = None
    raw_response: dict | None = None


# Type aliases for clarity
Price = int | float  # Will be converted to uint64 internally
Size = int | float  # Will be converted to uint64 internally
Address = str  # Ethereum address
Wei = int  # Wei amount for staking/delegation
