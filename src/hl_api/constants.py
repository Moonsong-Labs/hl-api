"""Constants and mappings for HyperLiquid unified API."""

from enum import Enum

# Asset symbol to index mapping for HyperLiquid
# These are the standard asset indices used by HyperLiquid Core
# https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/asset-ids
ASSET_INDICES = {
    "BTC": 0,
    "ETH": 4,
    "MATIC": 5,
}


class Precompile(str, Enum):
    """L1 Read precompile addresses for HyperLiquid EVM."""

    COREWRITER = "0x3333333333333333333333333333333333333333"
    MARK_PX = "0x0000000000000000000000000000000000000806"
    BBO = "0x000000000000000000000000000000000000080e"
    PERP_ASSET_INFO = "0x000000000000000000000000000000000000080a"
    SPOT_INFO = "0x000000000000000000000000000000000000080b"
    TOKEN_INFO = "0x000000000000000000000000000000000000080C"
    CORE_USER_EXISTS = "0x0000000000000000000000000000000000000810"

INDEX_TO_SYMBOL = {v: k for k, v in ASSET_INDICES.items()}


def get_asset_index(symbol: str) -> int:
    """Get asset index from symbol.

    Args:
        symbol: Asset symbol (e.g., "BTC", "ETH")

    Returns:
        Asset index

    Raises:
        ValueError: If symbol is not found
    """
    symbol = symbol.upper()
    if symbol not in ASSET_INDICES:
        raise ValueError(f"Unknown asset symbol: {symbol}")
    return ASSET_INDICES[symbol]


def get_asset_symbol(index: int) -> str:
    """Get asset symbol from index.

    Args:
        index: Asset index

    Returns:
        Asset symbol

    Raises:
        ValueError: If index is not found
    """
    if index not in INDEX_TO_SYMBOL:
        raise ValueError(f"Unknown asset index: {index}")
    return INDEX_TO_SYMBOL[index]
