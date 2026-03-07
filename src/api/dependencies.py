"""Dependency providers for the Nexus API."""

from __future__ import annotations

from api.services.redis_service import RedisService
from api.services.sse_manager import SSEManager


redis_service = RedisService()
sse_manager = SSEManager(redis_service)


def get_redis_service() -> RedisService:
    return redis_service


def get_sse_manager() -> SSEManager:
    return sse_manager
