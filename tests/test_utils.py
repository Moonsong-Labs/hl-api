"""Tests for utility functions."""

from decimal import Decimal

import pytest

from hl_api.exceptions import ValidationError
from hl_api.utils import (
    cloid_to_uint128,
    decode_tif,
    encode_tif,
    from_uint64,
    generate_cloid,
    to_uint64,
)


class TestUint64Conversion:
    """Test uint64 conversion functions."""

    def test_to_uint64_float(self):
        """Test converting float to uint64."""
        result = to_uint64(65000.0, 8)
        assert result == 6500000000000

    def test_to_uint64_decimal(self):
        """Test converting Decimal to uint64."""
        result = to_uint64(Decimal("65000"), 8)
        assert result == 6500000000000

    def test_to_uint64_int(self):
        """Test converting int to uint64."""
        result = to_uint64(65000, 8)
        assert result == 6500000000000

    def test_from_uint64(self):
        """Test converting uint64 back to Decimal."""
        result = from_uint64(6500000000000, 8)
        assert result == Decimal("65000")

    def test_to_uint64_negative_raises_error(self):
        """Test that negative value raises error."""
        with pytest.raises(ValidationError):
            to_uint64(-100, 8)

    def test_to_uint64_size(self):
        """Test converting size to uint64."""
        result = to_uint64(0.1, 8)
        assert result == 10000000

    def test_from_uint64_size(self):
        """Test converting uint64 back to size."""
        result = from_uint64(10000000, 8)
        assert result == Decimal("0.1")

    def test_size_negative_raises_error(self):
        """Test that negative size raises error."""
        with pytest.raises(ValidationError):
            to_uint64(-1, 8)


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
        # Check it's a hex string
        assert cloid.startswith("0x")
        # Convert and check range
        cloid_int = int(cloid, 16)
        assert 1 <= cloid_int <= 2**128 - 1

    def test_cloid_to_uint128_none(self):
        """Test converting None cloid."""
        assert cloid_to_uint128(None) == 0

    def test_cloid_to_uint128_valid(self):
        """Test converting valid cloid."""
        assert cloid_to_uint128("12345") == 12345
        assert cloid_to_uint128("0x3039") == 0x3039  # Test hex string

    def test_cloid_to_uint128_negative(self):
        """Test negative cloid raises error."""
        with pytest.raises(ValidationError):
            cloid_to_uint128("-1")

    def test_cloid_to_uint128_too_large(self):
        """Test cloid exceeding uint128 raises error."""
        with pytest.raises(ValidationError):
            cloid_to_uint128(str(2**128))
