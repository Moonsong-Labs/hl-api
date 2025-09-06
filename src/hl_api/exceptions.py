"""Exception hierarchy for HyperLiquid Unified API."""

from typing import Any


class HLProtocolError(Exception):
    """Base exception for all HyperLiquid protocol errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(HLProtocolError):
    """Raised when authentication fails."""

    pass


class OrderError(HLProtocolError):
    """Raised when order operations fail."""

    def __init__(
        self,
        message: str,
        order_id: str | None = None,
        cloid: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.order_id = order_id
        self.cloid = cloid


class TransferError(HLProtocolError):
    """Raised when transfer operations fail."""

    def __init__(
        self,
        message: str,
        transfer_type: str | None = None,
        amount: int | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.transfer_type = transfer_type
        self.amount = amount


class NetworkError(HLProtocolError):
    """Raised when network/connection issues occur."""

    def __init__(
        self,
        message: str,
        endpoint: str | None = None,
        status_code: int | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.endpoint = endpoint
        self.status_code = status_code


class ValidationError(HLProtocolError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.field = field
        self.value = value


class NotImplementedError(HLProtocolError):
    """Raised when a method is not yet implemented."""

    def __init__(self, method_name: str):
        super().__init__(f"Method '{method_name}' is not yet implemented")
        self.method_name = method_name
