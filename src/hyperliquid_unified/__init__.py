"""HyperLiquid Unified API - Consistent interface for Core and EVM.

This library provides a unified Python interface for interacting with
HyperLiquid through both the Core SDK and EVM CoreWriter precompile.
"""

from .base import HLProtocolBase
from .core import HLProtocolCore
from .evm import HLProtocolEVM
from .exceptions import (
    AuthenticationError,
    HLProtocolError,
    NetworkError,
    NotImplementedError,
    OrderError,
    TransferError,
    ValidationError,
)
from .types import (
    TIF,
    # Enums
    ActionID,
    Address,
    ApprovalResponse,
    CancelResponse,
    DelegateResponse,
    FinalizeResponse,
    # Response types
    OrderResponse,
    # Type aliases
    Price,
    SendResponse,
    Size,
    StakingResponse,
    TransferResponse,
    WalletResponse,
    Wei,
)
from .utils import (
    cloid_to_uint128,
    decode_tif,
    encode_tif,
    generate_cloid,
    price_to_uint64,
    size_to_uint64,
    uint64_to_price,
    uint64_to_size,
    validate_address,
)

__version__ = "0.1.0"

__all__ = [
    # Base classes
    "HLProtocolBase",
    "HLProtocolCore",
    "HLProtocolEVM",
    # Types and enums
    "ActionID",
    "TIF",
    "OrderResponse",
    "CancelResponse",
    "TransferResponse",
    "DelegateResponse",
    "StakingResponse",
    "SendResponse",
    "FinalizeResponse",
    "WalletResponse",
    "ApprovalResponse",
    "Price",
    "Size",
    "Address",
    "Wei",
    # Exceptions
    "HLProtocolError",
    "AuthenticationError",
    "OrderError",
    "TransferError",
    "NetworkError",
    "ValidationError",
    "NotImplementedError",
    # Utility functions
    "price_to_uint64",
    "uint64_to_price",
    "size_to_uint64",
    "uint64_to_size",
    "encode_tif",
    "decode_tif",
    "generate_cloid",
    "validate_address",
    "cloid_to_uint128",
]
