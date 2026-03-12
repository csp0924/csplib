"""WebSocket endpoint."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..dependencies import get_ws_manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WebSocket endpoint for real-time event streaming."""
    manager = get_ws_manager(ws)  # type: ignore[arg-type]  # WebSocket has same .app.state as Request
    await manager.connect(ws)
    try:
        while True:
            # Keep alive - receive client pings/messages
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
