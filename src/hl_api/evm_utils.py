"""Helper functions for EVM operations."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from hexbytes import HexBytes


def convert_perp_price(price_uint: int, sz_decimals: int) -> Decimal:
    """Convert a perp price from uint representation to Decimal."""
    exponent = 6 - int(sz_decimals)
    if exponent <= 0:
        raise ValueError("Size decimals too large for perp price conversion")
    return Decimal(price_uint) / (Decimal(10) ** exponent)


def convert_spot_price(price_uint: int, base_sz_decimals: int) -> Decimal:
    """Convert a spot price from uint representation to Decimal."""
    exponent = 8 - int(base_sz_decimals)
    if exponent >= 0:
        return Decimal(price_uint) / (Decimal(10) ** exponent)
    return Decimal(price_uint) * (Decimal(10) ** (-exponent))


def serialise_receipt(receipt: Any) -> Any:
    """Serialise web3 receipt objects into JSON-friendly structures."""
    if receipt is None:
        return None
    if isinstance(receipt, Mapping):
        return {key: serialise_receipt(value) for key, value in receipt.items()}
    if isinstance(receipt, Sequence) and not isinstance(
        receipt, str | bytes | bytearray | HexBytes
    ):
        return [serialise_receipt(item) for item in receipt]
    if isinstance(receipt, bytes | bytearray | HexBytes):
        return HexBytes(receipt).hex()
    return receipt
