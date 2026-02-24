# =============== Equipment Alarm Tests - Evaluator ===============
#
# 告警評估器單元測試

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.equipment.alarm.definition import AlarmDefinition, AlarmLevel
from csp_lib.equipment.alarm.evaluator import (
    AlarmEvaluator,
    BitMaskAlarmEvaluator,
    Operator,
    TableAlarmEvaluator,
    ThresholdAlarmEvaluator,
    ThresholdCondition,
)

# ======================== Fixtures ========================


@pytest.fixture
def bit0_alarm() -> AlarmDefinition:
    return AlarmDefinition(code="BIT0_FAULT", name="位元0故障")


@pytest.fixture
def bit1_alarm() -> AlarmDefinition:
    return AlarmDefinition(code="BIT1_FAULT", name="位元1故障")


@pytest.fixture
def bit7_alarm() -> AlarmDefinition:
    return AlarmDefinition(code="BIT7_FAULT", name="位元7故障")


@pytest.fixture
def fault_code_1_alarm() -> AlarmDefinition:
    return AlarmDefinition(code="FAULT_1", name="故障碼1")


@pytest.fixture
def fault_code_2_alarm() -> AlarmDefinition:
    return AlarmDefinition(code="FAULT_2", name="故障碼2")


@pytest.fixture
def high_temp_alarm() -> AlarmDefinition:
    return AlarmDefinition(code="HIGH_TEMP", name="溫度過高", level=AlarmLevel.ALARM)


@pytest.fixture
def low_temp_alarm() -> AlarmDefinition:
    return AlarmDefinition(code="LOW_TEMP", name="溫度過低", level=AlarmLevel.WARNING)


# ======================== Operator Tests ========================


class TestOperator:
    """Operator 測試"""

    def test_operator_values(self):
        """運算子值正確"""
        assert Operator.GT.value == ">"
        assert Operator.GE.value == ">="
        assert Operator.LT.value == "<"
        assert Operator.LE.value == "<="
        assert Operator.EQ.value == "=="
        assert Operator.NE.value == "!="


# ======================== ThresholdCondition Tests ========================


class TestThresholdCondition:
    """ThresholdCondition 測試"""

    def test_gt_operator(self, high_temp_alarm):
        """大於運算子"""
        cond = ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0)
        assert cond.check(46.0) is True
        assert cond.check(45.0) is False
        assert cond.check(44.0) is False

    def test_ge_operator(self, high_temp_alarm):
        """大於等於運算子"""
        cond = ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GE, value=45.0)
        assert cond.check(46.0) is True
        assert cond.check(45.0) is True
        assert cond.check(44.0) is False

    def test_lt_operator(self, low_temp_alarm):
        """小於運算子"""
        cond = ThresholdCondition(alarm=low_temp_alarm, operator=Operator.LT, value=0.0)
        assert cond.check(-1.0) is True
        assert cond.check(0.0) is False
        assert cond.check(1.0) is False

    def test_le_operator(self, low_temp_alarm):
        """小於等於運算子"""
        cond = ThresholdCondition(alarm=low_temp_alarm, operator=Operator.LE, value=0.0)
        assert cond.check(-1.0) is True
        assert cond.check(0.0) is True
        assert cond.check(1.0) is False

    def test_eq_operator(self, fault_code_1_alarm):
        """等於運算子"""
        cond = ThresholdCondition(alarm=fault_code_1_alarm, operator=Operator.EQ, value=100.0)
        assert cond.check(100.0) is True
        assert cond.check(99.0) is False
        assert cond.check(101.0) is False

    def test_ne_operator(self, fault_code_1_alarm):
        """不等於運算子"""
        cond = ThresholdCondition(alarm=fault_code_1_alarm, operator=Operator.NE, value=0.0)
        assert cond.check(1.0) is True
        assert cond.check(-1.0) is True
        assert cond.check(0.0) is False

    def test_immutable(self, high_temp_alarm):
        """ThresholdCondition 為 frozen dataclass"""
        cond = ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0)
        with pytest.raises(FrozenInstanceError):
            cond.value = 50.0


# ======================== BitMaskAlarmEvaluator Tests ========================


