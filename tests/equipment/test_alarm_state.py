# =============== Equipment Alarm Tests - State ===============
#
# 告警狀態管理單元測試

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from csp_lib.equipment.alarm.definition import (
    AlarmDefinition,
    AlarmLevel,
    HysteresisConfig,
)
from csp_lib.equipment.alarm.state import (
    AlarmEvent,
    AlarmEventType,
    AlarmState,
    AlarmStateManager,
)

# ======================== Fixtures ========================


@pytest.fixture
def simple_alarm() -> AlarmDefinition:
    """無遲滯告警定義"""
    return AlarmDefinition(
        code="OVER_TEMP",
        name="溫度過高",
        level=AlarmLevel.ALARM,
    )


@pytest.fixture
def hysteresis_alarm() -> AlarmDefinition:
    """有遲滯告警定義"""
    return AlarmDefinition(
        code="COMM_FAIL",
        name="通訊失敗",
        level=AlarmLevel.WARNING,
        hysteresis=HysteresisConfig(activate_threshold=3, clear_threshold=2),
    )


@pytest.fixture
def info_alarm() -> AlarmDefinition:
    """資訊級告警"""
    return AlarmDefinition(
        code="INFO_MSG",
        name="資訊訊息",
        level=AlarmLevel.INFO,
    )


# ======================== AlarmEventType Tests ========================


class TestAlarmEventType:
    """AlarmEventType 測試"""

    def test_event_types(self):
        assert AlarmEventType.TRIGGERED.value == "triggered"
        assert AlarmEventType.CLEARED.value == "cleared"


# ======================== AlarmEvent Tests ========================


class TestAlarmEvent:
    """AlarmEvent 測試"""

    def test_creation(self, simple_alarm):
        event = AlarmEvent(
            event_type=AlarmEventType.TRIGGERED,
            alarm=simple_alarm,
        )
        assert event.event_type == AlarmEventType.TRIGGERED
        assert event.alarm == simple_alarm
        assert isinstance(event.timestamp, datetime)

    def test_custom_timestamp(self, simple_alarm):
        custom_time = datetime(2026, 1, 1, 12, 0, 0)
        event = AlarmEvent(
            event_type=AlarmEventType.CLEARED,
            alarm=simple_alarm,
            timestamp=custom_time,
        )
        assert event.timestamp == custom_time


# ======================== AlarmState Tests ========================


class TestAlarmState:
    """AlarmState 測試"""

    def test_initial_state(self, simple_alarm):
        """初始狀態"""
        state = AlarmState(definition=simple_alarm)
        assert state.is_active is False
        assert state.activate_count == 0
        assert state.clear_count == 0
        assert state.activated_at is None
        assert state.cleared_at is None
        assert state.last_triggered_at is None

    def test_duration_not_activated(self, simple_alarm):
        """未啟用時 duration 為 None"""
        state = AlarmState(definition=simple_alarm)
        assert state.duration is None


