# =============== Equipment Template Tests - Definition ===============
#
# EquipmentTemplate / PointOverride 單元測試
#
# 測試覆蓋：
# - 建立與預設值
# - 不可變性
# - 各欄位正確存取

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.equipment.alarm import AlarmDefinition, AlarmLevel, BitMaskAlarmEvaluator
from csp_lib.equipment.core import PointMetadata, ReadPoint, WritePoint
from csp_lib.equipment.template import EquipmentTemplate, PointOverride
from csp_lib.modbus import Int16, UInt16


class TestPointOverride:
    """PointOverride 建立與不可變性測試"""

    def test_create_with_name_only(self):
        """只提供名稱應成功建立"""
        override = PointOverride(name="new_name")

        assert override.name == "new_name"
        assert override.metadata is None

    def test_create_with_metadata(self):
        """提供名稱與元資料應成功建立"""
        meta = PointMetadata(unit="kW", description="Active power")
        override = PointOverride(name="active_power", metadata=meta)

        assert override.name == "active_power"
        assert override.metadata is meta
        assert override.metadata.unit == "kW"

    def test_frozen_immutable(self):
        """frozen=True 應使物件不可變"""
        override = PointOverride(name="test")
        with pytest.raises(FrozenInstanceError):
            override.name = "other"  # type: ignore[misc]


class TestEquipmentTemplate:
    """EquipmentTemplate 建立與不可變性測試"""

    def test_create_minimal(self):
        """只提供 model 應成功建立"""
        tpl = EquipmentTemplate(model="TEST-100")

        assert tpl.model == "TEST-100"
        assert tpl.always_points == ()
        assert tpl.rotating_points == ()
        assert tpl.write_points == ()
        assert tpl.alarm_evaluators == ()
        assert tpl.aggregator_pipeline is None
        assert tpl.description == ""

    def test_create_with_points(self):
        """提供點位應正確存取"""
        rp = ReadPoint(name="voltage", address=100, data_type=UInt16())
        wp = WritePoint(name="cmd", address=200, data_type=Int16())

        tpl = EquipmentTemplate(
            model="INV-50",
            always_points=(rp,),
            write_points=(wp,),
            description="Test inverter",
        )

        assert len(tpl.always_points) == 1
        assert tpl.always_points[0].name == "voltage"
        assert len(tpl.write_points) == 1
        assert tpl.write_points[0].name == "cmd"
        assert tpl.description == "Test inverter"

    def test_create_with_rotating_points(self):
        """提供輪詢點位群組應正確存取"""
        rp1 = ReadPoint(name="temp1", address=300, data_type=Int16())
        rp2 = ReadPoint(name="temp2", address=301, data_type=Int16())

        tpl = EquipmentTemplate(
            model="BMS-SUB",
            rotating_points=((rp1,), (rp2,)),
        )

        assert len(tpl.rotating_points) == 2
        assert tpl.rotating_points[0][0].name == "temp1"
        assert tpl.rotating_points[1][0].name == "temp2"

    def test_create_with_alarm_evaluators(self):
        """提供告警評估器應正確存取"""
        alarm_def = AlarmDefinition(code="FAULT_01", name="Overcurrent", level=AlarmLevel.ALARM)
        evaluator = BitMaskAlarmEvaluator(point_name="fault_code", bit_alarms={0: alarm_def})

        tpl = EquipmentTemplate(
            model="INV-100",
            alarm_evaluators=(evaluator,),
        )

        assert len(tpl.alarm_evaluators) == 1
        assert tpl.alarm_evaluators[0].point_name == "fault_code"

    def test_frozen_immutable(self):
        """frozen=True 應使物件不可變"""
        tpl = EquipmentTemplate(model="TEST")
        with pytest.raises(FrozenInstanceError):
            tpl.model = "OTHER"  # type: ignore[misc]

    def test_tuple_fields_immutable(self):
        """tuple 欄位不可就地修改"""
        rp = ReadPoint(name="voltage", address=100, data_type=UInt16())
        tpl = EquipmentTemplate(model="TEST", always_points=(rp,))

        # tuple 本身不支援 append
        with pytest.raises(AttributeError):
            tpl.always_points.append(rp)  # type: ignore[attr-defined]
