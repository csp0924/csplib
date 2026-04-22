"""Tests for csp_lib.equipment.device.event_bridge."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.equipment.device.event_bridge import AggregateCondition, EventBridge
from csp_lib.equipment.device.events import EVENT_CONNECTED


def _make_mock_device(device_id: str) -> MagicMock:
    """Create a mock device with working on() subscription."""
    device = MagicMock()
    device.device_id = device_id
    device._handlers: dict[str, list] = {}

    def on(event: str, handler):
        device._handlers.setdefault(event, []).append(handler)

        def cancel():
            if event in device._handlers:
                device._handlers[event].remove(handler)

        return cancel

    async def _emit(event: str, payload):
        for h in device._handlers.get(event, []):
            await h(payload)

    device.on = on
    device._emit = _emit
    return device


class TestAggregateCondition:
    def test_frozen_dataclass(self):
        cond = AggregateCondition(
            source_event="connected",
            target_event="all_connected",
            predicate=lambda p: True,
            debounce_seconds=0.5,
        )
        assert cond.source_event == "connected"
        assert cond.debounce_seconds == 0.5


class TestEventBridgeAttachDetach:
    def test_attach_subscribes_to_devices(self):
        cond = AggregateCondition(
            source_event=EVENT_CONNECTED,
            target_event="all_connected",
            predicate=lambda p: len(p) >= 2,
        )
        bridge = EventBridge([cond])
        d1 = _make_mock_device("pcs1")
        d2 = _make_mock_device("pcs2")

        bridge.attach([d1, d2])
        assert len(d1._handlers.get(EVENT_CONNECTED, [])) == 1
        assert len(d2._handlers.get(EVENT_CONNECTED, [])) == 1

    def test_detach_removes_subscriptions(self):
        cond = AggregateCondition(
            source_event=EVENT_CONNECTED,
            target_event="all_connected",
            predicate=lambda p: len(p) >= 2,
        )
        bridge = EventBridge([cond])
        d1 = _make_mock_device("pcs1")

        bridge.attach([d1])
        assert len(d1._handlers.get(EVENT_CONNECTED, [])) == 1

        bridge.detach()
        assert len(d1._handlers.get(EVENT_CONNECTED, [])) == 0


class TestEventBridgeAggregation:
    @pytest.mark.asyncio
    async def test_aggregate_fires_when_all_connected(self):
        """All devices connected → fires target_event."""
        handler = AsyncMock()
        cond = AggregateCondition(
            source_event=EVENT_CONNECTED,
            target_event="system_ready",
            predicate=lambda p: len(p) >= 2,
            debounce_seconds=0.05,  # Short debounce for test
        )
        bridge = EventBridge([cond])
        d1 = _make_mock_device("pcs1")
        d2 = _make_mock_device("pcs2")
        bridge.attach([d1, d2])
        bridge.on("system_ready", handler)

        # Simulate both devices connecting
        await d1._emit(EVENT_CONNECTED, {"device_id": "pcs1"})
        await d2._emit(EVENT_CONNECTED, {"device_id": "pcs2"})

        # Wait for debounce
        await asyncio.sleep(0.1)

        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aggregate_does_not_fire_partial(self):
        """Only one device connected → does not fire."""
        handler = AsyncMock()
        cond = AggregateCondition(
            source_event=EVENT_CONNECTED,
            target_event="system_ready",
            predicate=lambda p: len(p) >= 2,
            debounce_seconds=0.05,
        )
        bridge = EventBridge([cond])
        d1 = _make_mock_device("pcs1")
        d2 = _make_mock_device("pcs2")
        bridge.attach([d1, d2])
        bridge.on("system_ready", handler)

        # Only one device connects
        await d1._emit(EVENT_CONNECTED, {"device_id": "pcs1"})
        await asyncio.sleep(0.1)

        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_returns_cancel_function(self):
        cond = AggregateCondition(
            source_event=EVENT_CONNECTED,
            target_event="system_ready",
            predicate=lambda p: True,
            debounce_seconds=0.05,
        )
        bridge = EventBridge([cond])
        handler = AsyncMock()
        cancel = bridge.on("system_ready", handler)

        cancel()

        d = _make_mock_device("pcs1")
        bridge.attach([d])
        await d._emit(EVENT_CONNECTED, {"device_id": "pcs1"})
        await asyncio.sleep(0.1)

        handler.assert_not_awaited()


class TestEventBridgeDebounce:
    @pytest.mark.asyncio
    async def test_debounce_resets_on_rapid_events(self):
        """Rapid events should only trigger once after debounce settles."""
        call_count = 0

        async def counting_handler(payload):
            nonlocal call_count
            call_count += 1

        cond = AggregateCondition(
            source_event=EVENT_CONNECTED,
            target_event="system_ready",
            predicate=lambda p: len(p) >= 1,
            debounce_seconds=0.1,
        )
        bridge = EventBridge([cond])
        d1 = _make_mock_device("pcs1")
        bridge.attach([d1])
        bridge.on("system_ready", counting_handler)

        # Rapid events
        for _ in range(5):
            await d1._emit(EVENT_CONNECTED, {"device_id": "pcs1"})
            await asyncio.sleep(0.02)

        # Wait for debounce to settle
        await asyncio.sleep(0.2)

        # Should fire exactly once (edge detection: False→True)
        assert call_count == 1


class TestEventBridgeEdgeDetection:
    @pytest.mark.asyncio
    async def test_edge_detection_no_repeat_fire(self):
        """Same condition met repeatedly should only fire once (False→True edge)."""
        handler = AsyncMock()
        cond = AggregateCondition(
            source_event=EVENT_CONNECTED,
            target_event="system_ready",
            predicate=lambda p: len(p) >= 1,
            debounce_seconds=0.05,
        )
        bridge = EventBridge([cond])
        d1 = _make_mock_device("pcs1")
        bridge.attach([d1])
        bridge.on("system_ready", handler)

        # First event → triggers
        await d1._emit(EVENT_CONNECTED, {"device_id": "pcs1"})
        await asyncio.sleep(0.1)
        assert handler.await_count == 1

        # Same event again → should NOT trigger (already True)
        await d1._emit(EVENT_CONNECTED, {"device_id": "pcs1"})
        await asyncio.sleep(0.1)
        assert handler.await_count == 1  # Still 1, not 2


class TestEventBridgeDeviceProtocolAcceptance:
    """確保 attach() 簽名鬆綁為 DeviceProtocol 後，非 AsyncModbusDevice 的實作可直接注入。"""

    @pytest.mark.asyncio
    async def test_attach_accepts_minimal_device_protocol_impl(self):
        """手刻一個純 DeviceProtocol 實作（非 AsyncModbusDevice），attach 應可接受並正常觸發聚合。

        重點：attach 只透過 ``device_id`` 與 ``on()`` 互動；鬆綁後非 AsyncModbusDevice
        的設備抽象（如 DerivedDevice / RemoteSnapshotDevice）可直接注入。
        """
        from csp_lib.equipment.device.events import AsyncHandler

        class MinimalProtocolDevice:
            """只實作 attach 需要的兩個成員：device_id + on()。"""

            def __init__(self, device_id: str) -> None:
                self.device_id = device_id
                self._handlers: dict[str, list[AsyncHandler]] = {}

            def on(self, event, handler):
                self._handlers.setdefault(event, []).append(handler)

                def cancel():
                    self._handlers[event].remove(handler)

                return cancel

            async def fire(self, event, payload):
                for h in self._handlers.get(event, []):
                    await h(payload)

        d1 = MinimalProtocolDevice("pcs1")
        d2 = MinimalProtocolDevice("pcs2")

        handler = AsyncMock()
        cond = AggregateCondition(
            source_event=EVENT_CONNECTED,
            target_event="system_ready",
            predicate=lambda p: len(p) >= 2,
            debounce_seconds=0.05,
        )
        bridge = EventBridge([cond])

        # 型別層：attach 應接受 DeviceProtocol sequence（mypy / IDE 不會報錯）
        bridge.attach([d1, d2])
        bridge.on("system_ready", handler)

        await d1.fire(EVENT_CONNECTED, {"device_id": "pcs1"})
        await d2.fire(EVENT_CONNECTED, {"device_id": "pcs2"})

        # poll-until-condition 避免 sleep-then-assert race（bug-lesson: async-test-state-race）
        async def _wait_for(pred, timeout=1.0, interval=0.01):
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                if pred():
                    return
                await asyncio.sleep(interval)
            raise AssertionError(f"condition not met within {timeout}s")

        await _wait_for(lambda: handler.await_count >= 1)
        handler.assert_awaited_once()
