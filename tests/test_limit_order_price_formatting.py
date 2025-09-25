"""Tests for limit order price formatting in the HyperLiquid EVM client."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest

from hl_api.evm import HLProtocolEVM
from hl_api.types import VerificationPayload
from hl_api.utils import format_price_for_api, price_to_uint64


@pytest.fixture()
def api() -> HLProtocolEVM:
    client = HLProtocolEVM(
        private_key="0x" + "1" * 64,
        hl_rpc_url="http://localhost:8545",
        mn_rpc_url="http://localhost:9545",
        hl_strategy_address="0x0000000000000000000000000000000000000001",
        bridge_strategy_address="0x0000000000000000000000000000000000000002",
        disable_call_verification=True,
    )

    client._ensure_connected = MagicMock()
    client._send_contract_transaction = MagicMock(
        return_value={"tx_hash": "0x1", "receipt": {"status": 1}}
    )

    return client


def _captured_price_uint(client: HLProtocolEVM) -> int:
    send_mock = cast(MagicMock, client._send_contract_transaction)
    call_args = send_mock.call_args
    assert call_args is not None, "Transaction was not sent"
    positional_args, _ = call_args
    sent_args = positional_args[1]
    assert len(sent_args) >= 2, "Unexpected contract argument payload"
    return sent_args[1]


def test_limit_order_formats_perp_price(api: HLProtocolEVM) -> None:
    api._resolve_asset_id = MagicMock(return_value=4)
    api._resolve_perp_sz_decimals = MagicMock(return_value=4)
    api._resolve_spot_base_sz_decimals = MagicMock(return_value=None)

    input_price = 2500.123456
    response = api.limit_order(asset="ETH", is_buy=True, limit_px=input_price, sz=1.0)

    assert response.success is True

    expected_price = format_price_for_api(input_price, 4, is_perp=True)
    assert _captured_price_uint(api) == price_to_uint64(expected_price)
    api._resolve_perp_sz_decimals.assert_called_once_with(4)
    api._resolve_spot_base_sz_decimals.assert_not_called()


def test_limit_order_formats_spot_price_when_perp_metadata_missing(api: HLProtocolEVM) -> None:
    api._resolve_asset_id = MagicMock(return_value=7)
    api._resolve_perp_sz_decimals = MagicMock(return_value=None)
    api._resolve_spot_base_sz_decimals = MagicMock(return_value=2)

    input_price = 12.3456789
    response = api.limit_order(asset="SOL/USDC", is_buy=False, limit_px=input_price, sz=0.5)

    assert response.success is True

    expected_price = format_price_for_api(input_price, 2, is_perp=False)
    assert _captured_price_uint(api) == price_to_uint64(expected_price)
    api._resolve_perp_sz_decimals.assert_called_once_with(7)
    api._resolve_spot_base_sz_decimals.assert_called_once_with(7)


def test_limit_order_falls_back_when_metadata_unavailable(api: HLProtocolEVM) -> None:
    api._resolve_asset_id = MagicMock(return_value=9)
    api._resolve_perp_sz_decimals = MagicMock(return_value=None)
    api._resolve_spot_base_sz_decimals = MagicMock(return_value=None)

    input_price = 123.456
    response = api.limit_order(asset="UNKNOWN", is_buy=True, limit_px=input_price, sz=1.0)

    assert response.success is True

    assert _captured_price_uint(api) == price_to_uint64(input_price)
    api._resolve_perp_sz_decimals.assert_called_once_with(9)
    api._resolve_spot_base_sz_decimals.assert_called_once_with(9)


def test_default_call_verification_returns_blank_payload() -> None:
    client = HLProtocolEVM(
        private_key="0x" + "2" * 64,
        hl_rpc_url="http://localhost:8545",
        mn_rpc_url="http://localhost:9545",
        hl_strategy_address="0x0000000000000000000000000000000000000001",
        bridge_strategy_address="0x0000000000000000000000000000000000000002",
    )

    payload = client._resolve_verification_payload("limit_order", {})

    assert payload.as_tuple() == VerificationPayload.default().as_tuple()
