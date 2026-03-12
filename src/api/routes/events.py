"""SSE event endpoint for Redis pub/sub notifications."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.dependencies import get_sse_manager
from api.services.sse_manager import SSEManager


router = APIRouter(tags=["events"])


@router.get("/events")
async def events(sse_manager: SSEManager = Depends(get_sse_manager)) -> StreamingResponse:
    stream: AsyncIterator[str] = sse_manager.stream()
    return StreamingResponse(stream, media_type="text/event-stream")
