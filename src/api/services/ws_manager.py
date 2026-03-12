"""WebSocket broadcast manager — Redis pub/sub fan-out over WebSocket."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable
from typing import Any

from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from api.config import CHANNEL_TO_EVENT, SSE_KEEPALIVE_SECONDS
from api.services.redis_service import RedisService

# Reuse the same fetcher map as SSEManager: event name → shaped payload.
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


class WSManager:
    """
    Manages connected WebSocket clients and fans Redis pub/sub events to all
    of them.  Each message sent to clients is a JSON object:
        {"event": "<event_name>", "data": <shaped_payload>}
    The payload is identical to the corresponding REST snapshot endpoint.
    """

    def __init__(self, redis_service: RedisService) -> None:
        self._redis = redis_service
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._broadcaster: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
            if self._broadcaster is None or self._broadcaster.done():
                self._broadcaster = asyncio.create_task(self._broadcast_loop())
        # Send all 9 current snapshots immediately so the client doesn't have
        # to wait for the next Redis publish to see data.
        await self._send_initial_snapshot(ws)

    async def _send_initial_snapshot(self, ws: WebSocket) -> None:
        for event, fetcher in _EVENT_FETCHERS.items():
            try:
                data = await fetcher(self._redis)
                text = json.dumps({"event": event, "data": data}, separators=(",", ":"))
                await ws.send_text(text)
            except Exception:
                continue

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    # ------------------------------------------------------------------
    # Broadcast loop — single task shared across all connected clients
    # ------------------------------------------------------------------

    async def _broadcast_loop(self) -> None:
        channels = tuple(CHANNEL_TO_EVENT.keys())
        async with self._redis.pubsub(*channels) as pubsub:
            async for message in pubsub.listen():
                async with self._lock:
                    if not self._clients:
                        # No clients left — stop the loop; a new task will be
                        # spawned when the next client connects.
                        break
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
                text = json.dumps({"event": event, "data": data}, separators=(",", ":"))
                await self._fan_out(text)

    async def _fan_out(self, text: str) -> None:
        """Send text to every connected client; silently drop dead sockets."""
        async with self._lock:
            targets = list(self._clients)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(text)
                else:
                    dead.append(ws)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
