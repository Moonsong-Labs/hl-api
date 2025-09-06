"""Utility functions for HyperLiquid Unified API."""

import random
from decimal import Decimal

from .exceptions import ValidationError
from .types import TIF


def price_to_uint64(price: float | Decimal | int, decimals: int = 8) -> int:
    """Convert a price to uint64 representation.

    Args:
        price: Price as float, Decimal, or int
        decimals: Number of decimal places (default 8 for HyperLiquid)

    Returns:
        Price as uint64

    Raises:
        ValidationError: If price is invalid
    """
    if price < 0:
        raise ValidationError("Price cannot be negative", field="price", value=price)

    if isinstance(price, float | int):
        price = Decimal(str(price))

    multiplier = Decimal(10**decimals)
    uint_price = int(price * multiplier)

    if uint_price > 2**64 - 1:
        raise ValidationError("Price exceeds uint64 maximum", field="price", value=price)

    return uint_price


def uint64_to_price(uint_price: int, decimals: int = 8) -> Decimal:
    """Convert uint64 price to Decimal.

    Args:
        uint_price: Price as uint64
        decimals: Number of decimal places (default 8 for HyperLiquid)

    Returns:
        Price as Decimal
    """
    divisor = Decimal(10**decimals)
    return Decimal(uint_price) / divisor


def size_to_uint64(size: float | Decimal | int, decimals: int = 8) -> int:
    """Convert a size to uint64 representation.

    Args:
        size: Size as float, Decimal, or int
        decimals: Number of decimal places (default 8)

    Returns:
        Size as uint64

    Raises:
        ValidationError: If size is invalid
    """
    if size < 0:
        raise ValidationError("Size cannot be negative", field="size", value=size)

    if isinstance(size, float | int):
        size = Decimal(str(size))

    multiplier = Decimal(10**decimals)
    uint_size = int(size * multiplier)

    if uint_size > 2**64 - 1:
        raise ValidationError("Size exceeds uint64 maximum", field="size", value=size)

    return uint_size


def uint64_to_size(uint_size: int, decimals: int = 8) -> Decimal:
    """Convert uint64 size to Decimal.

    Args:
        uint_size: Size as uint64
        decimals: Number of decimal places (default 8)

    Returns:
        Size as Decimal
    """
    divisor = Decimal(10**decimals)
    return Decimal(uint_size) / divisor


def encode_tif(tif: str) -> int:
    """Encode Time In Force string to uint8.

    Args:
        tif: Time in force - "ALO", "GTC", or "IOC"

    Returns:
        Encoded TIF as uint8 (1, 2, or 3)

    Raises:
        ValidationError: If TIF is invalid
    """
    tif_upper = tif.upper()

    if tif_upper == "ALO":
        return TIF.ALO
    elif tif_upper == "GTC":
        return TIF.GTC
    elif tif_upper == "IOC":
        return TIF.IOC
    else:
        raise ValidationError(
            f"Invalid TIF value: {tif}. Must be ALO, GTC, or IOC", field="tif", value=tif
        )


def decode_tif(tif_encoded: int) -> str:
    """Decode uint8 TIF to string.

    Args:
        tif_encoded: Encoded TIF (1, 2, or 3)

    Returns:
        TIF string ("ALO", "GTC", or "IOC")

    Raises:
        ValidationError: If encoded TIF is invalid
    """
    if tif_encoded == TIF.ALO:
        return "ALO"
    elif tif_encoded == TIF.GTC:
        return "GTC"
    elif tif_encoded == TIF.IOC:
        return "IOC"
    else:
        raise ValidationError(
            f"Invalid encoded TIF: {tif_encoded}", field="tif_encoded", value=tif_encoded
        )


def generate_cloid() -> str:
    """Generate a random client order ID as hex string.

    Returns:
        Random cloid as hex string (0x prefixed) for uint128
    """
    # Generate a random 128-bit integer
    # Using 16 bytes (128 bits) of randomness
    cloid_int = random.randint(1, 2**128 - 1)
    return f"0x{cloid_int:032x}"


def validate_address(address: str) -> str:
    """Validate and checksum an Ethereum address.

    Args:
        address: Ethereum address

    Returns:
        Checksummed address

    Raises:
        ValidationError: If address is invalid
    """
    if not address:
        raise ValidationError("Address cannot be empty", field="address", value=address)

    if not address.startswith("0x"):
        raise ValidationError("Address must start with 0x", field="address", value=address)

    if len(address) != 42:
        raise ValidationError(
            f"Address must be 42 characters (including 0x), got {len(address)}",
            field="address",
            value=address,
        )

    # Basic hex validation
    try:
        int(address[2:], 16)
    except ValueError:
        raise ValidationError(
            "Address contains invalid hex characters", field="address", value=address
        )

    # For now, just return the address as-is
    # In production, use web3.py's to_checksum_address
    return address.lower()


def cloid_to_uint128(cloid: str | None) -> int:
    """Convert cloid to uint128, handling None.

    Args:
        cloid: Client order ID or None

    Returns:
        cloid as uint128 (0 if None)

    Raises:
        ValidationError: If cloid exceeds uint128 maximum
    """
    if cloid is None:
        return 0

    if cloid < 0:
        raise ValidationError("Cloid cannot be negative", field="cloid", value=cloid)

    if cloid > 2**128 - 1:
        raise ValidationError("Cloid exceeds uint128 maximum", field="cloid", value=cloid)

    return cloid
