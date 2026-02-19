"""
tests/unit/test_utils.py
Unit tests for src/common/utils.py — no external dependencies required.
"""

from src.common.utils import sha256_hash, utc_now
from datetime import datetime, timezone


def test_sha256_hash_returns_hex_string():
    result = sha256_hash("test-user-123")
    assert isinstance(result, str)
    assert len(result) == 64  # SHA-256 hex digest is always 64 chars


def test_sha256_hash_is_deterministic():
    value = "user-abc"
    assert sha256_hash(value) == sha256_hash(value)


def test_sha256_hash_different_inputs_produce_different_outputs():
    assert sha256_hash("user-1") != sha256_hash("user-2")


def test_utc_now_returns_aware_datetime():
    result = utc_now()
    assert isinstance(result, datetime)
    assert result.tzinfo is not None
    assert result.tzinfo == timezone.utc