class TestAlarmStateUpdate:
    """AlarmState.update() 測試"""

    def test_trigger_without_hysteresis(self, simple_alarm):
        """無遲滯：單次觸發即啟用"""
        state = AlarmState(definition=simple_alarm)
        event = state.update(is_triggered=True)

        assert event is not None
        assert event.event_type == AlarmEventType.TRIGGERED
        assert state.is_active is True
        assert state.activate_count == 1

    def test_clear_without_hysteresis(self, simple_alarm):
        """無遲滯：單次解除即清除"""
        state = AlarmState(definition=simple_alarm)
        state.update(is_triggered=True)  # 先觸發
        event = state.update(is_triggered=False)  # 再解除

        assert event is not None
        assert event.event_type == AlarmEventType.CLEARED
        assert state.is_active is False
        assert state.clear_count == 1

    def test_trigger_with_hysteresis(self, hysteresis_alarm):
        """有遲滯：需連續觸發達閾值"""
        state = AlarmState(definition=hysteresis_alarm)

        # 第 1、2 次觸發：不應啟用
        assert state.update(is_triggered=True) is None
        assert state.is_active is False
        assert state.activate_count == 1

        assert state.update(is_triggered=True) is None
        assert state.is_active is False
        assert state.activate_count == 2

        # 第 3 次觸發：達閾值，應啟用
        event = state.update(is_triggered=True)
        assert event is not None
        assert event.event_type == AlarmEventType.TRIGGERED
        assert state.is_active is True
        assert state.activate_count == 3

    def test_clear_with_hysteresis(self, hysteresis_alarm):
        """有遲滯：需連續解除達閾值"""
        state = AlarmState(definition=hysteresis_alarm)

        # 先觸發啟用
        for _ in range(3):
            state.update(is_triggered=True)
        assert state.is_active is True

        # 第 1 次解除：不應清除
        assert state.update(is_triggered=False) is None
        assert state.is_active is True
        assert state.clear_count == 1

        # 第 2 次解除：達閾值，應清除
        event = state.update(is_triggered=False)
        assert event is not None
        assert event.event_type == AlarmEventType.CLEARED
        assert state.is_active is False

    def test_counter_reset_on_opposite(self, hysteresis_alarm):
        """觸發/解除計數互斥重置"""
        state = AlarmState(definition=hysteresis_alarm)

        # 觸發 2 次
        state.update(is_triggered=True)
        state.update(is_triggered=True)
        assert state.activate_count == 2

        # 解除 1 次：activate_count 應重置
        state.update(is_triggered=False)
        assert state.activate_count == 0
        assert state.clear_count == 1

        # 再觸發 1 次：clear_count 應重置
        state.update(is_triggered=True)
        assert state.activate_count == 1
        assert state.clear_count == 0

    def test_already_active_no_duplicate_event(self, simple_alarm):
        """已啟用時持續觸發不產生重複事件"""
        state = AlarmState(definition=simple_alarm)
        state.update(is_triggered=True)  # 第一次觸發

        event = state.update(is_triggered=True)  # 第二次觸發
        assert event is None
        assert state.is_active is True

    def test_already_cleared_no_duplicate_event(self, simple_alarm):
        """已清除時持續解除不產生重複事件"""
        state = AlarmState(definition=simple_alarm)

        event = state.update(is_triggered=False)
        assert event is None
        assert state.is_active is False


class TestAlarmStateForceClear:
    """AlarmState.force_clear() 測試"""

    def test_force_clear_active_alarm(self, simple_alarm):
        """強制清除啟用中告警"""
        state = AlarmState(definition=simple_alarm)
        state.update(is_triggered=True)
        assert state.is_active is True

        event = state.force_clear()
        assert event is not None
        assert event.event_type == AlarmEventType.CLEARED
        assert state.is_active is False
        assert state.activate_count == 0
        assert state.clear_count == 0

    def test_force_clear_inactive_alarm(self, simple_alarm):
        """強制清除未啟用告警：返回 None"""
        state = AlarmState(definition=simple_alarm)
        event = state.force_clear()
        assert event is None


