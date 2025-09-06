"""Tests for utility functions."""

from decimal import Decimal

import pytest

from hl_api.exceptions import ValidationError
from hl_api.utils import (
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


class TestPriceConversion:
    """Test price conversion functions."""

    def test_price_to_uint64_float(self):
        """Test converting float price to uint64."""
        result = price_to_uint64(65000.0)
        assert result == 6500000000000

    def test_price_to_uint64_decimal(self):
        """Test converting Decimal price to uint64."""
        result = price_to_uint64(Decimal("65000"))
        assert result == 6500000000000

    def test_price_to_uint64_int(self):
        """Test converting int price to uint64."""
        result = price_to_uint64(65000)
        assert result == 6500000000000

    def test_uint64_to_price(self):
        """Test converting uint64 back to price."""
        result = uint64_to_price(6500000000000)
        assert result == Decimal("65000")

    def test_price_negative_raises_error(self):
        """Test that negative price raises error."""
        with pytest.raises(ValidationError):
            price_to_uint64(-100)


class TestSizeConversion:
    """Test size conversion functions."""

    def test_size_to_uint64(self):
        """Test converting size to uint64."""
        result = size_to_uint64(0.1)
        assert result == 10000000

    def test_uint64_to_size(self):
        """Test converting uint64 back to size."""
        result = uint64_to_size(10000000)
        assert result == Decimal("0.1")

    def test_size_negative_raises_error(self):
        """Test that negative size raises error."""
        with pytest.raises(ValidationError):
            size_to_uint64(-1)


class TestTIFEncoding:
    """Test TIF encoding/decoding."""

    def test_encode_tif_alo(self):
        """Test encoding ALO."""
        assert encode_tif("ALO") == 1

    def test_encode_tif_gtc(self):
        """Test encoding GTC."""
        assert encode_tif("GTC") == 2

    def test_encode_tif_ioc(self):
        """Test encoding IOC."""
        assert encode_tif("IOC") == 3

    def test_encode_tif_lowercase(self):
        """Test encoding lowercase TIF."""
        assert encode_tif("gtc") == 2

    def test_encode_tif_invalid(self):
        """Test invalid TIF raises error."""
        with pytest.raises(ValidationError):
            encode_tif("INVALID")

    def test_decode_tif(self):
        """Test decoding TIF values."""
        assert decode_tif(1) == "ALO"
        assert decode_tif(2) == "GTC"
        assert decode_tif(3) == "IOC"

    def test_decode_tif_invalid(self):
        """Test invalid TIF code raises error."""
        with pytest.raises(ValidationError):
            decode_tif(99)


class TestCloid:
    """Test client order ID functions."""

    def test_generate_cloid(self):
        """Test generating client order ID."""
        cloid = generate_cloid()
        assert 1 <= cloid <= 2**128 - 1

    def test_cloid_to_uint128_none(self):
        """Test converting None cloid."""
        assert cloid_to_uint128(None) == 0

    def test_cloid_to_uint128_valid(self):
        """Test converting valid cloid."""
        assert cloid_to_uint128(12345) == 12345

    def test_cloid_to_uint128_negative(self):
        """Test negative cloid raises error."""
        with pytest.raises(ValidationError):
            cloid_to_uint128(-1)

    def test_cloid_to_uint128_too_large(self):
        """Test cloid exceeding uint128 raises error."""
        with pytest.raises(ValidationError):
            cloid_to_uint128(2**128)


class TestAddressValidation:
    """Test address validation."""

    def test_validate_address_valid(self):
        """Test validating correct address."""
        addr = "0x1234567890123456789012345678901234567890"
        result = validate_address(addr)
        assert result == addr.lower()

    def test_validate_address_no_prefix(self):
        """Test address without 0x prefix."""
        with pytest.raises(ValidationError):
            validate_address("1234567890123456789012345678901234567890")

    def test_validate_address_wrong_length(self):
        """Test address with wrong length."""
        with pytest.raises(ValidationError):
            validate_address("0x123")

    def test_validate_address_invalid_hex(self):
        """Test address with invalid hex characters."""
        with pytest.raises(ValidationError):
            validate_address("0xGGGG567890123456789012345678901234567890")

    def test_validate_address_empty(self):
        """Test empty address."""
        with pytest.raises(ValidationError):
            validate_address("")
