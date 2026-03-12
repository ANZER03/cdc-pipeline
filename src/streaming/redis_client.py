"""Redis writer helpers for Nexus streaming jobs."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import redis

from streaming.config import REDIS_HOST, REDIS_PORT


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _stringify_mapping(mapping: dict[str, Any]) -> dict[str, str]:
    return {key: "" if value is None else str(value) for key, value in mapping.items()}


class NexusRedisWriter:
    """Thread-safe Redis writer with connection pooling for Spark jobs."""

    def __init__(
        self,
        host: str = REDIS_HOST,
        port: int = REDIS_PORT,
        *,
        db: int = 0,
        max_connections: int = 10,
    ) -> None:
        self._pool = redis.ConnectionPool(
            host=host,
            port=port,
            db=db,
            max_connections=max_connections,
            decode_responses=True,
        )

    def _client(self) -> redis.Redis:
        return redis.Redis(connection_pool=self._pool)

    def ping(self) -> bool:
        return bool(self._client().ping())

    def write_hash(
        self,
        key: str,
        mapping: dict[str, Any],
        *,
        channel: str | None = None,
        ttl: int | None = None,
    ) -> None:
        payload = _stringify_mapping(mapping)
        raw_payload = json.dumps(mapping, default=_json_default)
        client = self._client()
        pipe = client.pipeline()
        pipe.hset(key, mapping=payload)
        if ttl is not None:
            pipe.expire(key, ttl)
        if channel is not None:
            pipe.publish(channel, raw_payload)
        pipe.execute()

    def write_json(
        self,
        key: str,
        data: Any,
        *,
        channel: str | None = None,
        ttl: int | None = None,
    ) -> None:
        payload = json.dumps(data, default=_json_default)
        client = self._client()
        pipe = client.pipeline()
        pipe.set(key, payload)
        if ttl is not None:
            pipe.expire(key, ttl)
        if channel is not None:
            pipe.publish(channel, payload)
        pipe.execute()

    def push_to_list(
        self,
        key: str,
        item: dict[str, Any],
        *,
        max_len: int,
        channel: str | None = None,
    ) -> None:
        payload = json.dumps(item, default=_json_default)
        client = self._client()
        pipe = client.pipeline()
        pipe.lpush(key, payload)
        pipe.ltrim(key, 0, max_len - 1)
        if channel is not None:
            pipe.publish(channel, payload)
        pipe.execute()

    def read_hash(self, key: str) -> dict[str, str]:
        result = self._client().hgetall(key)
        return {str(field): str(value) for field, value in result.items()}

    def close(self) -> None:
        self._pool.disconnect()
