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
    MethodNotImplementedError,
    NetworkError,
    ValidationError,
)
from .types import (
    TIF,
    ActionID,
    Address,
    ApprovalResponse,
    BridgeResponse,
    CancelResponse,
    DelegateResponse,
    FinalizeResponse,
    OrderResponse,
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
    from_uint64,
    generate_cloid,
    to_uint64,
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
    "BridgeResponse",
    "Price",
    "Size",
    "Address",
    "Wei",
    # Exceptions
    "HLProtocolError",
    "AuthenticationError",
    "NetworkError",
    "ValidationError",
    "MethodNotImplementedError",
    # Utility functions
    "to_uint64",
    "from_uint64",
    "encode_tif",
    "decode_tif",
    "generate_cloid",
    "cloid_to_uint128",
]
