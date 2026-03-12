"""Dependency providers for the Nexus API."""

from __future__ import annotations

from api.services.generator_manager import GeneratorManager
from api.services.redis_service import RedisService
from api.services.sse_manager import SSEManager
from api.services.ws_manager import WSManager


redis_service = RedisService()
sse_manager = SSEManager(redis_service)
ws_manager = WSManager(redis_service)
generator_manager = GeneratorManager()


def get_redis_service() -> RedisService:
    return redis_service


def get_sse_manager() -> SSEManager:
    return sse_manager


def get_ws_manager() -> WSManager:
    return ws_manager


def get_generator_manager() -> GeneratorManager:
    return generator_manager
