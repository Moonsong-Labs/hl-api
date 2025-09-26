"""Utility functions and constants for HyperLiquid API."""

from .constants import Precompile
from .core import (
    cloid_to_uint128,
    decode_tif,
    encode_tif,
    format_price_for_api,
    from_uint64,
    generate_cloid,
    to_uint64,
)
from .evm import (
    convert_perp_price,
    convert_spot_price,
    serialise_receipt,
)
from .token_metadata import (
    calculate_precompile_address,
    fetch_token_metadata,
    get_token_evm_address,
    get_token_info,
)

__all__ = [
    # Core utilities
    "to_uint64",
    "from_uint64",
    "encode_tif",
    "decode_tif",
    "generate_cloid",
    "cloid_to_uint128",
    "format_price_for_api",
    # Constants
    "Precompile",
    # EVM utilities
    "convert_perp_price",
    "convert_spot_price",
    "serialise_receipt",
    # Token metadata utilities
    "calculate_precompile_address",
    "fetch_token_metadata",
    "get_token_evm_address",
    "get_token_info",
]
