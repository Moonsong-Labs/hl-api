"""Constants and mappings for HyperLiquid unified API."""

# Asset symbol to index mapping for HyperLiquid
# These are the standard asset indices used by HyperLiquid Core
# https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/asset-ids
ASSET_INDICES = {
    "BTC": 0,
    "ETH": 4,
    "MATIC": 5,
}

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
