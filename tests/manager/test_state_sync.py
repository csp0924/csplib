# =============== Manager State Tests - Sync ===============
#
# StateSyncManager 單元測試
#
# 測試覆蓋：
# - subscribe/unsubscribe 設備訂閱
# - read_complete 事件 → Redis Hash + Pub/Sub
# - connected/disconnected 事件 → Redis online + Pub/Sub
# - alarm_triggered/cleared 事件 → Redis Set + Pub/Sub

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.alarm import AlarmDefinition, AlarmEvent, AlarmEventType, AlarmLevel
from csp_lib.equipment.device.events import (
    EVENT_ALARM_CLEARED,
    EVENT_ALARM_TRIGGERED,
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    ConnectedPayload,
    DeviceAlarmPayload,
    DisconnectPayload,
    ReadCompletePayload,
)
from csp_lib.manager.state.sync import StateSyncManager


class MockDevice:
    """Mock AsyncModbusDevice for testing"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self._handlers: dict[str, list] = {}

    def on(self, event: str, handler):
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

        def cancel():
            if event in self._handlers and handler in self._handlers[event]:
                self._handlers[event].remove(handler)

        return cancel

    async def emit(self, event: str, payload):
        """Simulate event emission for testing"""
        for handler in self._handlers.get(event, []):
            await handler(payload)


class MockRedisClient:
    """Mock RedisClient for testing"""

    def __init__(self):
        self.hset = AsyncMock(return_value=1)
        self.set = AsyncMock(return_value=True)
        self.sadd = AsyncMock(return_value=1)
        self.srem = AsyncMock(return_value=1)
        self.publish = AsyncMock(return_value=1)
        self.expire = AsyncMock(return_value=True)


# ======================== Subscribe/Unsubscribe Tests ========================


class TestStateSyncManagerSubscription:
    """訂閱/取消訂閱測試"""

    @pytest.fixture
    def redis_client(self) -> MockRedisClient:
        return MockRedisClient()

    @pytest.fixture
    def manager(self, redis_client: MockRedisClient) -> StateSyncManager:
        return StateSyncManager(redis_client=redis_client)

    def test_subscribe_device(self, manager: StateSyncManager):
        """subscribe 應註冊所有事件處理器"""
        device = MockDevice("device_001")

        manager.subscribe(device)

        # 應有 5 個事件被註冊
        assert len(device._handlers.get(EVENT_READ_COMPLETE, [])) == 1
        assert len(device._handlers.get(EVENT_CONNECTED, [])) == 1
        assert len(device._handlers.get(EVENT_DISCONNECTED, [])) == 1
        assert len(device._handlers.get(EVENT_ALARM_TRIGGERED, [])) == 1
        assert len(device._handlers.get(EVENT_ALARM_CLEARED, [])) == 1

    def test_subscribe_idempotent(self, manager: StateSyncManager):
        """重複 subscribe 同一設備應無效果"""
        device = MockDevice("device_001")

        manager.subscribe(device)
        manager.subscribe(device)  # 第二次

        # 仍只有 1 個處理器
        assert len(device._handlers.get(EVENT_READ_COMPLETE, [])) == 1

    def test_unsubscribe_device(self, manager: StateSyncManager):
        """unsubscribe 應移除所有事件處理器"""
        device = MockDevice("device_001")

        manager.subscribe(device)
        manager.unsubscribe(device)

        # 所有處理器應被移除
        assert len(device._handlers.get(EVENT_READ_COMPLETE, [])) == 0
        assert len(device._handlers.get(EVENT_CONNECTED, [])) == 0
        assert len(device._handlers.get(EVENT_DISCONNECTED, [])) == 0
        assert len(device._handlers.get(EVENT_ALARM_TRIGGERED, [])) == 0
        assert len(device._handlers.get(EVENT_ALARM_CLEARED, [])) == 0


# ======================== Read Complete Tests ========================


class TestStateSyncManagerReadComplete:
    """read_complete 事件測試"""

    @pytest.fixture
    def redis_client(self) -> MockRedisClient:
        return MockRedisClient()

    @pytest.fixture
    def manager(self, redis_client: MockRedisClient) -> StateSyncManager:
        return StateSyncManager(redis_client=redis_client)

    @pytest.mark.asyncio
    async def test_on_read_complete_updates_hash(self, manager: StateSyncManager, redis_client: MockRedisClient):
        """read_complete 應更新 Redis Hash"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = ReadCompletePayload(
            device_id="device_001",
            values={"temperature": 25.5, "humidity": 60},
            duration_ms=50.0,
        )
        await device.emit(EVENT_READ_COMPLETE, payload)

        redis_client.hset.assert_called_once()
        call_args = redis_client.hset.call_args[0]
        assert call_args[0] == "device:device_001:state"
        assert call_args[1] == {"temperature": 25.5, "humidity": 60}

    @pytest.mark.asyncio
    async def test_on_read_complete_publishes(self, manager: StateSyncManager, redis_client: MockRedisClient):
        """read_complete 應發布至 data channel"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = ReadCompletePayload(
            device_id="device_001",
            values={"temperature": 25.5},
            duration_ms=50.0,
        )
        await device.emit(EVENT_READ_COMPLETE, payload)

        redis_client.publish.assert_called_once()
        call_args = redis_client.publish.call_args[0]
        assert call_args[0] == "channel:device:device_001:data"

        # 解析 message
        message = json.loads(call_args[1])
        assert "timestamp" in message
        assert message["values"] == {"temperature": 25.5}


# ======================== Connected/Disconnected Tests ========================


class TestStateSyncManagerConnection:
    """連線狀態事件測試"""

    @pytest.fixture
    def redis_client(self) -> MockRedisClient:
        return MockRedisClient()

    @pytest.fixture
    def manager(self, redis_client: MockRedisClient) -> StateSyncManager:
        return StateSyncManager(redis_client=redis_client)

    @pytest.mark.asyncio
    async def test_on_connected_sets_online(self, manager: StateSyncManager, redis_client: MockRedisClient):
        """connected 應設定 online=1"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = ConnectedPayload(device_id="device_001")
        await device.emit(EVENT_CONNECTED, payload)

        redis_client.set.assert_called_once()
        call_args = redis_client.set.call_args[0]
        assert call_args[0] == "device:device_001:online"
        assert call_args[1] == "1"

    @pytest.mark.asyncio
    async def test_on_connected_publishes(self, manager: StateSyncManager, redis_client: MockRedisClient):
        """connected 應發布至 status channel"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = ConnectedPayload(device_id="device_001")
        await device.emit(EVENT_CONNECTED, payload)

        redis_client.publish.assert_called_once()
        call_args = redis_client.publish.call_args[0]
        assert call_args[0] == "channel:device:device_001:status"

        message = json.loads(call_args[1])
        assert message["online"] is True

    @pytest.mark.asyncio
    async def test_on_disconnected_sets_offline(self, manager: StateSyncManager, redis_client: MockRedisClient):
        """disconnected 應設定 online=0"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(
            device_id="device_001",
            reason="timeout",
            consecutive_failures=5,
        )
        await device.emit(EVENT_DISCONNECTED, payload)

        redis_client.set.assert_called_once()
        call_args = redis_client.set.call_args[0]
        assert call_args[0] == "device:device_001:online"
        assert call_args[1] == "0"

    @pytest.mark.asyncio
    async def test_on_disconnected_publishes(self, manager: StateSyncManager, redis_client: MockRedisClient):
        """disconnected 應發布至 status channel"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(
            device_id="device_001",
            reason="timeout",
            consecutive_failures=5,
        )
        await device.emit(EVENT_DISCONNECTED, payload)

        redis_client.publish.assert_called_once()
        call_args = redis_client.publish.call_args[0]
        assert call_args[0] == "channel:device:device_001:status"

        message = json.loads(call_args[1])
        assert message["online"] is False
        assert message["reason"] == "timeout"


# ======================== Alarm Tests ========================


class TestStateSyncManagerAlarm:
    """告警事件測試"""

    @pytest.fixture
    def redis_client(self) -> MockRedisClient:
        return MockRedisClient()

    @pytest.fixture
    def manager(self, redis_client: MockRedisClient) -> StateSyncManager:
        return StateSyncManager(redis_client=redis_client)

    @pytest.mark.asyncio
    async def test_on_alarm_triggered_adds_to_set(self, manager: StateSyncManager, redis_client: MockRedisClient):
        """alarm_triggered 應新增至 Set"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        alarm_def = AlarmDefinition(
            code="OVER_TEMP",
            name="溫度過高",
            level=AlarmLevel.ALARM,
            description="設備溫度超過閾值",
        )
        alarm_event = AlarmEvent(alarm=alarm_def, event_type=AlarmEventType.TRIGGERED)
        payload = DeviceAlarmPayload(device_id="device_001", alarm_event=alarm_event)

        await device.emit(EVENT_ALARM_TRIGGERED, payload)

        redis_client.sadd.assert_called_once()
        call_args = redis_client.sadd.call_args[0]
        assert call_args[0] == "device:device_001:alarms"
        assert call_args[1] == "OVER_TEMP"

    @pytest.mark.asyncio
    async def test_on_alarm_triggered_publishes(self, manager: StateSyncManager, redis_client: MockRedisClient):
        """alarm_triggered 應發布至 alarm channel"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        alarm_def = AlarmDefinition(
            code="OVER_TEMP",
            name="溫度過高",
            level=AlarmLevel.ALARM,
        )
        alarm_event = AlarmEvent(alarm=alarm_def, event_type=AlarmEventType.TRIGGERED)
        payload = DeviceAlarmPayload(device_id="device_001", alarm_event=alarm_event)

        await device.emit(EVENT_ALARM_TRIGGERED, payload)

        redis_client.publish.assert_called_once()
        call_args = redis_client.publish.call_args[0]
        assert call_args[0] == "channel:device:device_001:alarm"

        message = json.loads(call_args[1])
        assert message["type"] == "triggered"
        assert message["alarm"]["code"] == "OVER_TEMP"

    @pytest.mark.asyncio
    async def test_on_alarm_cleared_removes_from_set(self, manager: StateSyncManager, redis_client: MockRedisClient):
        """alarm_cleared 應從 Set 移除"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        alarm_def = AlarmDefinition(code="OVER_TEMP", name="溫度過高", level=AlarmLevel.ALARM)
        alarm_event = AlarmEvent(alarm=alarm_def, event_type=AlarmEventType.CLEARED)
        payload = DeviceAlarmPayload(device_id="device_001", alarm_event=alarm_event)

        await device.emit(EVENT_ALARM_CLEARED, payload)

        redis_client.srem.assert_called_once()
        call_args = redis_client.srem.call_args[0]
        assert call_args[0] == "device:device_001:alarms"
        assert call_args[1] == "OVER_TEMP"

    @pytest.mark.asyncio
    async def test_on_alarm_cleared_publishes(self, manager: StateSyncManager, redis_client: MockRedisClient):
        """alarm_cleared 應發布至 alarm channel"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        alarm_def = AlarmDefinition(code="OVER_TEMP", name="溫度過高", level=AlarmLevel.ALARM)
        alarm_event = AlarmEvent(alarm=alarm_def, event_type=AlarmEventType.CLEARED)
        payload = DeviceAlarmPayload(device_id="device_001", alarm_event=alarm_event)

        await device.emit(EVENT_ALARM_CLEARED, payload)

        redis_client.publish.assert_called_once()
        call_args = redis_client.publish.call_args[0]
        assert call_args[0] == "channel:device:device_001:alarm"

        message = json.loads(call_args[1])
        assert message["type"] == "cleared"
        assert message["alarm"]["code"] == "OVER_TEMP"
