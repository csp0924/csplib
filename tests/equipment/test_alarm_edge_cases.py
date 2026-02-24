from csp_lib.equipment.alarm.definition import AlarmDefinition, HysteresisConfig
from csp_lib.equipment.alarm.evaluator import (
    BitMaskAlarmEvaluator,
    Operator,
    TableAlarmEvaluator,
    ThresholdAlarmEvaluator,
    ThresholdCondition,
)
from csp_lib.equipment.alarm.state import AlarmEventType, AlarmState


class TestBitMaskEdgeCases:
    def test_empty_bit_alarms(self):
        evaluator = BitMaskAlarmEvaluator(point_name="status", bit_alarms={})
        result = evaluator.evaluate(0xFF)
        assert result == {}

    def test_none_value_returns_empty(self):
        alarm = AlarmDefinition(code="A1", name="test")
        evaluator = BitMaskAlarmEvaluator(point_name="status", bit_alarms={0: alarm})
        result = evaluator.evaluate(None)
        assert result == {}


class TestThresholdEdgeCases:
    def test_nan_value(self):
        """NaN comparisons are all False, so threshold alarms never trigger"""
        alarm = AlarmDefinition(code="HIGH", name="high temp")
        condition = ThresholdCondition(alarm=alarm, operator=Operator.GT, value=50.0)
        evaluator = ThresholdAlarmEvaluator(point_name="temp", conditions=[condition])
        result = evaluator.evaluate(float("nan"))
        assert result["HIGH"] is False

    def test_none_returns_empty(self):
        alarm = AlarmDefinition(code="HIGH", name="high temp")
        condition = ThresholdCondition(alarm=alarm, operator=Operator.GT, value=50.0)
        evaluator = ThresholdAlarmEvaluator(point_name="temp", conditions=[condition])
        result = evaluator.evaluate(None)
        assert result == {}


class TestTableEdgeCases:
    def test_float_to_int_precision(self):
        """3.7 -> int(3.7) = 3, should match table entry for 3"""
        alarm3 = AlarmDefinition(code="ERR3", name="error 3")
        evaluator = TableAlarmEvaluator(point_name="err", table={3: alarm3})
        result = evaluator.evaluate(3.7)
        assert result["ERR3"] is True  # int(3.7) = 3

    def test_none_value(self):
        alarm = AlarmDefinition(code="ERR1", name="error 1")
        evaluator = TableAlarmEvaluator(point_name="err", table={1: alarm})
        result = evaluator.evaluate(None)
        assert result == {}


class TestAlarmStateEdgeCases:
    def test_hysteresis_equal_thresholds(self):
        """activate_threshold=1, clear_threshold=1: single trigger activates"""
        alarm = AlarmDefinition(
            code="TEST",
            name="test",
            hysteresis=HysteresisConfig(activate_threshold=1, clear_threshold=1),
        )
        state = AlarmState(definition=alarm)
        event = state.update(is_triggered=True)
        assert event is not None
        assert event.event_type == AlarmEventType.TRIGGERED
        assert state.is_active

    def test_rapid_toggle_never_activates(self):
        """With threshold=2, alternating True/False never activates"""
        alarm = AlarmDefinition(
            code="TEST",
            name="test",
            hysteresis=HysteresisConfig(activate_threshold=2, clear_threshold=2),
        )
        state = AlarmState(definition=alarm)
        for _ in range(10):
            state.update(is_triggered=True)
            state.update(is_triggered=False)
        assert not state.is_active

    def test_force_clear_inactive_returns_none(self):
        alarm = AlarmDefinition(code="TEST", name="test")
        state = AlarmState(definition=alarm)
        event = state.force_clear()
        assert event is None
