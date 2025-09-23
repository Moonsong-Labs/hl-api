"""Asset metadata and decimal resolution helpers for the EVM client."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from decimal import Decimal
from functools import lru_cache
from typing import Any, cast

import requests

from ..constants import Precompile
from ..evm_utils import convert_perp_price, convert_spot_price
from ..exceptions import NetworkError, ValidationError
from ..utils import format_price_for_api, uint64_to_price
from .config import EVMClientConfig
from .connections import Web3Connections

logger = logging.getLogger(__name__)


class AssetMetadataCache:
    """Maintain asset/token mappings and cached decimal metadata."""

    def __init__(
        self,
        config: EVMClientConfig,
        connections: Web3Connections,
        session: requests.Session,
    ) -> None:
        self._config = config
        self._connections = connections
        self._session = session
        self._asset_by_symbol: dict[str, int] = {}
        self._token_index_by_symbol: dict[str, int] = {}
        self._metadata_loaded = False

    # ------------------------------------------------------------------
    # Metadata hydration
    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._asset_by_symbol.clear()
        self._token_index_by_symbol.clear()
        self._metadata_loaded = False
        self.resolve_perp_sz_decimals.cache_clear()
        self.resolve_spot_base_sz_decimals.cache_clear()

    @property
    def metadata_loaded(self) -> bool:
        return self._metadata_loaded

    @property
    def asset_by_symbol(self) -> Mapping[str, int]:
        return self._asset_by_symbol

    @property
    def token_index_by_symbol(self) -> Mapping[str, int]:
        return self._token_index_by_symbol

    def load_from_info(self) -> None:
        """Fetch asset metadata directly from the HyperLiquid info endpoint."""

        payload = self._request_json({"type": "meta"})
        universe = payload.get("universe") if isinstance(payload, Mapping) else None
        if isinstance(universe, Sequence):
            for asset_id, entry in enumerate(universe):
                if not isinstance(entry, Mapping):
                    continue
                symbol = entry.get("name")
                if symbol:
                    self._asset_by_symbol[str(symbol).upper()] = asset_id
        else:
            logger.warning("Meta response missing 'universe' array")

        self._metadata_loaded = True
        if not self._asset_by_symbol:
            logger.warning("Meta info call did not produce any symbol mappings")

    def register_asset_entries(self, entries: Any) -> None:
        if isinstance(entries, Mapping):
            for symbol, value in entries.items():
                asset_id = self._coerce_int(value)
                if asset_id is not None:
                    self._asset_by_symbol[str(symbol).upper()] = asset_id
            return

        if isinstance(entries, Sequence):
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                symbol = (
                    entry.get("symbol")
                    or entry.get("name")
                    or entry.get("asset")
                    or entry.get("ticker")
                )
                if not symbol:
                    continue
                asset_id_val = (
                    entry.get("assetId")
                    or entry.get("asset_id")
                    or entry.get("id")
                    or entry.get("assetIndex")
                    or entry.get("index")
                )
                asset_id = self._coerce_int(asset_id_val)
                if asset_id is not None:
                    self._asset_by_symbol[str(symbol).upper()] = asset_id

    def register_token_entries(self, entries: Any) -> None:
        if isinstance(entries, Mapping):
            for symbol, value in entries.items():
                index = self._coerce_int(value)
                if index is not None:
                    self._token_index_by_symbol[str(symbol).upper()] = index
            return

        if isinstance(entries, Sequence):
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                symbol = entry.get("symbol") or entry.get("token") or entry.get("name")
                if not symbol:
                    continue
                index_val = entry.get("index") or entry.get("tokenIndex") or entry.get("id")
                index = self._coerce_int(index_val)
                if index is not None:
                    self._token_index_by_symbol[str(symbol).upper()] = index

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------
    def resolve_asset_id(self, asset: str) -> int:
        try:
            return int(asset, 0)
        except (TypeError, ValueError):
            symbol = str(asset).upper()
            if symbol in self._asset_by_symbol:
                return self._asset_by_symbol[symbol]
            if not self._metadata_loaded:
                try:
                    self.load_from_info()
                except NetworkError as exc:
                    logger.warning("Failed to load asset metadata from info endpoint: %s", exc)
                if symbol in self._asset_by_symbol:
                    return self._asset_by_symbol[symbol]
            raise ValidationError(
                f"Unknown asset symbol '{asset}'",
                field="asset",
                value=asset,
            )

    def resolve_token_index(self, token: str | int) -> int:
        if isinstance(token, int):
            return token
        try:
            return int(token, 0)
        except (TypeError, ValueError):
            symbol = str(token).upper()
            if symbol in self._token_index_by_symbol:
                return self._token_index_by_symbol[symbol]
            raise ValidationError(
                f"Unknown token identifier '{token}'",
                field="token",
                value=token,
            )

    @lru_cache(maxsize=128)
    def resolve_perp_sz_decimals(self, asset_id: int) -> int | None:
        try:
            result = self._connections.call_precompile(
                Precompile.PERP_ASSET_INFO,
                ["uint32"],
                [asset_id],
                ["(string,uint32,uint8,uint8,bool)"],
            )
            if result and len(result) > 0:
                result = result[0]
        except NetworkError as exc:
            logger.warning("perpAssetInfo NetworkError for asset %s: %s", asset_id, exc)
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("perpAssetInfo call failed for asset %s: %s", asset_id, exc)
            return None

        if not result:
            logger.error("Empty perp asset info for asset %s", asset_id)
            return None

        try:
            sz_decimals = int(result[2])
        except (TypeError, ValueError, IndexError):
            return None
        return sz_decimals

    @lru_cache(maxsize=128)
    def resolve_spot_base_sz_decimals(self, asset_id: int) -> int | None:
        try:
            spot_info = self._connections.call_precompile(
                Precompile.SPOT_INFO,
                ["uint32"],
                [asset_id],
                ["(string,uint64[2])"],
            )
            if spot_info and len(spot_info) > 0:
                spot_info = spot_info[0]
        except NetworkError:
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("spotInfo call failed for %s: %s", asset_id, exc)
            return None

        if not spot_info:
            return None

        try:
            tokens = spot_info[1]
        except (IndexError, TypeError):
            return None

        if not tokens:
            return None

        base_token_id = int(tokens[0])

        try:
            token_info = self._connections.call_precompile(
                Precompile.TOKEN_INFO,
                ["uint32"],
                [base_token_id],
                [
                    "string",
                    "uint64[]",
                    "uint64",
                    "address",
                    "address",
                    "uint8",
                    "uint8",
                    "int8",
                ],
            )
        except NetworkError:
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("tokenInfo call failed for token %s: %s", base_token_id, exc)
            return None

        if not token_info:
            return None

        try:
            sz_decimals = int(token_info[5])
        except (IndexError, TypeError, ValueError):
            return None

        return sz_decimals

    # ------------------------------------------------------------------
    # Price helpers
    # ------------------------------------------------------------------
    def format_limit_price(self, asset_id: int, price: float) -> float:
        sz_decimals = self.resolve_perp_sz_decimals(asset_id)
        if sz_decimals is not None:
            return format_price_for_api(price, sz_decimals, is_perp=True)

        base_sz_decimals = self.resolve_spot_base_sz_decimals(asset_id)
        if base_sz_decimals is not None:
            return format_price_for_api(price, base_sz_decimals, is_perp=False)

        return price

    def convert_market_prices(
        self,
        asset_id: int,
        mid_uint: int,
        bid_uint: int,
        ask_uint: int,
    ) -> tuple[Decimal, Decimal | None, Decimal | None]:
        sz_decimals = self.resolve_perp_sz_decimals(asset_id)
        if sz_decimals is not None:
            return (
                convert_perp_price(mid_uint, sz_decimals),
                convert_perp_price(bid_uint, sz_decimals) if bid_uint else None,
                convert_perp_price(ask_uint, sz_decimals) if ask_uint else None,
            )

        base_sz_decimals = self.resolve_spot_base_sz_decimals(asset_id)
        if base_sz_decimals is not None:
            return (
                convert_spot_price(mid_uint, base_sz_decimals),
                convert_spot_price(bid_uint, base_sz_decimals) if bid_uint else None,
                convert_spot_price(ask_uint, base_sz_decimals) if ask_uint else None,
            )

        return (
            uint64_to_price(mid_uint),
            uint64_to_price(bid_uint) if bid_uint else None,
            uint64_to_price(ask_uint) if ask_uint else None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _request_json(self, payload: Mapping[str, Any]) -> Any:
        response = self._session.request(
            "POST",
            cast(str, self._config.info_url),
            json=payload,
            timeout=self._config.request_timeout,
        )
        response.raise_for_status()
        return response.json()

    def _coerce_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            if isinstance(value, str):
                value = value.strip()
            return int(value, 0) if isinstance(value, str) else int(value)
        except (TypeError, ValueError):
            logger.debug("Failed to coerce value '%s' to int", value)
            return None