class TestBitMaskAlarmEvaluator:
    """BitMaskAlarmEvaluator 測試"""

    def test_point_name(self, bit0_alarm):
        """point_name 屬性"""
        evaluator = BitMaskAlarmEvaluator(
            point_name="fault_register",
            bit_alarms={0: bit0_alarm},
        )
        assert evaluator.point_name == "fault_register"

    def test_single_bit_triggered(self, bit0_alarm):
        """單一位元觸發"""
        evaluator = BitMaskAlarmEvaluator(
            point_name="fault",
            bit_alarms={0: bit0_alarm},
        )
        result = evaluator.evaluate(0b0001)  # bit 0 = 1
        assert result["BIT0_FAULT"] is True

    def test_single_bit_not_triggered(self, bit0_alarm):
        """單一位元未觸發"""
        evaluator = BitMaskAlarmEvaluator(
            point_name="fault",
            bit_alarms={0: bit0_alarm},
        )
        result = evaluator.evaluate(0b0010)  # bit 0 = 0
        assert result["BIT0_FAULT"] is False

    def test_multiple_bits(self, bit0_alarm, bit1_alarm, bit7_alarm):
        """多位元評估"""
        evaluator = BitMaskAlarmEvaluator(
            point_name="fault",
            bit_alarms={
                0: bit0_alarm,
                1: bit1_alarm,
                7: bit7_alarm,
            },
        )
        # 0b10000011 = bit 0, 1, 7 都是 1
        result = evaluator.evaluate(0b10000011)
        assert result["BIT0_FAULT"] is True
        assert result["BIT1_FAULT"] is True
        assert result["BIT7_FAULT"] is True

    def test_partial_bits(self, bit0_alarm, bit1_alarm, bit7_alarm):
        """部分位元觸發"""
        evaluator = BitMaskAlarmEvaluator(
            point_name="fault",
            bit_alarms={
                0: bit0_alarm,
                1: bit1_alarm,
                7: bit7_alarm,
            },
        )
        # 0b00000010 = 只有 bit 1 是 1
        result = evaluator.evaluate(0b00000010)
        assert result["BIT0_FAULT"] is False
        assert result["BIT1_FAULT"] is True
        assert result["BIT7_FAULT"] is False

    def test_value_none(self, bit0_alarm):
        """值為 None 返回空字典"""
        evaluator = BitMaskAlarmEvaluator(
            point_name="fault",
            bit_alarms={0: bit0_alarm},
        )
        result = evaluator.evaluate(None)
        assert result == {}

    def test_value_string_convertible(self, bit0_alarm):
        """字串可轉換為整數"""
        evaluator = BitMaskAlarmEvaluator(
            point_name="fault",
            bit_alarms={0: bit0_alarm},
        )
        result = evaluator.evaluate("1")
        assert result["BIT0_FAULT"] is True

    def test_value_string_not_convertible(self, bit0_alarm):
        """字串無法轉換返回空字典"""
        evaluator = BitMaskAlarmEvaluator(
            point_name="fault",
            bit_alarms={0: bit0_alarm},
        )
        result = evaluator.evaluate("not_a_number")
        assert result == {}

    def test_value_float(self, bit0_alarm):
        """浮點數可轉換"""
        evaluator = BitMaskAlarmEvaluator(
            point_name="fault",
            bit_alarms={0: bit0_alarm},
        )
        result = evaluator.evaluate(1.9)  # int(1.9) = 1
        assert result["BIT0_FAULT"] is True

    def test_get_alarms(self, bit0_alarm, bit1_alarm):
        """取得所有告警定義"""
        evaluator = BitMaskAlarmEvaluator(
            point_name="fault",
            bit_alarms={
                0: bit0_alarm,
                1: bit1_alarm,
            },
        )
        alarms = evaluator.get_alarms()
        assert len(alarms) == 2
        assert bit0_alarm in alarms
        assert bit1_alarm in alarms


# ======================== TableAlarmEvaluator Tests ========================


class TestTableAlarmEvaluator:
    """TableAlarmEvaluator 測試"""

    def test_point_name(self, fault_code_1_alarm):
        """point_name 屬性"""
        evaluator = TableAlarmEvaluator(
            point_name="error_code",
            table={1: fault_code_1_alarm},
        )
        assert evaluator.point_name == "error_code"

    def test_value_matched(self, fault_code_1_alarm, fault_code_2_alarm):
        """值匹配表中項目"""
        evaluator = TableAlarmEvaluator(
            point_name="error_code",
            table={
                1: fault_code_1_alarm,
                2: fault_code_2_alarm,
            },
        )
        result = evaluator.evaluate(1)
        assert result["FAULT_1"] is True
        assert result["FAULT_2"] is False

    def test_value_not_matched(self, fault_code_1_alarm, fault_code_2_alarm):
        """值不在表中"""
        evaluator = TableAlarmEvaluator(
            point_name="error_code",
            table={
                1: fault_code_1_alarm,
                2: fault_code_2_alarm,
            },
        )
        result = evaluator.evaluate(99)  # 不在表中
        assert result["FAULT_1"] is False
        assert result["FAULT_2"] is False

    def test_value_zero(self, fault_code_1_alarm):
        """值為 0（通常表示無錯誤）"""
        evaluator = TableAlarmEvaluator(
            point_name="error_code",
            table={1: fault_code_1_alarm},
        )
        result = evaluator.evaluate(0)
        assert result["FAULT_1"] is False

    def test_value_none(self, fault_code_1_alarm):
        """值為 None 返回空字典"""
        evaluator = TableAlarmEvaluator(
            point_name="error_code",
            table={1: fault_code_1_alarm},
        )
        result = evaluator.evaluate(None)
        assert result == {}

    def test_value_string_convertible(self, fault_code_1_alarm):
        """字串可轉換"""
        evaluator = TableAlarmEvaluator(
            point_name="error_code",
            table={1: fault_code_1_alarm},
        )
        result = evaluator.evaluate("1")
        assert result["FAULT_1"] is True

    def test_value_string_not_convertible(self, fault_code_1_alarm):
        """字串無法轉換返回全 False"""
        evaluator = TableAlarmEvaluator(
            point_name="error_code",
            table={1: fault_code_1_alarm},
        )
        result = evaluator.evaluate("invalid")
        assert result["FAULT_1"] is False

    def test_get_alarms(self, fault_code_1_alarm, fault_code_2_alarm):
        """取得所有告警定義"""
        evaluator = TableAlarmEvaluator(
            point_name="error_code",
            table={
                1: fault_code_1_alarm,
                2: fault_code_2_alarm,
            },
        )
        alarms = evaluator.get_alarms()
        assert len(alarms) == 2
        assert fault_code_1_alarm in alarms
        assert fault_code_2_alarm in alarms


