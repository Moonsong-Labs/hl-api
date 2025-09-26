"""Utility functions for HyperLiquid Unified API."""

import random
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .exceptions import ValidationError
from .types import TIF


def to_uint64(value: float | Decimal | int, decimals: int = 8) -> int:
    """Convert a value to uint64 representation."""
    if value < 0:
        raise ValidationError("Value cannot be negative", field="value", value=value)

    if isinstance(value, float | int):
        value = Decimal(str(value))

    multiplier = Decimal(10**decimals)
    uint_value = int(value * multiplier)

    if uint_value > 2**64 - 1:
        raise ValidationError("Value exceeds uint64 maximum", field="value", value=value)

    return uint_value


def from_uint64(uint_value: int, decimals: int = 8) -> Decimal:
    """Convert uint64 to Decimal."""
    divisor = Decimal(10**decimals)
    return Decimal(uint_value) / divisor


def encode_tif(tif: str) -> int:
    """Encode Time In Force string to uint8."""
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
    """Decode uint8 TIF to string."""
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
    """Generate a random client order ID as hex string."""
    # Draw a random 128-bit integer using Python's RNG
    cloid_int = random.randint(1, 2**128 - 1)
    return f"0x{cloid_int:032x}"


def cloid_to_uint128(cloid: str | None) -> int:
    """Convert cloid to uint128, handling None."""
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
    """Format price according to Hyperliquid API precision requirements."""
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
