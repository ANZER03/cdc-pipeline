"""SSE formatting and Redis pub/sub fan-out."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

from api.config import CHANNEL_TO_EVENT, SSE_KEEPALIVE_SECONDS
from api.services.redis_service import RedisService


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
                    payload = str(message["data"])
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
