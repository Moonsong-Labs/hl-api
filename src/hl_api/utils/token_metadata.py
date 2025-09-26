"""Utility functions for fetching and working with Hyperliquid token metadata."""

from __future__ import annotations

import logging
from typing import Any

import requests
from web3 import Web3

logger = logging.getLogger(__name__)


def fetch_token_metadata(testnet: bool = True, timeout: float = 10.0) -> dict[str, int]:
    url = (
        "https://api.hyperliquid-testnet.xyz/info"
        if testnet
        else "https://api.hyperliquid.xyz/info"
    )

    try:
        response = requests.post(
            url,
            json={"type": "spotMeta"},
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        data = response.json()
        tokens = data.get("tokens", [])

        token_map = {}
        for token in tokens:
            name = token.get("name")
            index = token.get("index")
            if name is not None and index is not None:
                token_map[name] = index
                logger.debug(f"Found token {name} with index {index}")

        logger.info(f"Fetched metadata for {len(token_map)} tokens")
        return token_map

    except requests.RequestException as e:
        logger.error(f"Failed to fetch token metadata: {e}")
        raise
    except (KeyError, TypeError) as e:
        logger.error(f"Unexpected response format: {e}")
        raise KeyError(f"Invalid response format from Hyperliquid API: {e}")


def get_token_info(testnet: bool = True, timeout: float = 10.0) -> list[dict[str, Any]]:
    url = (
        "https://api.hyperliquid-testnet.xyz/info"
        if testnet
        else "https://api.hyperliquid.xyz/info"
    )

    try:
        response = requests.post(
            url,
            json={"type": "spotMeta"},
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        data = response.json()
        return data.get("tokens", [])

    except requests.RequestException as e:
        logger.error(f"Failed to fetch token info: {e}")
        raise
    except (KeyError, TypeError) as e:
        logger.error(f"Unexpected response format: {e}")
        raise KeyError(f"Invalid response format from Hyperliquid API: {e}")


def calculate_precompile_address(token_index: int) -> str:
    if token_index < 0:
        raise ValueError(f"Token index must be non-negative, got {token_index}")

    prefix = 0x2000000000000000000000000000000000000000
    address_int = prefix + token_index

    address_hex = hex(address_int)[2:].zfill(40)
    address = f"0x{address_hex}"

    return Web3.to_checksum_address(address)


def get_token_evm_address(
    token_name: str, testnet: bool = True, timeout: float = 10.0
) -> str | None:
    tokens = get_token_info(testnet, timeout)

    for token in tokens:
        if token.get("name") == token_name:
            evm_contract = token.get("evmContract")
            if evm_contract:
                return Web3.to_checksum_address(evm_contract.get("address"))

    return None
