# =============== Manager Alarm Tests - Persistence ===============
#
# AlarmPersistenceManager 單元測試
#
# 測試覆蓋：
# - subscribe/unsubscribe 設備訂閱
# - 斷線/重連事件處理
# - 告警觸發/解除事件處理
# - log 條件判斷

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from csp_lib.equipment.alarm import AlarmDefinition, AlarmEvent, AlarmEventType, AlarmLevel
from csp_lib.equipment.device.events import (
    EVENT_ALARM_CLEARED,
    EVENT_ALARM_TRIGGERED,
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    ConnectedPayload,
    DeviceAlarmPayload,
    DisconnectPayload,
)
from csp_lib.manager.alarm.persistence import AlarmPersistenceManager
from csp_lib.manager.alarm.schema import AlarmRecord, AlarmType
from csp_lib.notification import NotificationDispatcher, NotificationEvent


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


class MockRepository:
    """Mock AlarmRepository for testing"""

    def __init__(self):
        self.upsert = AsyncMock(return_value=("mock_id", True))
        self.resolve = AsyncMock(return_value=True)
        self.get_active_alarms = AsyncMock(return_value=[])
        self.get_active_by_device = AsyncMock(return_value=[])


# ======================== Subscribe/Unsubscribe Tests ========================


class TestAlarmPersistenceManagerSubscription:
    """訂閱/取消訂閱測試"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository()

    @pytest.fixture
    def manager(self, repository: MockRepository) -> AlarmPersistenceManager:
        return AlarmPersistenceManager(repository=repository)

    def test_subscribe_device(self, manager: AlarmPersistenceManager):
        """subscribe 應註冊所有事件處理器"""
        device = MockDevice("device_001")

        manager.subscribe(device)

        # 應有 4 個事件被註冊
        assert len(device._handlers.get(EVENT_DISCONNECTED, [])) == 1
        assert len(device._handlers.get(EVENT_CONNECTED, [])) == 1
        assert len(device._handlers.get(EVENT_ALARM_TRIGGERED, [])) == 1
        assert len(device._handlers.get(EVENT_ALARM_CLEARED, [])) == 1

    def test_subscribe_idempotent(self, manager: AlarmPersistenceManager):
        """重複 subscribe 同一設備應無效果"""
        device = MockDevice("device_001")

        manager.subscribe(device)
        manager.subscribe(device)  # 第二次

        # 仍只有 1 個處理器
        assert len(device._handlers.get(EVENT_DISCONNECTED, [])) == 1

    def test_unsubscribe_device(self, manager: AlarmPersistenceManager):
        """unsubscribe 應移除所有事件處理器"""
        device = MockDevice("device_001")

        manager.subscribe(device)
        manager.unsubscribe(device)

        # 所有處理器應被移除
        assert len(device._handlers.get(EVENT_DISCONNECTED, [])) == 0
        assert len(device._handlers.get(EVENT_CONNECTED, [])) == 0
        assert len(device._handlers.get(EVENT_ALARM_TRIGGERED, [])) == 0
        assert len(device._handlers.get(EVENT_ALARM_CLEARED, [])) == 0

    def test_unsubscribe_unsubscribed_no_error(self, manager: AlarmPersistenceManager):
        """取消訂閱未訂閱的設備不應報錯"""
        device = MockDevice("device_001")
        manager.unsubscribe(device)  # 不應拋錯

    def test_subscribe_multiple_devices(self, manager: AlarmPersistenceManager):
        """應能訂閱多個設備"""
        device1 = MockDevice("device_001")
        device2 = MockDevice("device_002")

        manager.subscribe(device1)
        manager.subscribe(device2)

        assert len(device1._handlers.get(EVENT_DISCONNECTED, [])) == 1
        assert len(device2._handlers.get(EVENT_DISCONNECTED, [])) == 1


# ======================== Disconnect/Connect Event Tests ========================


class TestAlarmPersistenceManagerDisconnect:
    """斷線/重連事件測試"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository()

    @pytest.fixture
    def manager(self, repository: MockRepository) -> AlarmPersistenceManager:
        return AlarmPersistenceManager(repository=repository)

    @pytest.mark.asyncio
    async def test_on_disconnected_creates_alarm(self, manager: AlarmPersistenceManager, repository: MockRepository):
        """斷線事件應建立 DISCONNECT 告警"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(
            device_id="device_001",
            reason="Connection timeout",
            consecutive_failures=5,
        )
        await device.emit(EVENT_DISCONNECTED, payload)

        # 應呼叫 upsert
        repository.upsert.assert_called_once()
        record: AlarmRecord = repository.upsert.call_args[0][0]

        assert record.alarm_key == "device_001:disconnect:DISCONNECT"
        assert record.device_id == "device_001"
        assert record.alarm_type == AlarmType.DISCONNECT
        assert record.name == "設備斷線"
        assert record.level == AlarmLevel.WARNING
        assert record.description == "Connection timeout"

    @pytest.mark.asyncio
    async def test_on_connected_resolves_alarm(self, manager: AlarmPersistenceManager, repository: MockRepository):
        """重連事件應解除 DISCONNECT 告警"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = ConnectedPayload(device_id="device_001")
        await device.emit(EVENT_CONNECTED, payload)

        # 應呼叫 resolve
        repository.resolve.assert_called_once()
        key, resolved_at = repository.resolve.call_args[0]

        assert key == "device_001:disconnect:DISCONNECT"
        assert isinstance(resolved_at, datetime)


