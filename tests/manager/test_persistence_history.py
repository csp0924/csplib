# =============== Manager Alarm Tests - History (v0.8.2) ===============
#
# AlarmPersistenceManager + buffered_uploader 整合測試
#
# 測試覆蓋：
# - buffered_uploader=None 時行為完全等同 v0.8.1（回歸保護）
# - buffered_uploader 提供時，_create_alarm 成功後呼叫 write_immediate
#   （collection=config.history_collection）
# - _resolve_alarm 成功後同樣呼叫 write_immediate（帶 event="resolved"）
# - buffered_uploader.write_immediate 拋例外時主流程仍正常（failure tolerance）
# - AlarmPersistenceConfig.history_collection 客製化時正確傳遞

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

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
from csp_lib.manager.alarm.config import AlarmPersistenceConfig
from csp_lib.manager.alarm.persistence import AlarmPersistenceManager
from csp_lib.mongo.writer import WriteResult


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
        for handler in self._handlers.get(event, []):
            await handler(payload)


class MockRepository:
    """Mock AlarmRepository"""

    def __init__(self, *, is_new: bool = True, resolve_success: bool = True):
        self.upsert = AsyncMock(return_value=("mock_id", is_new))
        self.resolve = AsyncMock(return_value=resolve_success)
        self.get_active_alarms = AsyncMock(return_value=[])
        self.get_active_by_device = AsyncMock(return_value=[])


def _make_buffered_uploader(success: bool = True) -> MagicMock:
    """建立 mock LocalBufferedUploader（具 write_immediate AsyncMock）"""
    buffered = MagicMock()
    buffered.write_immediate = AsyncMock(return_value=WriteResult(success=success, inserted_count=1 if success else 0))
    buffered.register_collection = MagicMock()
    buffered.enqueue = AsyncMock()
    return buffered


# ======================== 回歸保護：buffered_uploader=None ========================


class TestAlarmPersistenceWithoutBufferedUploader:
    """buffered_uploader=None 時行為應完全等同 v0.8.1"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository()

    @pytest.fixture
    def manager(self, repository: MockRepository) -> AlarmPersistenceManager:
        # 明確不傳 buffered_uploader，驗證 None default
        return AlarmPersistenceManager(repository=repository)

    async def test_no_buffered_uploader_create_alarm_normal(
        self, manager: AlarmPersistenceManager, repository: MockRepository
    ):
        """無 buffered_uploader 時，建立告警流程應正常（不因缺少 buffer 而失敗）"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(device_id="device_001", reason="timeout", consecutive_failures=3)
        await device.emit(EVENT_DISCONNECTED, payload)

        # repository.upsert 被呼叫
        repository.upsert.assert_awaited_once()

    async def test_no_buffered_uploader_resolve_alarm_normal(
        self, manager: AlarmPersistenceManager, repository: MockRepository
    ):
        """無 buffered_uploader 時，解除告警流程應正常"""
        device = MockDevice("device_001")
        manager.subscribe(device)

        await device.emit(EVENT_CONNECTED, ConnectedPayload(device_id="device_001"))

        repository.resolve.assert_awaited_once()


# ======================== buffered_uploader 提供：create_alarm 路徑 ========================


