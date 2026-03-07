"""Redis access helpers for REST snapshots and SSE fan-out."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.asyncio.connection import ConnectionPool

from api.config import REDIS_HEALTH_URL, REDIS_URL


def _loads_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


def _parse_number(value: str | None) -> int | float:
    if value in (None, ""):
        return 0
    if any(token in value for token in (".", "e", "E")):
        return float(value)
    return int(value)


class RedisService:
    def __init__(self) -> None:
        self._pool = ConnectionPool.from_url(REDIS_URL, decode_responses=True)
        self._health_pool = ConnectionPool.from_url(REDIS_HEALTH_URL, decode_responses=True)

    def client(self) -> Redis:
        return Redis(connection_pool=self._pool)

    def health_client(self) -> Redis:
        return Redis(connection_pool=self._health_pool)

    async def close(self) -> None:
        await self._pool.disconnect()
        await self._health_pool.disconnect()

    async def ping(self) -> bool:
        return bool(await self.health_client().ping())

    async def get_metrics(self) -> dict[str, Any]:
        payload = await self.client().hgetall("nexus:kpi:current")
        if not payload:
            return {
                "activeUsers": 0,
                "activeUsersTrend": 0.0,
                "revenue": 0.0,
                "revenueTrend": 0.0,
                "orders": 0,
                "ordersTrend": 0.0,
                "errorRate": 0.0,
                "errorRateTrend": 0.0,
                "latency": 0,
                "latencyTrend": 0.0,
                "updatedAt": 0,
            }
        return {
            "activeUsers": _parse_number(payload.get("activeUsers")),
            "activeUsersTrend": float(payload.get("activeUsersTrend", 0.0)),
            "revenue": float(payload.get("revenue", 0.0)),
            "revenueTrend": float(payload.get("revenueTrend", 0.0)),
            "orders": _parse_number(payload.get("orders")),
            "ordersTrend": float(payload.get("ordersTrend", 0.0)),
            "errorRate": float(payload.get("errorRate", 0.0)),
            "errorRateTrend": float(payload.get("errorRateTrend", 0.0)),
            "latency": _parse_number(payload.get("latency")),
            "latencyTrend": float(payload.get("latencyTrend", 0.0)),
            "updatedAt": _parse_number(payload.get("updatedAt")),
        }

    async def get_traffic(self) -> list[dict[str, Any]]:
        payload = await self.client().lrange("nexus:traffic:timeseries", 0, 20)
        if not payload:
            return []
        return list(reversed([json.loads(item) for item in payload]))

    async def get_activities(self) -> list[dict[str, Any]]:
        payload = await self.client().lrange("nexus:activity:feed", 0, 14)
        return [json.loads(item) for item in payload] if payload else []

    async def get_regions(self) -> list[dict[str, Any]]:
        return _loads_json(await self.client().get("nexus:regions:current"), [])

    async def get_flows(self) -> list[dict[str, Any]]:
        return _loads_json(await self.client().get("nexus:flows:current"), [])

    async def get_alerts(self) -> dict[str, Any]:
        rules = _loads_json(await self.client().get("nexus:alert:rules"), [])
        summary = await self.client().hgetall("nexus:alert:summary")
        if not summary:
            summary_payload = {
                "criticalCount": 0,
                "warningCount": 0,
                "healthyCount": 0,
                "criticalImpact": "Currently affecting 0% of users",
                "updatedAt": 0,
            }
        else:
            summary_payload = {
                "criticalCount": _parse_number(summary.get("criticalCount")),
                "warningCount": _parse_number(summary.get("warningCount")),
                "healthyCount": _parse_number(summary.get("healthyCount")),
                "criticalImpact": summary.get("criticalImpact", "Currently affecting 0% of users"),
                "updatedAt": _parse_number(summary.get("updatedAt")),
            }
        return {"rules": rules, "summary": summary_payload}

    async def get_platform(self) -> list[dict[str, Any]]:
        return _loads_json(await self.client().get("nexus:platform:breakdown"), [])

    async def get_health(self) -> dict[str, Any]:
        payload = await self.client().hgetall("nexus:health:current")
        if not payload:
            return {
                "cpu": 0.0,
                "memory": 0.0,
                "apiClusterStatus": "DOWN",
                "apiClusterScore": 0.0,
                "updatedAt": 0,
            }
        return {
            "cpu": float(payload.get("cpu", 0.0)),
            "memory": float(payload.get("memory", 0.0)),
            "apiClusterStatus": payload.get("apiClusterStatus", "DOWN"),
            "apiClusterScore": float(payload.get("apiClusterScore", 0.0)),
            "updatedAt": _parse_number(payload.get("updatedAt")),
        }

    async def get_geo(self) -> dict[str, Any]:
        payload = await self.client().hgetall("nexus:geo:header")
        if not payload:
            return {
                "uptime": 0.0,
                "globalLoad": "0 B/S",
                "globalLoadBytes": 0,
                "engineVersion": "V4-Orbit",
                "protocolStatus": "Unknown",
                "updatedAt": 0,
            }
        return {
            "uptime": float(payload.get("uptime", 0.0)),
            "globalLoad": payload.get("globalLoad", "0 B/S"),
            "globalLoadBytes": _parse_number(payload.get("globalLoadBytes")),
            "engineVersion": payload.get("engineVersion", "V4-Orbit"),
            "protocolStatus": payload.get("protocolStatus", "Unknown"),
            "updatedAt": _parse_number(payload.get("updatedAt")),
        }

    @asynccontextmanager
    async def pubsub(self, *channels: str):
        client = self.client()
        pubsub: PubSub = client.pubsub()
        await pubsub.subscribe(*channels)
        try:
            yield pubsub
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.close()
