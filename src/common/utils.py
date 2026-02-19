"""
common/utils.py
EBAP — Shared utility functions.

Provides:
  - sha256_hash: GDPR-compliant PII hashing
  - utc_now: timezone-aware UTC datetime helper
"""

import hashlib
from datetime import datetime, timezone


def sha256_hash(value: str) -> str:
    """Return a hex SHA-256 digest of the input string (for PII anonymization)."""
    return hashlib.sha256(value.encode()).hexdigest()


def utc_now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)