class TestAlarmPersistenceHistoryCreate:
    """buffered_uploader 提供時，_create_alarm 成功後應寫 history"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository(is_new=True)

    async def test_disconnect_writes_history_triggered(self, repository: MockRepository):
        """斷線告警（新）→ history collection 寫入 event='triggered'"""
        buffered = _make_buffered_uploader()
        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(device_id="device_001", reason="timeout", consecutive_failures=3)
        await device.emit(EVENT_DISCONNECTED, payload)

        # 預設 history_collection = "alarm_history"
        buffered.write_immediate.assert_awaited_once()
        call = buffered.write_immediate.await_args
        assert call.args[0] == "alarm_history"
        doc = call.args[1]
        assert doc["device_id"] == "device_001"
        assert doc["event"] == "triggered"
        assert doc["alarm_code"] == "DISCONNECT"

    async def test_alarm_triggered_writes_history(self, repository: MockRepository):
        """設備告警觸發 → history 寫入 event='triggered'"""
        buffered = _make_buffered_uploader()
        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        alarm_def = AlarmDefinition(code="OVER_TEMP", name="過溫", level=AlarmLevel.ALARM)
        alarm_event = AlarmEvent(alarm=alarm_def, event_type=AlarmEventType.TRIGGERED)
        payload = DeviceAlarmPayload(device_id="device_001", alarm_event=alarm_event)

        await device.emit(EVENT_ALARM_TRIGGERED, payload)

        buffered.write_immediate.assert_awaited_once()
        call = buffered.write_immediate.await_args
        assert call.args[0] == "alarm_history"
        doc = call.args[1]
        assert doc["event"] == "triggered"
        assert doc["alarm_code"] == "OVER_TEMP"
        assert doc["device_id"] == "device_001"

    async def test_existing_alarm_does_not_write_history(self):
        """is_new=False（既有告警）時不應寫入 history（重複）"""
        repository = MockRepository(is_new=False)
        buffered = _make_buffered_uploader()
        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(device_id="device_001", reason="timeout", consecutive_failures=1)
        await device.emit(EVENT_DISCONNECTED, payload)

        # 只呼叫 upsert 不呼叫 history
        repository.upsert.assert_awaited_once()
        buffered.write_immediate.assert_not_awaited()

    async def test_history_write_has_event_time(self):
        """history doc 應包含 event_time 欄位"""
        repository = MockRepository(is_new=True)
        buffered = _make_buffered_uploader()
        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        payload = DisconnectPayload(
            device_id="device_001",
            reason="timeout",
            consecutive_failures=1,
            timestamp=ts,
        )
        await device.emit(EVENT_DISCONNECTED, payload)

        doc = buffered.write_immediate.await_args.args[1]
        assert doc.get("event_time") == ts


# ======================== buffered_uploader 提供：resolve_alarm 路徑 ========================


class TestAlarmPersistenceHistoryResolve:
    """_resolve_alarm 成功後應寫 resolved event"""

    async def test_connect_writes_resolved_history(self):
        """重連 → history 寫入 event='resolved'"""
        repository = MockRepository(resolve_success=True)
        buffered = _make_buffered_uploader()
        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        ts = datetime(2026, 1, 1, 13, 30, 0, tzinfo=timezone.utc)
        await device.emit(EVENT_CONNECTED, ConnectedPayload(device_id="device_001", timestamp=ts))

        buffered.write_immediate.assert_awaited_once()
        call = buffered.write_immediate.await_args
        assert call.args[0] == "alarm_history"
        doc = call.args[1]
        assert doc["event"] == "resolved"
        assert doc["alarm_key"] == "device_001:disconnect:DISCONNECT"
        assert doc["device_id"] == "device_001"
        assert doc["resolved_timestamp"] == ts
        assert doc["event_time"] == ts

    async def test_alarm_cleared_writes_resolved_history(self):
        """設備告警解除 → history 寫入 resolved"""
        repository = MockRepository(resolve_success=True)
        buffered = _make_buffered_uploader()
        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        alarm_def = AlarmDefinition(code="OVER_TEMP", name="過溫", level=AlarmLevel.ALARM)
        alarm_event = AlarmEvent(alarm=alarm_def, event_type=AlarmEventType.CLEARED)
        ts = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        payload = DeviceAlarmPayload(device_id="device_001", alarm_event=alarm_event, timestamp=ts)

        await device.emit(EVENT_ALARM_CLEARED, payload)

        buffered.write_immediate.assert_awaited_once()
        doc = buffered.write_immediate.await_args.args[1]
        assert doc["event"] == "resolved"
        assert doc["alarm_key"] == "device_001:device_alarm:OVER_TEMP"

    async def test_resolve_failure_skips_history(self):
        """resolve=False 時不應寫 resolved history"""
        repository = MockRepository(resolve_success=False)
        buffered = _make_buffered_uploader()
        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        await device.emit(EVENT_CONNECTED, ConnectedPayload(device_id="device_001"))

        repository.resolve.assert_awaited_once()
        buffered.write_immediate.assert_not_awaited()


# ======================== Failure tolerance ========================


class TestAlarmPersistenceHistoryFailureTolerance:
    """buffered_uploader 拋例外時主流程仍正常"""

    async def test_history_write_exception_does_not_break_create(self):
        """write_immediate 拋例外時，_create_alarm 仍完成（log warning）"""
        repository = MockRepository(is_new=True)
        buffered = _make_buffered_uploader()
        buffered.write_immediate = AsyncMock(side_effect=RuntimeError("buffer down"))

        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(device_id="device_001", reason="timeout", consecutive_failures=1)
        # 不應拋錯
        await device.emit(EVENT_DISCONNECTED, payload)

        # 主流程仍正常：upsert 被呼叫
        repository.upsert.assert_awaited_once()

    async def test_history_write_exception_does_not_break_resolve(self):
        """write_immediate 拋例外時，_resolve_alarm 仍完成"""
        repository = MockRepository(resolve_success=True)
        buffered = _make_buffered_uploader()
        buffered.write_immediate = AsyncMock(side_effect=RuntimeError("buffer down"))

        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        # 不應拋錯
        await device.emit(EVENT_CONNECTED, ConnectedPayload(device_id="device_001"))

        repository.resolve.assert_awaited_once()


# ======================== Custom history_collection ========================


class TestAlarmPersistenceHistoryCustomCollection:
    """AlarmPersistenceConfig.history_collection 客製化時正確傳遞"""

    async def test_custom_history_collection_used_for_triggered(self):
        """客製化 history_collection 應被傳給 buffered_uploader.write_immediate"""
        repository = MockRepository(is_new=True)
        buffered = _make_buffered_uploader()
        config = AlarmPersistenceConfig(history_collection="my_alarm_archive")
        manager = AlarmPersistenceManager(
            repository=repository,
            config=config,
            buffered_uploader=buffered,
        )

        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(device_id="device_001", reason="timeout", consecutive_failures=1)
        await device.emit(EVENT_DISCONNECTED, payload)

        call = buffered.write_immediate.await_args
        assert call.args[0] == "my_alarm_archive"

    async def test_custom_history_collection_used_for_resolved(self):
        """resolve 路徑也應使用客製化 collection"""
        repository = MockRepository(resolve_success=True)
        buffered = _make_buffered_uploader()
        config = AlarmPersistenceConfig(history_collection="my_alarm_archive")
        manager = AlarmPersistenceManager(
            repository=repository,
            config=config,
            buffered_uploader=buffered,
        )

        device = MockDevice("device_001")
        manager.subscribe(device)

        await device.emit(EVENT_CONNECTED, ConnectedPayload(device_id="device_001"))

        call = buffered.write_immediate.await_args
        assert call.args[0] == "my_alarm_archive"


# ======================== Config 驗證 ========================


class TestAlarmPersistenceConfigHistoryCollection:
    """AlarmPersistenceConfig.history_collection 欄位驗證"""

    def test_default_history_collection(self):
        cfg = AlarmPersistenceConfig()
        assert cfg.history_collection == "alarm_history"

    def test_custom_history_collection(self):
        cfg = AlarmPersistenceConfig(history_collection="custom")
        assert cfg.history_collection == "custom"

    def test_empty_history_collection_raises(self):
        with pytest.raises(ValueError, match="history_collection"):
            AlarmPersistenceConfig(history_collection="")
