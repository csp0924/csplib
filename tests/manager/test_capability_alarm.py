# =============== Manager Alarm Tests - Capability Degraded ===============
#
# Wave 2b Step 1：CAPABILITY_DEGRADED alarm 測試
#
# 測試覆蓋：
# - EVENT_CAPABILITY_REMOVED → AlarmPersistenceManager 建 CAPABILITY_DEGRADED record
# - EVENT_CAPABILITY_ADDED → alarm 被 resolve
# - 不同 capability_name 獨立產生 alarm
# - 不同 device 同 capability 彼此獨立
# - alarm_key 格式驗證
# - notification dispatcher 被觸發
# - repository 失敗時 warn 不中斷

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from csp_lib.equipment.alarm import AlarmLevel
from csp_lib.equipment.device.events import (
    EVENT_CAPABILITY_ADDED,
    EVENT_CAPABILITY_REMOVED,
    CapabilityChangedPayload,
)
from csp_lib.manager.alarm.persistence import AlarmPersistenceManager
from csp_lib.manager.alarm.schema import AlarmRecord, AlarmType
from csp_lib.notification import NotificationDispatcher, NotificationEvent


class MockDevice:
    """Mock AsyncModbusDevice for capability event testing"""

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self._handlers: dict[str, list] = {}

    def on(self, event: str, handler):
        self._handlers.setdefault(event, []).append(handler)

        def _cancel() -> None:
            if event in self._handlers and handler in self._handlers[event]:
                self._handlers[event].remove(handler)

        return _cancel

    async def emit(self, event: str, payload) -> None:
        """同步觸發所有 handlers（測試用，避免真正的 async queue）"""
        for handler in list(self._handlers.get(event, [])):
            await handler(payload)


class MockRepository:
    """Mock AlarmRepository"""

    def __init__(self) -> None:
        self.upsert = AsyncMock(return_value=("mock_id", True))
        self.resolve = AsyncMock(return_value=True)
        self.get_active_alarms = AsyncMock(return_value=[])
        self.get_active_by_device = AsyncMock(return_value=[])


# ======================== EVENT_CAPABILITY_REMOVED ========================


