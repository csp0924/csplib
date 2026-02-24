"""WebSocket connection manager."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    """
    Manages WebSocket connections and broadcasts messages.

    Thread-safe via asyncio.Lock.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        """Accept and register a WebSocket connection."""
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients."""
        if not self._connections:
            return

        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []

        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.discard(ws)

    @property
    def connection_count(self) -> int:
        """Number of active connections."""
        return len(self._connections)