# ======================== Device Alarm Event Tests ========================


class TestAlarmPersistenceManagerDeviceAlarm:
    """設備告警事件測試"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository()

    @pytest.fixture
    def manager(self, repository: MockRepository) -> AlarmPersistenceManager:
        return AlarmPersistenceManager(repository=repository)

    @pytest.mark.asyncio
    async def test_on_alarm_triggered_creates_alarm(self, manager: AlarmPersistenceManager, repository: MockRepository):
        """告警觸發事件應建立告警記錄"""
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

        repository.upsert.assert_called_once()
        record: AlarmRecord = repository.upsert.call_args[0][0]

        assert record.alarm_key == "device_001:device_alarm:OVER_TEMP"
        assert record.device_id == "device_001"
        assert record.alarm_type == AlarmType.DEVICE_ALARM
        assert record.name == "溫度過高"
        assert record.level == AlarmLevel.ALARM.value
        assert record.description == "設備溫度超過閾值"

    @pytest.mark.asyncio
    async def test_on_alarm_cleared_resolves_alarm(self, manager: AlarmPersistenceManager, repository: MockRepository):
        """告警解除事件應解除告警記錄"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        alarm_def = AlarmDefinition(code="OVER_TEMP", name="溫度過高", level=AlarmLevel.ALARM)
        alarm_event = AlarmEvent(alarm=alarm_def, event_type=AlarmEventType.CLEARED)
        payload = DeviceAlarmPayload(device_id="device_001", alarm_event=alarm_event)

        await device.emit(EVENT_ALARM_CLEARED, payload)

        repository.resolve.assert_called_once()
        key, resolved_at = repository.resolve.call_args[0]

        assert key == "device_001:device_alarm:OVER_TEMP"
        assert isinstance(resolved_at, datetime)


# ======================== Logging Tests ========================


