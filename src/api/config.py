"""Configuration helpers for the Nexus API."""

from __future__ import annotations

import os
import time

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_HEALTH_URL = os.getenv("REDIS_HEALTH_URL", REDIS_URL)
API_START_TIME = time.monotonic()

ALLOWED_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]

SSE_KEEPALIVE_SECONDS = 25

CHANNEL_TO_EVENT = {
    "nexus.kpi": "metrics",
    "nexus.traffic": "traffic",
    "nexus.activity": "activity",
    "nexus.regions": "regions",
    "nexus.flows": "flows",
    "nexus.alerts": "alert",
    "nexus.platform": "platform",
    "nexus.health": "health",
    "nexus.geo": "geo",
}
