"""
common/logger.py
EBAP — Structured logging factory.

Call get_logger(__name__) in any module to get a consistent,
pre-configured logger.
"""

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given module name."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    return logging.getLogger(name)
