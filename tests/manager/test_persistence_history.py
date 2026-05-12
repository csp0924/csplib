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

    async def test_existing_alarm_writes_duplicate_trigger_history(self):
        """is_new=False（既有 ACTIVE 告警）→ 寫入 history with event='duplicate_trigger'

        合約：upsert 找到既有 ACTIVE 不代表 disconnect 沒發生；audit history 必須記錄每個
        event。否則 resolve() 失敗造成 stuck-ACTIVE 後，後續同 alarm_key 的 disconnect
        會 silent（無 audit、無 notify）→ silent monitoring blackout。
        Notification 維持 dedupe，但 history 不去重。
        """
        repository = MockRepository(is_new=False)
        buffered = _make_buffered_uploader()
        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        payload = DisconnectPayload(device_id="device_001", reason="timeout", consecutive_failures=1)
        await device.emit(EVENT_DISCONNECTED, payload)

        repository.upsert.assert_awaited_once()
        # 既有 ACTIVE 也要寫 history,但用不同 event 區別
        buffered.write_immediate.assert_awaited_once()
        call = buffered.write_immediate.await_args
        assert call.args[0] == "alarm_history"
        doc = call.args[1]
        assert doc["event"] == "duplicate_trigger"
        assert doc["device_id"] == "device_001"
        assert doc["alarm_code"] == "DISCONNECT"

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


# ======================== Stuck-active silent-blackout regression ========================


class TestStuckActiveSilentBlackoutRegression:
    """resolve 失敗造成 DB 殘留 ACTIVE → 後續同 alarm_key disconnect 仍應有 audit history。

    此類測試是 silent monitoring blackout bug 的回歸保護。修法前:resolve fail → 後續
    disconnect 全部 silent(無 history、無 notify、無 log)。修法後:notification 維持
    dedupe(原合約),但 history 每個 event 都寫入(event=triggered 或 duplicate_trigger)。
    """

    async def test_resolve_fail_then_subsequent_disconnect_still_writes_history(self):
        """stuck-active 場景:resolve fail 後,下一次 disconnect 仍應寫 history。"""
        # 模擬 transient resolve fail:第一次 disconnect 寫入 ACTIVE → connect resolve fail
        # → DB 仍 ACTIVE → 第二次 disconnect upsert 返回 is_new=False
        repository = MockRepository(is_new=True, resolve_success=False)
        buffered = _make_buffered_uploader()
        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        # 第一次 disconnect:正常 triggered history
        await device.emit(
            EVENT_DISCONNECTED,
            DisconnectPayload(device_id="device_001", reason="t1", consecutive_failures=5),
        )
        # connect 嘗試 resolve 失敗(modify_count=0)
        await device.emit(EVENT_CONNECTED, ConnectedPayload(device_id="device_001"))

        # 切換 upsert 為 is_new=False(模擬 DB 仍 ACTIVE)
        repository.upsert.return_value = ("existing_id", False)

        buffered.write_immediate.reset_mock()
        # 第二次 disconnect:修法前 silent,修法後應寫 duplicate_trigger history
        await device.emit(
            EVENT_DISCONNECTED,
            DisconnectPayload(device_id="device_001", reason="t2", consecutive_failures=5),
        )

        buffered.write_immediate.assert_awaited_once()
        doc = buffered.write_immediate.await_args.args[1]
        assert doc["event"] == "duplicate_trigger"
        assert doc["device_id"] == "device_001"
        assert doc["alarm_code"] == "DISCONNECT"

    async def test_continuous_stuck_blackout_quantified(self):
        """連續 N cycle flap 配 100% resolve fail → 全部 N 次 disconnect 都應有 history。

        Quantified regression:修法前 history 只記第一次 disconnect(N-1 silent);
        修法後每次 disconnect 都寫(triggered 1 次 + duplicate_trigger N-1 次)。
        """
        repository = MockRepository(is_new=True, resolve_success=False)
        buffered = _make_buffered_uploader()
        manager = AlarmPersistenceManager(repository=repository, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.subscribe(device)

        n_cycles = 5
        for i in range(n_cycles):
            await device.emit(
                EVENT_DISCONNECTED,
                DisconnectPayload(device_id="device_001", reason=f"#{i}", consecutive_failures=5),
            )
            # connect resolve 永遠失敗,第二次起 upsert 為 is_new=False
            await device.emit(EVENT_CONNECTED, ConnectedPayload(device_id="device_001"))
            repository.upsert.return_value = ("existing_id", False)

        # 統計 history 事件
        triggered = 0
        duplicate = 0
        for call in buffered.write_immediate.await_args_list:
            event = call.args[1].get("event")
            if event == "triggered":
                triggered += 1
            elif event == "duplicate_trigger":
                duplicate += 1

        # resolve 永遠 fail → 不該有 resolved history
        assert triggered == 1  # 只有第一次是 new
        assert duplicate == n_cycles - 1  # 其餘 N-1 次是 duplicate
        # 加總 = N 個 disconnect 都被記錄(無 silent blackout)
        assert triggered + duplicate == n_cycles

    async def test_duplicate_trigger_does_not_notify(self):
        """duplicate_trigger 不應觸發 notification(維持 dedupe spam 設計)。"""
        from csp_lib.notification import NotificationDispatcher

        repository = MockRepository(is_new=False)
        buffered = _make_buffered_uploader()
        dispatcher = MagicMock(spec=NotificationDispatcher)
        dispatcher.dispatch = AsyncMock()
        dispatcher.from_alarm_record = NotificationDispatcher.from_alarm_record

        manager = AlarmPersistenceManager(
            repository=repository,
            dispatcher=dispatcher,
            buffered_uploader=buffered,
        )

        device = MockDevice("device_001")
        manager.subscribe(device)

        await device.emit(
            EVENT_DISCONNECTED,
            DisconnectPayload(device_id="device_001", reason="t", consecutive_failures=1),
        )

        # history 有寫,但 notification 不發
        buffered.write_immediate.assert_awaited_once()
        dispatcher.dispatch.assert_not_awaited()


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