class TestAlarmPersistenceManagerLogging:
    """日誌輸出測試"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository()

    @pytest.fixture
    def manager(self, repository: MockRepository) -> AlarmPersistenceManager:
        return AlarmPersistenceManager(repository=repository)

    @pytest.mark.asyncio
    async def test_create_alarm_logs_when_new(self, manager: AlarmPersistenceManager, repository: MockRepository):
        """新增告警時應記錄 log"""
        repository.upsert.return_value = ("mock_id", True)  # is_new = True

        with patch("csp_lib.manager.alarm.persistence.logger") as mock_logger:
            device = MockDevice("device_001")
            manager.subscribe(device)

            payload = DisconnectPayload(
                device_id="device_001",
                reason="test",
                consecutive_failures=1,
            )
            await device.emit(EVENT_DISCONNECTED, payload)

            mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_create_alarm_no_log_when_existing(
        self, manager: AlarmPersistenceManager, repository: MockRepository
    ):
        """告警已存在時不應記錄 log"""
        repository.upsert.return_value = ("existing_id", False)  # is_new = False

        with patch("csp_lib.manager.alarm.persistence.logger") as mock_logger:
            device = MockDevice("device_001")
            manager.subscribe(device)

            payload = DisconnectPayload(
                device_id="device_001",
                reason="test",
                consecutive_failures=1,
            )
            await device.emit(EVENT_DISCONNECTED, payload)

            # info 不應被呼叫（subscribe 時會呼叫一次，但 create_alarm 不應呼叫）
            # 檢查是否只有 subscribe 的 log
            calls = mock_logger.info.call_args_list
            assert len(calls) == 1  # 只有 subscribe 的 log
            assert "訂閱" in str(calls[0])

    @pytest.mark.asyncio
    async def test_resolve_alarm_logs_when_success(self, manager: AlarmPersistenceManager, repository: MockRepository):
        """解除告警成功時應記錄 log"""
        repository.resolve.return_value = True

        with patch("csp_lib.manager.alarm.persistence.logger") as mock_logger:
            device = MockDevice("device_001")
            manager.subscribe(device)

            payload = ConnectedPayload(device_id="device_001")
            await device.emit(EVENT_CONNECTED, payload)

            # 應有 resolve log
            info_calls = [str(c) for c in mock_logger.info.call_args_list]
            assert any("解除" in c for c in info_calls)

    @pytest.mark.asyncio
    async def test_resolve_alarm_no_log_when_not_found(
        self, manager: AlarmPersistenceManager, repository: MockRepository
    ):
        """解除告警失敗時不應記錄 log"""
        repository.resolve.return_value = False  # 找不到告警

        with patch("csp_lib.manager.alarm.persistence.logger") as mock_logger:
            device = MockDevice("device_001")
            manager.subscribe(device)

            payload = ConnectedPayload(device_id="device_001")
            await device.emit(EVENT_CONNECTED, payload)

            # 不應有 resolve log
            info_calls = [str(c) for c in mock_logger.info.call_args_list]
            assert not any("解除" in c for c in info_calls)


# ======================== Notification Dispatch Tests ========================


class TestAlarmPersistenceManagerNotification:
    """通知分發整合測試"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository()

    @pytest.fixture
    def mock_dispatcher(self) -> MagicMock:
        dispatcher = MagicMock(spec=NotificationDispatcher)
        dispatcher.dispatch = AsyncMock()
        dispatcher.from_alarm_record = NotificationDispatcher.from_alarm_record
        return dispatcher

    @pytest.mark.asyncio
    async def test_new_alarm_triggers_notification(self, repository: MockRepository, mock_dispatcher: MagicMock):
        """新告警應觸發 TRIGGERED 通知"""
        repository.upsert.return_value = ("mock_id", True)  # is_new = True
        manager = AlarmPersistenceManager(repository=repository, dispatcher=mock_dispatcher)

        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(
            device_id="device_001",
            reason="Connection timeout",
            consecutive_failures=5,
        )
        await device.emit(EVENT_DISCONNECTED, payload)

        mock_dispatcher.dispatch.assert_called_once()
        notification = mock_dispatcher.dispatch.call_args[0][0]
        assert notification.event == NotificationEvent.TRIGGERED
        assert notification.device_id == "device_001"

    @pytest.mark.asyncio
    async def test_existing_alarm_no_notification(self, repository: MockRepository, mock_dispatcher: MagicMock):
        """既存告警（is_new=False）不應觸發通知"""
        repository.upsert.return_value = ("existing_id", False)  # is_new = False
        manager = AlarmPersistenceManager(repository=repository, dispatcher=mock_dispatcher)

        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(
            device_id="device_001",
            reason="test",
            consecutive_failures=1,
        )
        await device.emit(EVENT_DISCONNECTED, payload)

        mock_dispatcher.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_alarm_triggers_resolved_notification(
        self, repository: MockRepository, mock_dispatcher: MagicMock
    ):
        """解除告警應觸發 RESOLVED 通知"""
        repository.resolve.return_value = True
        manager = AlarmPersistenceManager(repository=repository, dispatcher=mock_dispatcher)

        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = ConnectedPayload(device_id="device_001")
        await device.emit(EVENT_CONNECTED, payload)

        mock_dispatcher.dispatch.assert_called_once()
        notification = mock_dispatcher.dispatch.call_args[0][0]
        assert notification.event == NotificationEvent.RESOLVED
        assert notification.device_id == "device_001"

    @pytest.mark.asyncio
    async def test_resolve_failure_no_notification(self, repository: MockRepository, mock_dispatcher: MagicMock):
        """解除失敗時不應觸發通知"""
        repository.resolve.return_value = False
        manager = AlarmPersistenceManager(repository=repository, dispatcher=mock_dispatcher)

        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = ConnectedPayload(device_id="device_001")
        await device.emit(EVENT_CONNECTED, payload)

        mock_dispatcher.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_dispatcher_backward_compatible(self, repository: MockRepository):
        """無 dispatcher 時行為與現有完全相同"""
        repository.upsert.return_value = ("mock_id", True)
        manager = AlarmPersistenceManager(repository=repository)  # 無 dispatcher

        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(
            device_id="device_001",
            reason="test",
            consecutive_failures=1,
        )
        await device.emit(EVENT_DISCONNECTED, payload)

        repository.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatcher_failure_does_not_break_persistence(
        self, repository: MockRepository, mock_dispatcher: MagicMock
    ):
        """dispatcher 發送失敗不應影響告警持久化"""
        repository.upsert.return_value = ("mock_id", True)
        mock_dispatcher.dispatch = AsyncMock(side_effect=RuntimeError("dispatch failed"))
        mock_dispatcher.from_alarm_record = NotificationDispatcher.from_alarm_record
        manager = AlarmPersistenceManager(repository=repository, dispatcher=mock_dispatcher)

        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(
            device_id="device_001",
            reason="test",
            consecutive_failures=1,
        )
        # 不應拋錯
        await device.emit(EVENT_DISCONNECTED, payload)

        # 持久化仍成功
        repository.upsert.assert_called_once()
