from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import ALLOWED_ORIGINS, API_START_TIME
from api.dependencies import generator_manager, redis_service
from api.routes.generator import router as generator_router
from api.routes.events import router as events_router
from api.routes.snapshots import router as snapshots_router

app = FastAPI(title="Nexus API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(snapshots_router)
app.include_router(events_router)
app.include_router(generator_router)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await generator_manager.shutdown()
    await redis_service.close()


@app.get("/health")
async def health() -> dict[str, str | float]:
    return {
        "status": "ok",
        "redis": "connected" if await redis_service.ping() else "disconnected",
        "uptime": round(time.monotonic() - API_START_TIME, 2),
    }


@app.get("/docs-ready")
def docs_ready() -> dict[str, bool]:
    return {"docs": True}
