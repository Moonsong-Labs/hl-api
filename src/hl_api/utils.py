"""Utility functions for HyperLiquid Unified API."""

import random
from decimal import Decimal

from web3 import Web3

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

    # Convert string to int (handle hex strings too)
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
    - Maximum 5 significant figures for the integer part
    - For perps: Maximum (6 - sz_decimals) decimal places
    - For spot: Maximum (8 - sz_decimals) decimal places
    - Trailing zeros are removed as per Hyperliquid docs

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

    from decimal import ROUND_HALF_UP

    if not isinstance(price, Decimal):
        price_decimal = Decimal(str(price))
    else:
        price_decimal = price

    max_decimals = (6 - sz_decimals) if is_perp else (8 - sz_decimals)

    if max_decimals >= 0:
        quantizer = Decimal(f"1e-{max_decimals}")
        rounded_price = price_decimal.quantize(quantizer, rounding=ROUND_HALF_UP)
    else:
        multiplier = Decimal(10 ** abs(max_decimals))
        rounded_price = (price_decimal / multiplier).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ) * multiplier

    # Now check the 5 significant figures constraint
    # According to Hyperliquid docs, this applies to the whole number, not just integer part
    price_str = str(rounded_price.normalize())

    digits_only = price_str.replace(".", "").replace("-", "").lstrip("0")

    if len(digits_only) > 5:
        # We have more than 5 significant figures, need to round
        # Find the position to round to
        if rounded_price >= 1:
            # For numbers >= 1, find how many digits in integer part
            int_part = int(abs(rounded_price))
            int_digits = len(str(int_part))

            if int_digits >= 5:
                # Round to remove decimal part and some integer digits
                round_to = 10 ** (int_digits - 5)
                rounded_price = (rounded_price / round_to).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                ) * round_to
            else:
                # Keep some decimal places
                decimal_places = 5 - int_digits
                # But respect the max_decimals constraint
                decimal_places = (
                    min(decimal_places, max_decimals) if max_decimals >= 0 else decimal_places
                )
                quantizer = Decimal(f"1e-{decimal_places}")
                rounded_price = rounded_price.quantize(quantizer, rounding=ROUND_HALF_UP)
        else:
            # For numbers < 1, we need to handle leading zeros after decimal
            # Find first non-zero digit position
            for i, char in enumerate(price_str):
                if char not in "0.-":
                    first_sig_pos = i
                    break

            # Figure out how many decimals that is
            decimal_pos = price_str.find(".")
            if decimal_pos >= 0:
                # Count zeros after decimal point
                leading_zeros = 0
                for char in price_str[decimal_pos + 1 :]:
                    if char == "0":
                        leading_zeros += 1
                    else:
                        break

                # We want 5 significant figures total
                decimal_places = leading_zeros + 5
                # But respect the max_decimals constraint
                decimal_places = (
                    min(decimal_places, max_decimals) if max_decimals >= 0 else decimal_places
                )
                quantizer = Decimal("1e-{}".format(decimal_places))
                rounded_price = rounded_price.quantize(quantizer, rounding=ROUND_HALF_UP)

    # Remove trailing zeros and return as float
    return float(rounded_price.normalize())