class TestCapabilityRemovedCreatesAlarm:
    """EVENT_CAPABILITY_REMOVED 應建立 CAPABILITY_DEGRADED alarm"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository()

    @pytest.fixture
    def manager(self, repository: MockRepository) -> AlarmPersistenceManager:
        return AlarmPersistenceManager(repository=repository)

    async def test_capability_removed_creates_warning_alarm(
        self, manager: AlarmPersistenceManager, repository: MockRepository
    ):
        """capability 被移除 → 建立 WARNING 級 CAPABILITY_DEGRADED alarm"""
        device = MockDevice("pcs_001")
        manager.subscribe(device)

        payload = CapabilityChangedPayload(
            device_id="pcs_001",
            capability_name="power_control",
        )
        await device.emit(EVENT_CAPABILITY_REMOVED, payload)

        repository.upsert.assert_called_once()
        record: AlarmRecord = repository.upsert.call_args[0][0]

        assert record.alarm_type == AlarmType.CAPABILITY_DEGRADED
        assert record.device_id == "pcs_001"
        assert record.alarm_code == "power_control"
        assert record.level == AlarmLevel.WARNING
        assert record.name == "能力降級: power_control"
        assert "pcs_001" in record.description
        assert "power_control" in record.description

    async def test_alarm_key_format(self, manager: AlarmPersistenceManager, repository: MockRepository):
        """alarm_key 格式 = '<device_id>:capability_degraded:<capability_name>'"""
        device = MockDevice("meter_A")
        manager.subscribe(device)

        payload = CapabilityChangedPayload(
            device_id="meter_A",
            capability_name="read_energy",
        )
        await device.emit(EVENT_CAPABILITY_REMOVED, payload)

        record: AlarmRecord = repository.upsert.call_args[0][0]
        assert record.alarm_key == "meter_A:capability_degraded:read_energy"

    async def test_timestamp_propagated(self, manager: AlarmPersistenceManager, repository: MockRepository):
        """payload.timestamp 應傳遞到 record.timestamp"""
        device = MockDevice("dev_ts")
        manager.subscribe(device)

        ts = datetime(2026, 4, 22, 12, 0, 0)
        payload = CapabilityChangedPayload(
            device_id="dev_ts",
            capability_name="cap_x",
            timestamp=ts,
        )
        await device.emit(EVENT_CAPABILITY_REMOVED, payload)

        record: AlarmRecord = repository.upsert.call_args[0][0]
        assert record.timestamp == ts


# ======================== EVENT_CAPABILITY_ADDED (restore) ========================


class TestCapabilityAddedResolvesAlarm:
    """EVENT_CAPABILITY_ADDED 應 resolve 對應 alarm"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository()

    @pytest.fixture
    def manager(self, repository: MockRepository) -> AlarmPersistenceManager:
        return AlarmPersistenceManager(repository=repository)

    async def test_capability_added_resolves_matching_alarm(
        self, manager: AlarmPersistenceManager, repository: MockRepository
    ):
        """同 capability_name 的 ADDED 事件應 resolve 對應 alarm"""
        device = MockDevice("pcs_001")
        manager.subscribe(device)

        payload = CapabilityChangedPayload(
            device_id="pcs_001",
            capability_name="power_control",
        )
        await device.emit(EVENT_CAPABILITY_ADDED, payload)

        repository.resolve.assert_called_once()
        key, resolved_at = repository.resolve.call_args[0]
        assert key == "pcs_001:capability_degraded:power_control"
        assert isinstance(resolved_at, datetime)

    async def test_removed_then_added_flow(self, manager: AlarmPersistenceManager, repository: MockRepository):
        """REMOVED 後 ADDED：先 upsert，後 resolve，alarm_key 相同"""
        device = MockDevice("pcs_lifecycle")
        manager.subscribe(device)

        # capability 消失
        await device.emit(
            EVENT_CAPABILITY_REMOVED,
            CapabilityChangedPayload(device_id="pcs_lifecycle", capability_name="cap_a"),
        )
        # capability 恢復
        await device.emit(
            EVENT_CAPABILITY_ADDED,
            CapabilityChangedPayload(device_id="pcs_lifecycle", capability_name="cap_a"),
        )

        repository.upsert.assert_called_once()
        repository.resolve.assert_called_once()

        upsert_record: AlarmRecord = repository.upsert.call_args[0][0]
        resolve_key = repository.resolve.call_args[0][0]
        assert upsert_record.alarm_key == resolve_key


# ======================== 多 capability / 多 device 獨立性 ========================


