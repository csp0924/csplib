"""Tests for WebSocket EventBridge."""

import pytest

from csp_lib.gui.ws.events import EventBridge
from csp_lib.gui.ws.manager import WebSocketManager


@pytest.mark.asyncio
class TestEventBridge:
    async def test_attach_registers_handlers(self, mock_system_controller):
        ws_manager = WebSocketManager()
        bridge = EventBridge(mock_system_controller, ws_manager, snapshot_interval=100)
        await bridge.attach()
        # Each device gets 6 event handlers
        for device in mock_system_controller.registry.all_devices:
            assert device.on.call_count == 6
        await bridge.detach()

    async def test_detach_cancels_handlers(self, mock_system_controller):
        ws_manager = WebSocketManager()
        bridge = EventBridge(mock_system_controller, ws_manager, snapshot_interval=100)
        await bridge.attach()
        cancel_count = sum(device.on.call_count for device in mock_system_controller.registry.all_devices)
        await bridge.detach()
        # All cancel functions should have been called (one per .on() registration)
        assert cancel_count == 12  # 2 devices x 6 events

    async def test_build_snapshot(self, mock_system_controller):
        ws_manager = WebSocketManager()
        bridge = EventBridge(mock_system_controller, ws_manager, snapshot_interval=100)
        snapshot = bridge._build_snapshot()
        assert snapshot["type"] == "snapshot"
        assert "devices" in snapshot["data"]
        assert "mode" in snapshot["data"]
        assert len(snapshot["data"]["devices"]) == 2

    async def test_snapshot_includes_mode_state(self, mock_system_controller):
        ws_manager = WebSocketManager()
        bridge = EventBridge(mock_system_controller, ws_manager, snapshot_interval=100)
        snapshot = bridge._build_snapshot()
        mode_data = snapshot["data"]["mode"]
        assert "base_mode_names" in mode_data
        assert "active_override_names" in mode_data
        assert "effective_mode" in mode_data
