from __future__ import annotations

import functools
import logging
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Callable, TypeVar, cast
from urllib import parse as urlparse

from hexbytes import HexBytes

from .exceptions import NetworkError, ValidationError

logger = logging.getLogger(__name__)


F = TypeVar('F', bound=Callable[..., Any])

def transaction_method(action_name: str, response_type: type) -> Callable[[F], F]:
    """Decorator to eliminate repetitive transaction boilerplate for EVM methods.

    The decorated method should return (function_name, args, context, extra_kwargs)
    where extra_kwargs contains any response-specific fields.

    Args:
        action_name: Name of the action for logging and context
        response_type: Response class to instantiate with results

    Returns:
        Decorator function that wraps transaction methods
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            extra_fields = {}  # Initialize early to avoid unbound variable issues
            try:
                self._ensure_connected()

                # Method returns function name, args, context, and extra response fields
                result = func(self, *args, **kwargs)
                if len(result) == 3:
                    function_name, contract_args, context = result
                    extra_fields = {}
                else:
                    function_name, contract_args, context, extra_fields = result

                # Send transaction using centralized method
                tx_result = self._send_contract_transaction(
                    function_name=function_name,
                    args=contract_args,
                    action=action_name,
                    context=context,
                )

                # Create appropriate response object
                receipt = tx_result.get("receipt")
                status = bool(receipt is None or receipt.get("status", 0) == 1)
                error_text = None if status else tx_result.get("error", "Transaction reverted")

                # Common response fields
                response_kwargs = {
                    "success": status,
                    "transaction_hash": tx_result["tx_hash"],
                    "error": error_text,
                    "raw_response": tx_result,
                }

                # Add type-specific fields
                response_kwargs.update(extra_fields)

                return response_type(**response_kwargs)

            except ValidationError as exc:
                error_kwargs = {"success": False, "error": str(exc)}
                error_kwargs.update(extra_fields)
                return response_type(**error_kwargs)
            except NetworkError as exc:
                error_kwargs = {
                    "success": False,
                    "error": str(exc),
                    "raw_response": getattr(exc, "details", None),
                }
                error_kwargs.update(extra_fields)
                return response_type(**error_kwargs)
            except Exception as exc:  # pragma: no cover
                logger.exception(f"Unexpected {action_name} failure")
                error_kwargs = {"success": False, "error": str(exc)}
                error_kwargs.update(extra_fields)
                return response_type(**error_kwargs)

        return cast(F, wrapper)

    return decorator


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
