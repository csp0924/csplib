"""Tests for WebSocket manager."""

from unittest.mock import AsyncMock

import pytest

from csp_lib.gui.ws.manager import WebSocketManager


@pytest.mark.asyncio
class TestWebSocketManager:
    async def test_initial_state(self):
        mgr = WebSocketManager()
        assert mgr.connection_count == 0

    async def test_connect(self):
        mgr = WebSocketManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        assert mgr.connection_count == 1
        ws.accept.assert_called_once()

    async def test_disconnect(self):
        mgr = WebSocketManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        await mgr.disconnect(ws)
        assert mgr.connection_count == 0

    async def test_broadcast(self):
        mgr = WebSocketManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1)
        await mgr.connect(ws2)
        await mgr.broadcast({"type": "test", "data": "hello"})
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    async def test_broadcast_removes_dead_connections(self):
        mgr = WebSocketManager()
        ws_good = AsyncMock()
        ws_dead = AsyncMock()
        ws_dead.send_text.side_effect = Exception("Connection closed")
        await mgr.connect(ws_good)
        await mgr.connect(ws_dead)
        assert mgr.connection_count == 2
        await mgr.broadcast({"type": "test"})
        assert mgr.connection_count == 1

    async def test_broadcast_no_connections(self):
        mgr = WebSocketManager()
        await mgr.broadcast({"type": "test"})  # Should not raise
