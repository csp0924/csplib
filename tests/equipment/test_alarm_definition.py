# =============== Equipment Alarm Tests - Definition ===============
#
# 告警定義單元測試

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.equipment.alarm.definition import (
    NO_HYSTERESIS,
    AlarmDefinition,
    AlarmLevel,
    HysteresisConfig,
)


class TestAlarmLevel:
    """AlarmLevel 測試"""

    def test_level_values(self):
        """等級數值正確"""
        assert AlarmLevel.INFO == 1
        assert AlarmLevel.WARNING == 2
        assert AlarmLevel.ALARM == 3

    def test_level_ordering(self):
        """等級可排序比較"""
        assert AlarmLevel.INFO < AlarmLevel.WARNING < AlarmLevel.ALARM

    def test_is_int_enum(self):
        """是 IntEnum，可作為整數使用"""
        assert AlarmLevel.WARNING + 1 == 3
        assert int(AlarmLevel.ALARM) == 3


class TestHysteresisConfig:
    """HysteresisConfig 測試"""

    def test_default_values(self):
        """預設閾值皆為 1"""
        config = HysteresisConfig()
        assert config.activate_threshold == 1
        assert config.clear_threshold == 1

    def test_custom_thresholds(self):
        """可自訂閾值"""
        config = HysteresisConfig(activate_threshold=3, clear_threshold=5)
        assert config.activate_threshold == 3
        assert config.clear_threshold == 5

    def test_invalid_activate_threshold(self):
        """activate_threshold < 1 應報錯"""
        with pytest.raises(ValueError, match="activate_threshold"):
            HysteresisConfig(activate_threshold=0)

    def test_invalid_clear_threshold(self):
        """clear_threshold < 1 應報錯"""
        with pytest.raises(ValueError, match="clear_threshold"):
            HysteresisConfig(clear_threshold=0)

    def test_negative_thresholds(self):
        """負數閾值應報錯"""
        with pytest.raises(ValueError):
            HysteresisConfig(activate_threshold=-1)

    def test_immutable(self):
        """Config 為 frozen dataclass"""
        config = HysteresisConfig()
        with pytest.raises(FrozenInstanceError):
            config.activate_threshold = 10

    def test_no_hysteresis_constant(self):
        """NO_HYSTERESIS 常數正確"""
        assert NO_HYSTERESIS.activate_threshold == 1
        assert NO_HYSTERESIS.clear_threshold == 1


class TestAlarmDefinition:
    """AlarmDefinition 測試"""

    def test_basic_creation(self):
        """基本建立"""
        alarm = AlarmDefinition(
            code="OVER_TEMP",
            name="溫度過高",
        )
        assert alarm.code == "OVER_TEMP"
        assert alarm.name == "溫度過高"
        assert alarm.level == AlarmLevel.ALARM  # 預設等級
        assert alarm.hysteresis == NO_HYSTERESIS
        assert alarm.description == ""

    def test_custom_level(self):
        """可自訂等級"""
        alarm = AlarmDefinition(
            code="LOW_BATTERY",
            name="電量低",
            level=AlarmLevel.WARNING,
        )
        assert alarm.level == AlarmLevel.WARNING

    def test_custom_hysteresis(self):
        """可自訂遲滯設定"""
        config = HysteresisConfig(activate_threshold=3, clear_threshold=5)
        alarm = AlarmDefinition(
            code="OVER_TEMP",
            name="溫度過高",
            hysteresis=config,
        )
        assert alarm.hysteresis.activate_threshold == 3
        assert alarm.hysteresis.clear_threshold == 5

    def test_with_description(self):
        """可附加描述"""
        alarm = AlarmDefinition(
            code="COMM_FAIL",
            name="通訊失敗",
            description="連續 3 次通訊超時",
        )
        assert alarm.description == "連續 3 次通訊超時"

    def test_immutable(self):
        """Definition 為 frozen dataclass"""
        alarm = AlarmDefinition(code="TEST", name="Test")
        with pytest.raises(FrozenInstanceError):
            alarm.code = "CHANGED"

    def test_hashable_by_code(self):
        """hash 基於 code"""
        alarm1 = AlarmDefinition(code="SAME", name="Name1")
        alarm2 = AlarmDefinition(code="SAME", name="Name2")
        assert hash(alarm1) == hash(alarm2)

    def test_different_codes_different_hash(self):
        """不同 code 應有不同 hash"""
        alarm1 = AlarmDefinition(code="A", name="Alarm A")
        alarm2 = AlarmDefinition(code="B", name="Alarm B")
        assert hash(alarm1) != hash(alarm2)

    def test_can_use_in_set(self):
        """可放入 set"""
        alarm1 = AlarmDefinition(code="X", name="X")
        alarm2 = AlarmDefinition(code="Y", name="Y")
        alarm_set = {alarm1, alarm2}
        assert len(alarm_set) == 2
