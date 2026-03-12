"""WebSocket endpoint — real-time Redis pub/sub fan-out over WS."""

from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from api.dependencies import get_ws_manager
from api.services.ws_manager import WSManager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def ws_endpoint(
    ws: WebSocket,
    ws_manager: WSManager = Depends(get_ws_manager),
) -> None:
    await ws_manager.connect(ws)
    try:
        # Keep the handler alive so FastAPI doesn't close the socket.
        # The broadcast loop runs independently; here we just wait for the
        # client to disconnect (receive raises WebSocketDisconnect on close).
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(ws)