class TestAlarmStateDuration:
    """AlarmState.duration 測試"""

    def test_duration_active_alarm(self, simple_alarm):
        """啟用中告警的持續時間"""
        state = AlarmState(definition=simple_alarm)

        fixed_time = datetime(2026, 1, 1, 12, 0, 0)
        with patch("csp_lib.equipment.alarm.state.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            state.update(is_triggered=True)

        # 模擬經過 10 秒
        later_time = fixed_time + timedelta(seconds=10)
        with patch("csp_lib.equipment.alarm.state.datetime") as mock_dt:
            mock_dt.now.return_value = later_time
            duration = state.duration

        assert duration is not None
        assert duration >= 10.0

    def test_duration_cleared_alarm(self, simple_alarm):
        """已清除告警的持續時間（固定值）"""
        state = AlarmState(definition=simple_alarm)

        t1 = datetime(2026, 1, 1, 12, 0, 0)
        t2 = datetime(2026, 1, 1, 12, 0, 30)

        with patch("csp_lib.equipment.alarm.state.datetime") as mock_dt:
            mock_dt.now.return_value = t1
            state.update(is_triggered=True)

        with patch("csp_lib.equipment.alarm.state.datetime") as mock_dt:
            mock_dt.now.return_value = t2
            state.update(is_triggered=False)

        # 持續時間應為 30 秒
        assert state.duration == 30.0


# ======================== AlarmStateManager Tests ========================


class TestAlarmStateManagerRegistration:
    """AlarmStateManager 註冊測試"""

    def test_register_alarm(self, simple_alarm):
        """註冊單一告警"""
        manager = AlarmStateManager()
        state = manager.register_alarm(simple_alarm)

        assert state is not None
        assert state.definition == simple_alarm
        assert manager.get_state("OVER_TEMP") is state

    def test_register_duplicate_alarm(self, simple_alarm):
        """重複註冊應拋錯"""
        manager = AlarmStateManager()
        manager.register_alarm(simple_alarm)

        with pytest.raises(KeyError, match="OVER_TEMP"):
            manager.register_alarm(simple_alarm)

    def test_register_alarms_batch(self, simple_alarm, hysteresis_alarm):
        """批量註冊多個告警"""
        manager = AlarmStateManager()
        states = manager.register_alarms([simple_alarm, hysteresis_alarm])

        assert len(states) == 2
        assert manager.get_state("OVER_TEMP") is not None
        assert manager.get_state("COMM_FAIL") is not None

    def test_register_alarms_with_duplicates(self, simple_alarm):
        """批量註冊時有重複應拋錯"""
        manager = AlarmStateManager()
        manager.register_alarm(simple_alarm)

        dup_alarm = AlarmDefinition(code="OVER_TEMP", name="另一個溫度告警")
        with pytest.raises(KeyError, match="OVER_TEMP"):
            manager.register_alarms([dup_alarm])

    def test_register_alarms_atomic(self, simple_alarm):
        """批量註冊失敗時應全部回滾（不註冊任何一個）"""
        manager = AlarmStateManager()
        manager.register_alarm(simple_alarm)

        new_alarm = AlarmDefinition(code="NEW_ALARM", name="新告警")
        dup_alarm = AlarmDefinition(code="OVER_TEMP", name="重複告警")

        with pytest.raises(KeyError):
            manager.register_alarms([new_alarm, dup_alarm])

        # new_alarm 不應被註冊
        assert manager.get_state("NEW_ALARM") is None


class TestAlarmStateManagerUpdate:
    """AlarmStateManager.update() 測試"""

    def test_update_single_alarm(self, simple_alarm):
        """更新單一告警"""
        manager = AlarmStateManager()
        manager.register_alarm(simple_alarm)

        events = manager.update({"OVER_TEMP": True})
        assert len(events) == 1
        assert events[0].event_type == AlarmEventType.TRIGGERED

    def test_update_multiple_alarms(self, simple_alarm, hysteresis_alarm):
        """更新多個告警"""
        manager = AlarmStateManager()
        manager.register_alarms([simple_alarm, hysteresis_alarm])

        # simple_alarm 應觸發，hysteresis_alarm 不應（需 3 次）
        events = manager.update({"OVER_TEMP": True, "COMM_FAIL": True})
        assert len(events) == 1
        assert events[0].alarm.code == "OVER_TEMP"

    def test_update_unknown_alarm_ignored(self, simple_alarm):
        """更新未註冊告警應忽略"""
        manager = AlarmStateManager()
        manager.register_alarm(simple_alarm)

        events = manager.update({"UNKNOWN_CODE": True})
        assert len(events) == 0

    def test_update_partial_evaluations(self, simple_alarm, hysteresis_alarm):
        """部分評估（只更新部分告警）"""
        manager = AlarmStateManager()
        manager.register_alarms([simple_alarm, hysteresis_alarm])

        # 只更新 OVER_TEMP
        events = manager.update({"OVER_TEMP": True})
        assert len(events) == 1

        # COMM_FAIL 狀態不變
        state = manager.get_state("COMM_FAIL")
        assert state.activate_count == 0


class TestAlarmStateManagerClearAlarm:
    """AlarmStateManager.clear_alarm() 測試"""

    def test_clear_active_alarm(self, simple_alarm):
        """清除啟用中告警"""
        manager = AlarmStateManager()
        manager.register_alarm(simple_alarm)
        manager.update({"OVER_TEMP": True})

        event = manager.clear_alarm("OVER_TEMP")
        assert event is not None
        assert event.event_type == AlarmEventType.CLEARED

    def test_clear_inactive_alarm(self, simple_alarm):
        """清除未啟用告警：返回 None"""
        manager = AlarmStateManager()
        manager.register_alarm(simple_alarm)

        event = manager.clear_alarm("OVER_TEMP")
        assert event is None

    def test_clear_unknown_alarm(self):
        """清除未註冊告警：返回 None"""
        manager = AlarmStateManager()
        event = manager.clear_alarm("UNKNOWN")
        assert event is None


class TestAlarmStateManagerQueries:
    """AlarmStateManager 查詢方法測試"""

    def test_get_active_alarms_empty(self):
        """無啟用告警時返回空列表"""
        manager = AlarmStateManager()
        assert manager.get_active_alarms() == []

    def test_get_active_alarms(self, simple_alarm, hysteresis_alarm):
        """取得所有啟用中告警"""
        manager = AlarmStateManager()
        manager.register_alarms([simple_alarm, hysteresis_alarm])
        manager.update({"OVER_TEMP": True})

        active = manager.get_active_alarms()
        assert len(active) == 1
        assert active[0].definition.code == "OVER_TEMP"

    def test_get_state_exists(self, simple_alarm):
        """取得已註冊告警狀態"""
        manager = AlarmStateManager()
        manager.register_alarm(simple_alarm)

        state = manager.get_state("OVER_TEMP")
        assert state is not None
        assert state.definition.code == "OVER_TEMP"

    def test_get_state_not_exists(self):
        """取得未註冊告警狀態：返回 None"""
        manager = AlarmStateManager()
        assert manager.get_state("UNKNOWN") is None

    def test_has_protection_alarm_true(self, simple_alarm, info_alarm):
        """存在保護性告警（ALARM 等級）"""
        manager = AlarmStateManager()
        manager.register_alarms([simple_alarm, info_alarm])
        manager.update({"OVER_TEMP": True})

        assert manager.has_protection_alarm() is True

    def test_has_protection_alarm_false_warning(self, hysteresis_alarm):
        """只有 WARNING 等級告警"""
        manager = AlarmStateManager()
        manager.register_alarm(hysteresis_alarm)

        # 觸發 WARNING 級告警
        for _ in range(3):
            manager.update({"COMM_FAIL": True})

        assert manager.has_protection_alarm() is False

    def test_has_protection_alarm_false_inactive(self, simple_alarm):
        """ALARM 等級告警未啟用"""
        manager = AlarmStateManager()
        manager.register_alarm(simple_alarm)

        assert manager.has_protection_alarm() is False


class TestAlarmStateManagerReset:
    """AlarmStateManager.reset() 測試"""

    def test_reset_clears_all_alarms(self, simple_alarm, hysteresis_alarm):
        """重置清除所有告警"""
        manager = AlarmStateManager()
        manager.register_alarms([simple_alarm, hysteresis_alarm])

        # 觸發所有告警
        manager.update({"OVER_TEMP": True})
        for _ in range(3):
            manager.update({"COMM_FAIL": True})

        assert len(manager.get_active_alarms()) == 2

        manager.reset()

        assert len(manager.get_active_alarms()) == 0
        assert manager.get_state("OVER_TEMP").is_active is False
        assert manager.get_state("COMM_FAIL").is_active is False
