from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from urllib import parse as urlparse

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


def build_verification_url(base_url: str | None, action: str, context: Mapping[str, Any]) -> str:
    """Format a verification payload URL using query parameters from context."""

    url = base_url or ""
    if "{action}" in url:
        url = url.format(action=action)

    query_params = {
        key: value for key, value in context.items() if isinstance(value, str | int | float | bool)
    }
    if not query_params:
        return url

    encoded = urlparse.urlencode({k: str(v) for k, v in query_params.items()})
    parsed = urlparse.urlparse(url)
    separator = "&" if parsed.query else "?"
    return f"{url}{separator}{encoded}"


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


def summarise_param(value: Any) -> Any:
    """Produce readable logging output for contract arguments."""

    if isinstance(value, bytes | bytearray | HexBytes):
        hexstr = HexBytes(value).hex()
        if len(hexstr) > 70:
            return f"bytes[{len(value)}]={hexstr[:70]}..."
        return f"bytes[{len(value)}]={hexstr}"
    if isinstance(value, list | tuple | set):
        return [summarise_param(v) for v in value]
    if isinstance(value, Mapping):
        return {k: summarise_param(v) for k, v in value.items()}
    return value


__all__ = [
    "build_verification_url",
    "convert_perp_price",
    "convert_spot_price",
    "serialise_receipt",
    "summarise_param",
]