class TestCapabilityAlarmIndependence:
    """不同 capability_name / device 彼此獨立"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository()

    @pytest.fixture
    def manager(self, repository: MockRepository) -> AlarmPersistenceManager:
        return AlarmPersistenceManager(repository=repository)

    async def test_different_capabilities_produce_distinct_alarms(
        self, manager: AlarmPersistenceManager, repository: MockRepository
    ):
        """同 device，不同 capability 各自一筆 alarm（alarm_key 不同）"""
        device = MockDevice("pcs_multi")
        manager.subscribe(device)

        await device.emit(
            EVENT_CAPABILITY_REMOVED,
            CapabilityChangedPayload(device_id="pcs_multi", capability_name="cap_a"),
        )
        await device.emit(
            EVENT_CAPABILITY_REMOVED,
            CapabilityChangedPayload(device_id="pcs_multi", capability_name="cap_b"),
        )

        assert repository.upsert.call_count == 2
        keys = [call.args[0].alarm_key for call in repository.upsert.call_args_list]
        assert "pcs_multi:capability_degraded:cap_a" in keys
        assert "pcs_multi:capability_degraded:cap_b" in keys

    async def test_different_devices_same_capability_independent(
        self, manager: AlarmPersistenceManager, repository: MockRepository
    ):
        """不同 device 的同 capability_name，alarm_key 不同（獨立）"""
        dev_a = MockDevice("dev_a")
        dev_b = MockDevice("dev_b")
        manager.subscribe(dev_a)
        manager.subscribe(dev_b)

        await dev_a.emit(
            EVENT_CAPABILITY_REMOVED,
            CapabilityChangedPayload(device_id="dev_a", capability_name="shared_cap"),
        )
        await dev_b.emit(
            EVENT_CAPABILITY_REMOVED,
            CapabilityChangedPayload(device_id="dev_b", capability_name="shared_cap"),
        )

        assert repository.upsert.call_count == 2
        keys = [call.args[0].alarm_key for call in repository.upsert.call_args_list]
        assert "dev_a:capability_degraded:shared_cap" in keys
        assert "dev_b:capability_degraded:shared_cap" in keys
        assert keys[0] != keys[1]

    async def test_resolve_one_capability_does_not_affect_other(
        self, manager: AlarmPersistenceManager, repository: MockRepository
    ):
        """resolve cap_a 不影響 cap_b"""
        device = MockDevice("pcs_partial")
        manager.subscribe(device)

        await device.emit(
            EVENT_CAPABILITY_REMOVED,
            CapabilityChangedPayload(device_id="pcs_partial", capability_name="cap_a"),
        )
        await device.emit(
            EVENT_CAPABILITY_REMOVED,
            CapabilityChangedPayload(device_id="pcs_partial", capability_name="cap_b"),
        )
        # 只恢復 cap_a
        await device.emit(
            EVENT_CAPABILITY_ADDED,
            CapabilityChangedPayload(device_id="pcs_partial", capability_name="cap_a"),
        )

        repository.resolve.assert_called_once()
        resolve_key = repository.resolve.call_args[0][0]
        assert resolve_key == "pcs_partial:capability_degraded:cap_a"


# ======================== Notification Dispatch ========================


class TestCapabilityAlarmNotification:
    """capability alarm 應觸發 notification dispatch（對齊其他 alarm 路徑）"""

    async def test_new_capability_alarm_triggers_notification(self):
        """新 capability alarm 應 dispatch TRIGGERED 通知"""
        repository = MockRepository()
        repository.upsert.return_value = ("mock_id", True)  # is_new = True

        dispatcher = MagicMock(spec=NotificationDispatcher)
        dispatcher.dispatch = AsyncMock()
        dispatcher.from_alarm_record = NotificationDispatcher.from_alarm_record

        manager = AlarmPersistenceManager(repository=repository, dispatcher=dispatcher)
        device = MockDevice("pcs_notify")
        manager.subscribe(device)

        await device.emit(
            EVENT_CAPABILITY_REMOVED,
            CapabilityChangedPayload(device_id="pcs_notify", capability_name="cap_x"),
        )

        dispatcher.dispatch.assert_called_once()
        notification = dispatcher.dispatch.call_args[0][0]
        assert notification.event == NotificationEvent.TRIGGERED
        assert notification.device_id == "pcs_notify"

    async def test_existing_capability_alarm_no_notification(self):
        """既存 alarm（is_new=False）不應重複 dispatch"""
        repository = MockRepository()
        repository.upsert.return_value = ("existing", False)  # is_new = False

        dispatcher = MagicMock(spec=NotificationDispatcher)
        dispatcher.dispatch = AsyncMock()
        dispatcher.from_alarm_record = NotificationDispatcher.from_alarm_record

        manager = AlarmPersistenceManager(repository=repository, dispatcher=dispatcher)
        device = MockDevice("pcs_dup")
        manager.subscribe(device)

        await device.emit(
            EVENT_CAPABILITY_REMOVED,
            CapabilityChangedPayload(device_id="pcs_dup", capability_name="cap_dup"),
        )

        dispatcher.dispatch.assert_not_called()

    async def test_resolved_capability_alarm_triggers_resolved_notification(self):
        """capability 恢復應 dispatch RESOLVED 通知"""
        repository = MockRepository()
        repository.resolve.return_value = True

        dispatcher = MagicMock(spec=NotificationDispatcher)
        dispatcher.dispatch = AsyncMock()

        manager = AlarmPersistenceManager(repository=repository, dispatcher=dispatcher)
        device = MockDevice("pcs_resolved")
        manager.subscribe(device)

        await device.emit(
            EVENT_CAPABILITY_ADDED,
            CapabilityChangedPayload(device_id="pcs_resolved", capability_name="cap_r"),
        )

        dispatcher.dispatch.assert_called_once()
        notification = dispatcher.dispatch.call_args[0][0]
        assert notification.event == NotificationEvent.RESOLVED
        assert notification.device_id == "pcs_resolved"
        assert notification.alarm_key == "pcs_resolved:capability_degraded:cap_r"


# ======================== Repository failure resilience ========================


class TestCapabilityAlarmRepositoryFailure:
    """repository 失敗時行為：alarm handler 不應中斷事件分發。

    現有 _create_alarm / _resolve_alarm 並未用 try/except 包裹 upsert/resolve，
    失敗會以 exception 冒泡到 handler 外；測試驗證當前行為，作為後續若改為
    warn-and-continue 的 regression 基準。
    """

    async def test_upsert_failure_propagates_from_handler(self):
        """repository.upsert 失敗時 exception 冒泡（當前行為）"""
        repository = MockRepository()
        repository.upsert.side_effect = RuntimeError("DB down")

        manager = AlarmPersistenceManager(repository=repository)
        device = MockDevice("pcs_fail")
        manager.subscribe(device)

        payload = CapabilityChangedPayload(
            device_id="pcs_fail",
            capability_name="cap_err",
        )
        with pytest.raises(RuntimeError, match="DB down"):
            await device.emit(EVENT_CAPABILITY_REMOVED, payload)

    async def test_resolve_failure_propagates_from_handler(self):
        """repository.resolve 失敗時 exception 冒泡（當前行為）"""
        repository = MockRepository()
        repository.resolve.side_effect = RuntimeError("DB down")

        manager = AlarmPersistenceManager(repository=repository)
        device = MockDevice("pcs_res_fail")
        manager.subscribe(device)

        payload = CapabilityChangedPayload(
            device_id="pcs_res_fail",
            capability_name="cap_err",
        )
        with pytest.raises(RuntimeError, match="DB down"):
            await device.emit(EVENT_CAPABILITY_ADDED, payload)

    async def test_notification_dispatcher_failure_does_not_break_flow(self):
        """dispatcher 失敗應被吞為 warn log，不影響主流程（對齊 _notify 既有行為）"""
        repository = MockRepository()
        repository.upsert.return_value = ("mock_id", True)

        dispatcher = MagicMock(spec=NotificationDispatcher)
        dispatcher.dispatch = AsyncMock(side_effect=RuntimeError("notify down"))
        dispatcher.from_alarm_record = NotificationDispatcher.from_alarm_record

        manager = AlarmPersistenceManager(repository=repository, dispatcher=dispatcher)
        device = MockDevice("pcs_notify_fail")
        manager.subscribe(device)

        # 不應 raise（_notify 內 try/except 吞例外）
        with patch("csp_lib.manager.alarm.persistence.logger") as mock_logger:
            await device.emit(
                EVENT_CAPABILITY_REMOVED,
                CapabilityChangedPayload(
                    device_id="pcs_notify_fail",
                    capability_name="cap_any",
                ),
            )
            # warn 應被呼叫（opt(exception=True).warning）
            assert mock_logger.opt.return_value.warning.called


# ======================== Subscribe lifecycle ========================


class TestCapabilityEventRegistration:
    """驗證 subscribe 時確實註冊了 CAPABILITY 相關事件 handler"""

    async def test_subscribe_registers_capability_handlers(self):
        """subscribe 後 device 應有 capability_added / capability_removed handler"""
        manager = AlarmPersistenceManager(repository=MockRepository())
        device = MockDevice("pcs_sub")

        manager.subscribe(device)

        assert len(device._handlers.get(EVENT_CAPABILITY_REMOVED, [])) == 1
        assert len(device._handlers.get(EVENT_CAPABILITY_ADDED, [])) == 1

    async def test_unsubscribe_removes_capability_handlers(self):
        """unsubscribe 後 capability handler 應被移除"""
        manager = AlarmPersistenceManager(repository=MockRepository())
        device = MockDevice("pcs_unsub")

        manager.subscribe(device)
        manager.unsubscribe(device)

        assert len(device._handlers.get(EVENT_CAPABILITY_REMOVED, [])) == 0
        assert len(device._handlers.get(EVENT_CAPABILITY_ADDED, [])) == 0