# ======================== ThresholdAlarmEvaluator Tests ========================


class TestThresholdAlarmEvaluator:
    """ThresholdAlarmEvaluator 測試"""

    def test_point_name(self, high_temp_alarm):
        """point_name 屬性"""
        evaluator = ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0)],
        )
        assert evaluator.point_name == "temperature"

    def test_single_condition_triggered(self, high_temp_alarm):
        """單一條件觸發"""
        evaluator = ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0)],
        )
        result = evaluator.evaluate(50.0)
        assert result["HIGH_TEMP"] is True

    def test_single_condition_not_triggered(self, high_temp_alarm):
        """單一條件未觸發"""
        evaluator = ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0)],
        )
        result = evaluator.evaluate(40.0)
        assert result["HIGH_TEMP"] is False

    def test_multiple_conditions(self, high_temp_alarm, low_temp_alarm):
        """多條件評估"""
        evaluator = ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[
                ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0),
                ThresholdCondition(alarm=low_temp_alarm, operator=Operator.LT, value=0.0),
            ],
        )
        # 高溫觸發
        result = evaluator.evaluate(50.0)
        assert result["HIGH_TEMP"] is True
        assert result["LOW_TEMP"] is False

        # 低溫觸發
        result = evaluator.evaluate(-5.0)
        assert result["HIGH_TEMP"] is False
        assert result["LOW_TEMP"] is True

        # 正常溫度
        result = evaluator.evaluate(25.0)
        assert result["HIGH_TEMP"] is False
        assert result["LOW_TEMP"] is False

    def test_value_none(self, high_temp_alarm):
        """值為 None 返回空字典"""
        evaluator = ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0)],
        )
        result = evaluator.evaluate(None)
        assert result == {}

    def test_value_string_convertible(self, high_temp_alarm):
        """字串可轉換"""
        evaluator = ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0)],
        )
        result = evaluator.evaluate("50.5")
        assert result["HIGH_TEMP"] is True

    def test_value_string_not_convertible(self, high_temp_alarm):
        """字串無法轉換返回空字典"""
        evaluator = ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0)],
        )
        result = evaluator.evaluate("not_a_number")
        assert result == {}

    def test_value_integer(self, high_temp_alarm):
        """整數值"""
        evaluator = ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0)],
        )
        result = evaluator.evaluate(50)
        assert result["HIGH_TEMP"] is True

    def test_get_alarms(self, high_temp_alarm, low_temp_alarm):
        """取得所有告警定義"""
        evaluator = ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[
                ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0),
                ThresholdCondition(alarm=low_temp_alarm, operator=Operator.LT, value=0.0),
            ],
        )
        alarms = evaluator.get_alarms()
        assert len(alarms) == 2
        assert high_temp_alarm in alarms
        assert low_temp_alarm in alarms

    def test_empty_conditions(self):
        """空條件列表"""
        evaluator = ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[],
        )
        result = evaluator.evaluate(50.0)
        assert result == {}


# ======================== AlarmEvaluator Protocol Tests ========================


class TestAlarmEvaluatorProtocol:
    """AlarmEvaluator 協議測試"""

    def test_bitmask_is_evaluator(self, bit0_alarm):
        """BitMaskAlarmEvaluator 是 AlarmEvaluator"""
        evaluator = BitMaskAlarmEvaluator(point_name="test", bit_alarms={0: bit0_alarm})
        assert isinstance(evaluator, AlarmEvaluator)

    def test_table_is_evaluator(self, fault_code_1_alarm):
        """TableAlarmEvaluator 是 AlarmEvaluator"""
        evaluator = TableAlarmEvaluator(point_name="test", table={1: fault_code_1_alarm})
        assert isinstance(evaluator, AlarmEvaluator)

    def test_threshold_is_evaluator(self, high_temp_alarm):
        """ThresholdAlarmEvaluator 是 AlarmEvaluator"""
        evaluator = ThresholdAlarmEvaluator(
            point_name="test",
            conditions=[ThresholdCondition(alarm=high_temp_alarm, operator=Operator.GT, value=45.0)],
        )
        assert isinstance(evaluator, AlarmEvaluator)
