"""Utility functions for HyperLiquid Unified API."""

import random
from decimal import ROUND_HALF_UP, Decimal, localcontext

from web3 import Web3

from .exceptions import ValidationError
from .types import TIF


def to_uint64(value: float | Decimal | int, decimals: int = 8, field_name: str = "value") -> int:
    """Convert a value to uint64 representation.

    Args:
        value: Value as float, Decimal, or int
        decimals: Number of decimal places (default 8 for HyperLiquid)
        field_name: Name of field for error messages (default "value")

    Returns:
        Value as uint64

    Raises:
        ValidationError: If value is invalid
    """
    if value < 0:
        raise ValidationError(f"{field_name} cannot be negative", field=field_name, value=value)

    if isinstance(value, float | int):
        value = Decimal(str(value))

    multiplier = Decimal(10**decimals)
    uint_value = int(value * multiplier)

    if uint_value > 2**64 - 1:
        raise ValidationError(f"{field_name} exceeds uint64 maximum", field=field_name, value=value)

    return uint_value


def from_uint64(uint_value: int, decimals: int = 8) -> Decimal:
    """Convert uint64 to Decimal.

    Args:
        uint_value: Value as uint64
        decimals: Number of decimal places (default 8)

    Returns:
        Value as Decimal
    """
    divisor = Decimal(10**decimals)
    return Decimal(uint_value) / divisor


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
    return to_uint64(price, decimals, "price")


def uint64_to_price(uint_price: int, decimals: int = 8) -> Decimal:
    """Convert uint64 price to Decimal.

    Args:
        uint_price: Price as uint64
        decimals: Number of decimal places (default 8 for HyperLiquid)

    Returns:
        Price as Decimal
    """
    return from_uint64(uint_price, decimals)


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
    return to_uint64(size, decimals, "size")


def uint64_to_size(uint_size: int, decimals: int = 8) -> Decimal:
    """Convert uint64 size to Decimal.

    Args:
        uint_size: Size as uint64
        decimals: Number of decimal places (default 8)

    Returns:
        Size as Decimal
    """
    return from_uint64(uint_size, decimals)


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
    # Draw a random 128-bit integer using Python's RNG
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

    try:
        int(address[2:], 16)
    except ValueError:
        raise ValidationError(
            "Address contains invalid hex characters", field="address", value=address
        )

    return Web3.to_checksum_address(address)


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

    try:
        if isinstance(cloid, str) and cloid.startswith("0x"):
            cloid_int = int(cloid, 16)
        else:
            cloid_int = int(cloid)
    except (ValueError, TypeError):
        raise ValidationError("Cloid must be a valid integer string", field="cloid", value=cloid)

    if cloid_int < 0:
        raise ValidationError("Cloid cannot be negative", field="cloid", value=cloid)

    if cloid_int > 2**128 - 1:
        raise ValidationError("Cloid exceeds uint128 maximum", field="cloid", value=cloid)

    return cloid_int


def format_price_for_api(price: float | Decimal, sz_decimals: int, is_perp: bool = True) -> float:
    """Format price according to Hyperliquid API precision requirements.

    Applies the following rules:
    - Maximum 5 significant figures
    - For perps: Maximum (6 - sz_decimals) decimal places
    - For spot: Maximum (8 - sz_decimals) decimal places
    - Trailing zeros are removed

    Args:
        price: The price to format
        sz_decimals: Asset's size decimals from metadata
        is_perp: True for perpetual contracts, False for spot

    Returns:
        Properly formatted price as float

    Raises:
        ValidationError: If price is invalid
    """
    if price <= 0:
        raise ValidationError("Price must be positive", field="price", value=price)

    price_d = price if isinstance(price, Decimal) else Decimal(str(price))

    max_decimals = (6 - sz_decimals) if is_perp else (8 - sz_decimals)
    max_sig_figs = 5

    abs_price = price_d.copy_abs()
    exponent_sig = abs_price.adjusted() - (max_sig_figs - 1)

    if max_decimals >= 0:
        leading_zeros = max(0, -abs_price.adjusted() - 1)
        allowed_decimals = max_decimals + leading_zeros + (1 if abs_price < 1 else 0)
        exponent_dec = -allowed_decimals
    else:
        exponent_dec = -max_decimals

    final_exponent = max(exponent_sig, exponent_dec)

    with localcontext() as ctx:
        ctx.rounding = ROUND_HALF_UP
        ctx.prec = max(
            28,
            abs(price_d.adjusted()) + max_sig_figs + 4,
            abs(exponent_dec) + max_sig_figs + 4,
        )

        quantizer = Decimal(1).scaleb(final_exponent)
        price_d = price_d.quantize(quantizer, rounding=ROUND_HALF_UP)

    return float(price_d)
