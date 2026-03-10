"""SSE formatting and Redis pub/sub fan-out."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from collections.abc import Callable
from typing import Any

from api.config import CHANNEL_TO_EVENT, SSE_KEEPALIVE_SECONDS
from api.services.redis_service import RedisService

# Map each SSE event name to the RedisService method that returns the
# correctly shaped payload (identical to the corresponding REST endpoint).
_EVENT_FETCHERS: dict[str, Callable[[RedisService], Any]] = {
    "metrics": lambda svc: svc.get_metrics(),
    "traffic": lambda svc: svc.get_traffic(),
    "activity": lambda svc: svc.get_activities(),
    "regions": lambda svc: svc.get_regions(),
    "flows": lambda svc: svc.get_flows(),
    "alert": lambda svc: svc.get_alerts(),
    "platform": lambda svc: svc.get_platform(),
    "health": lambda svc: svc.get_health(),
    "geo": lambda svc: svc.get_geo(),
}


class SSEManager:
    def __init__(self, redis_service: RedisService) -> None:
        self._redis = redis_service

    async def stream(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        channels = tuple(CHANNEL_TO_EVENT.keys())

        async def pump_messages() -> None:
            async with self._redis.pubsub(*channels) as pubsub:
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    channel = str(message["channel"])
                    event = CHANNEL_TO_EVENT.get(channel)
                    if event is None:
                        continue
                    fetcher = _EVENT_FETCHERS.get(event)
                    if fetcher is None:
                        continue
                    try:
                        data = await fetcher(self._redis)
                    except Exception:
                        continue
                    payload = json.dumps(data, separators=(",", ":"))
                    await queue.put(f"event: {event}\ndata: {payload}\n\n")

        producer = asyncio.create_task(pump_messages())
        try:
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer

    @staticmethod
    def encode_event(event: str, payload: dict | list) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
