# =============== Equipment Template Tests - Factory ===============
#
# DeviceFactory 設備工廠單元測試
#
# 測試覆蓋：
# - create: 基本建立、覆寫、位址偏移
# - create_batch: 批次建立、偏移、驗證
# - create_stride: 步幅建立、ID 格式化
# - 告警評估器 point_name 更新

from unittest.mock import MagicMock

import pytest

from csp_lib.equipment.alarm import (
    AlarmDefinition,
    AlarmLevel,
    BitMaskAlarmEvaluator,
    Operator,
    TableAlarmEvaluator,
    ThresholdAlarmEvaluator,
    ThresholdCondition,
)
from csp_lib.equipment.core import PointMetadata, ReadPoint, WritePoint
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.equipment.template import DeviceFactory, EquipmentTemplate, PointOverride
from csp_lib.modbus import Int16, UInt16


def _make_mock_client():
    """建立 mock Modbus 客戶端"""
    return MagicMock()


def _make_template(**kwargs):
    """建立測試用範本"""
    defaults = {
        "model": "TEST-100",
        "always_points": (
            ReadPoint(name="voltage", address=100, data_type=UInt16()),
            ReadPoint(name="current", address=101, data_type=Int16()),
        ),
        "write_points": (WritePoint(name="power_cmd", address=200, data_type=Int16()),),
    }
    defaults.update(kwargs)
    return EquipmentTemplate(**defaults)


def _make_config(**kwargs):
    """建立測試用設定"""
    defaults = {"device_id": "dev_01", "unit_id": 1}
    defaults.update(kwargs)
    return DeviceConfig(**defaults)


class TestDeviceFactoryCreate:
    """DeviceFactory.create 測試"""

    def test_create_basic(self):
        """基本建立應成功"""
        tpl = _make_template()
        config = _make_config()
        client = _make_mock_client()

        device = DeviceFactory.create(tpl, config, client)

        assert device.device_id == "dev_01"

    def test_create_with_address_offset(self):
        """位址偏移應加到所有點位"""
        rp = ReadPoint(name="voltage", address=100, data_type=UInt16())
        wp = WritePoint(name="cmd", address=200, data_type=Int16())
        tpl = EquipmentTemplate(model="TEST", always_points=(rp,), write_points=(wp,))
        config = _make_config()
        client = _make_mock_client()

        device = DeviceFactory.create(tpl, config, client, address_offset=50)

        # 透過內部 _scheduler 驗證點位位址已偏移
        groups = device._scheduler.get_next_groups()
        assert len(groups) > 0
        # 驗證讀取點位位址已偏移
        for group in groups:
            for point in group.points:
                assert point.address == 150  # 100 + 50

        # 驗證寫入點位位址已偏移
        assert device._write_points["cmd"].address == 250  # 200 + 50

    def test_create_with_overrides(self):
        """覆寫應重新命名點位"""
        tpl = _make_template()
        config = _make_config()
        client = _make_mock_client()

        overrides = {
            "voltage": PointOverride(name="bus_voltage", metadata=PointMetadata(unit="V")),
            "current": PointOverride(name="bus_current"),
        }

        device = DeviceFactory.create(tpl, config, client, overrides=overrides)

        # 讀取點位應已重新命名
        groups = device._scheduler.get_next_groups()
        point_names = set()
        for group in groups:
            for point in group.points:
                point_names.add(point.name)
        assert "bus_voltage" in point_names
        assert "bus_current" in point_names
        assert "voltage" not in point_names
        assert "current" not in point_names

    def test_create_with_write_point_override(self):
        """覆寫也應重新命名寫入點位"""
        tpl = _make_template()
        config = _make_config()
        client = _make_mock_client()

        overrides = {"power_cmd": PointOverride(name="active_power_cmd")}

        device = DeviceFactory.create(tpl, config, client, overrides=overrides)

        assert "active_power_cmd" in device._write_points
        assert "power_cmd" not in device._write_points

    def test_create_with_override_and_offset(self):
        """覆寫與偏移應同時生效"""
        rp = ReadPoint(name="ch0", address=0, data_type=UInt16())
        tpl = EquipmentTemplate(model="IO", always_points=(rp,))
        config = _make_config()
        client = _make_mock_client()

        device = DeviceFactory.create(
            tpl,
            config,
            client,
            overrides={"ch0": PointOverride(name="fan_status")},
            address_offset=10,
        )

        groups = device._scheduler.get_next_groups()
        for group in groups:
            for point in group.points:
                assert point.name == "fan_status"
                assert point.address == 10  # 0 + 10

    def test_create_with_rotating_points(self):
        """輪詢點位應正確處理"""
        rp_always = ReadPoint(name="always_pt", address=100, data_type=UInt16())
        rp_rot1 = ReadPoint(name="rot1", address=200, data_type=UInt16())
        rp_rot2 = ReadPoint(name="rot2", address=201, data_type=UInt16())

        tpl = EquipmentTemplate(
            model="TEST",
            always_points=(rp_always,),
            rotating_points=((rp_rot1,), (rp_rot2,)),
        )
        config = _make_config()
        client = _make_mock_client()

        device = DeviceFactory.create(tpl, config, client, address_offset=10)

        # 第一次呼叫 get_next_groups 應包含 always + rotating[0]
        groups = device._scheduler.get_next_groups()
        all_points = [p for g in groups for p in g.points]
        names = {p.name for p in all_points}
        assert "always_pt" in names

    def test_create_zero_offset_no_change(self):
        """offset=0 不應改變點位"""
        rp = ReadPoint(name="pt", address=42, data_type=UInt16())
        tpl = EquipmentTemplate(model="TEST", always_points=(rp,))
        config = _make_config()
        client = _make_mock_client()

        device = DeviceFactory.create(tpl, config, client, address_offset=0)

        groups = device._scheduler.get_next_groups()
        for group in groups:
            for point in group.points:
                assert point.address == 42


class TestDeviceFactoryCreateWithAlarms:
    """DeviceFactory.create 告警相關測試"""

    def test_alarm_evaluator_point_name_updated(self):
        """覆寫點位時告警評估器的 point_name 也應更新"""
        alarm_def = AlarmDefinition(code="FAULT", name="Fault", level=AlarmLevel.ALARM)
        evaluator = BitMaskAlarmEvaluator(point_name="fault_code", bit_alarms={0: alarm_def})
        rp = ReadPoint(name="fault_code", address=100, data_type=UInt16())

        tpl = EquipmentTemplate(model="TEST", always_points=(rp,), alarm_evaluators=(evaluator,))
        config = _make_config()
        client = _make_mock_client()

        overrides = {"fault_code": PointOverride(name="error_register")}
        device = DeviceFactory.create(tpl, config, client, overrides=overrides)

        # 驗證評估器的 point_name 已更新
        assert len(device._alarm_evaluators) == 1
        assert device._alarm_evaluators[0].point_name == "error_register"

    def test_table_evaluator_point_name_updated(self):
        """TableAlarmEvaluator 的 point_name 也應更新"""
        alarm_def = AlarmDefinition(code="ERR_01", name="Error 1", level=AlarmLevel.WARNING)
        evaluator = TableAlarmEvaluator(point_name="status_code", table={1: alarm_def})
        rp = ReadPoint(name="status_code", address=100, data_type=UInt16())

        tpl = EquipmentTemplate(model="TEST", always_points=(rp,), alarm_evaluators=(evaluator,))
        config = _make_config()
        client = _make_mock_client()

        overrides = {"status_code": PointOverride(name="device_status")}
        device = DeviceFactory.create(tpl, config, client, overrides=overrides)

        assert device._alarm_evaluators[0].point_name == "device_status"

    def test_threshold_evaluator_point_name_updated(self):
        """ThresholdAlarmEvaluator 的 point_name 也應更新"""
        alarm_def = AlarmDefinition(code="HIGH_TEMP", name="High Temperature", level=AlarmLevel.ALARM)
        evaluator = ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[ThresholdCondition(alarm=alarm_def, operator=Operator.GT, value=80.0)],
        )
        rp = ReadPoint(name="temperature", address=100, data_type=Int16())

        tpl = EquipmentTemplate(model="TEST", always_points=(rp,), alarm_evaluators=(evaluator,))
        config = _make_config()
        client = _make_mock_client()

        overrides = {"temperature": PointOverride(name="cpu_temp")}
        device = DeviceFactory.create(tpl, config, client, overrides=overrides)

        assert device._alarm_evaluators[0].point_name == "cpu_temp"

    def test_non_overridden_evaluator_unchanged(self):
        """未覆寫的告警評估器不應受影響"""
        alarm_def = AlarmDefinition(code="FAULT", name="Fault", level=AlarmLevel.ALARM)
        evaluator = BitMaskAlarmEvaluator(point_name="fault_code", bit_alarms={0: alarm_def})
        rp1 = ReadPoint(name="fault_code", address=100, data_type=UInt16())
        rp2 = ReadPoint(name="voltage", address=101, data_type=UInt16())

        tpl = EquipmentTemplate(model="TEST", always_points=(rp1, rp2), alarm_evaluators=(evaluator,))
        config = _make_config()
        client = _make_mock_client()

        # 只覆寫 voltage，不覆寫 fault_code
        overrides = {"voltage": PointOverride(name="bus_voltage")}
        device = DeviceFactory.create(tpl, config, client, overrides=overrides)

        assert device._alarm_evaluators[0].point_name == "fault_code"

    def test_original_template_not_mutated(self):
        """建立設備不應修改原始範本"""
        alarm_def = AlarmDefinition(code="FAULT", name="Fault", level=AlarmLevel.ALARM)
        evaluator = BitMaskAlarmEvaluator(point_name="fault_code", bit_alarms={0: alarm_def})
        rp = ReadPoint(name="fault_code", address=100, data_type=UInt16())

        tpl = EquipmentTemplate(model="TEST", always_points=(rp,), alarm_evaluators=(evaluator,))

        DeviceFactory.create(
            tpl,
            _make_config(),
            _make_mock_client(),
            overrides={"fault_code": PointOverride(name="renamed")},
            address_offset=50,
        )

        # 原始範本不應被修改
        assert tpl.always_points[0].name == "fault_code"
        assert tpl.always_points[0].address == 100
        assert tpl.alarm_evaluators[0].point_name == "fault_code"


class TestDeviceFactoryCreateBatch:
    """DeviceFactory.create_batch 測試"""

    def test_create_batch_basic(self):
        """批次建立應建立正確數量的設備"""
        tpl = _make_template()
        instances = [
            DeviceConfig(device_id=f"dev_{i}", unit_id=i) for i in range(1, 4)
        ]

        devices = DeviceFactory.create_batch(
            tpl,
            instances=instances,
            client_factory=lambda cfg: _make_mock_client(),
        )

        assert len(devices) == 3
        assert devices[0].device_id == "dev_1"
        assert devices[1].device_id == "dev_2"
        assert devices[2].device_id == "dev_3"

    def test_create_batch_with_offsets(self):
        """批次建立各自偏移應正確"""
        rp = ReadPoint(name="voltage", address=100, data_type=UInt16())
        tpl = EquipmentTemplate(model="TEST", always_points=(rp,))
        instances = [
            DeviceConfig(device_id=f"dev_{i}", unit_id=1) for i in range(3)
        ]

        devices = DeviceFactory.create_batch(
            tpl,
            instances=instances,
            client_factory=lambda cfg: _make_mock_client(),
            address_offsets=[0, 200, 500],
        )

        # 驗證各設備的點位位址
        for device, expected_addr in zip(devices, [100, 300, 600]):
            groups = device._scheduler.get_next_groups()
            for group in groups:
                for point in group.points:
                    assert point.address == expected_addr

    def test_create_batch_offset_length_mismatch(self):
        """偏移長度不一致應拋出 ValueError"""
        tpl = _make_template()
        instances = [DeviceConfig(device_id=f"dev_{i}", unit_id=1) for i in range(3)]

        with pytest.raises(ValueError, match="不一致"):
            DeviceFactory.create_batch(
                tpl,
                instances=instances,
                client_factory=lambda cfg: _make_mock_client(),
                address_offsets=[0, 100],  # 長度 2 != 3
            )

    def test_create_batch_with_shared_overrides(self):
        """覆寫應套用到所有實例"""
        tpl = _make_template()
        instances = [DeviceConfig(device_id=f"dev_{i}", unit_id=1) for i in range(2)]

        overrides = {"voltage": PointOverride(name="bus_voltage")}
        devices = DeviceFactory.create_batch(
            tpl,
            instances=instances,
            client_factory=lambda cfg: _make_mock_client(),
            overrides=overrides,
        )

        for device in devices:
            groups = device._scheduler.get_next_groups()
            point_names = {p.name for g in groups for p in g.points}
            assert "bus_voltage" in point_names
            assert "voltage" not in point_names

    def test_create_batch_client_factory_receives_config(self):
        """client_factory 應接收到正確的 config"""
        tpl = _make_template()
        received_configs = []

        def track_factory(cfg):
            received_configs.append(cfg)
            return _make_mock_client()

        instances = [
            DeviceConfig(device_id="dev_a", unit_id=1),
            DeviceConfig(device_id="dev_b", unit_id=2),
        ]

        DeviceFactory.create_batch(tpl, instances=instances, client_factory=track_factory)

        assert len(received_configs) == 2
        assert received_configs[0].device_id == "dev_a"
        assert received_configs[1].device_id == "dev_b"

    def test_create_batch_no_offsets(self):
        """不提供偏移時不應偏移"""
        rp = ReadPoint(name="pt", address=42, data_type=UInt16())
        tpl = EquipmentTemplate(model="TEST", always_points=(rp,))
        instances = [DeviceConfig(device_id=f"dev_{i}", unit_id=1) for i in range(2)]

        devices = DeviceFactory.create_batch(
            tpl,
            instances=instances,
            client_factory=lambda cfg: _make_mock_client(),
        )

        for device in devices:
            groups = device._scheduler.get_next_groups()
            for group in groups:
                for point in group.points:
                    assert point.address == 42


class TestDeviceFactoryCreateStride:
    """DeviceFactory.create_stride 測試"""

    def test_create_stride_basic(self):
        """步幅建立應建立正確數量與 ID"""
        tpl = _make_template()
        base_config = DeviceConfig(device_id="sub_bms", unit_id=1)

        devices = DeviceFactory.create_stride(
            tpl,
            base_config=base_config,
            client_factory=lambda cfg: _make_mock_client(),
            count=3,
            stride=100,
        )

        assert len(devices) == 3
        assert devices[0].device_id == "sub_bms_1"
        assert devices[1].device_id == "sub_bms_2"
        assert devices[2].device_id == "sub_bms_3"

    def test_create_stride_address_offsets(self):
        """步幅建立的位址偏移應為 i * stride"""
        rp = ReadPoint(name="voltage", address=0, data_type=UInt16())
        tpl = EquipmentTemplate(model="TEST", always_points=(rp,))
        base_config = DeviceConfig(device_id="rack", unit_id=1)

        devices = DeviceFactory.create_stride(
            tpl,
            base_config=base_config,
            client_factory=lambda cfg: _make_mock_client(),
            count=4,
            stride=50,
        )

        expected_addresses = [0, 50, 100, 150]
        for device, expected_addr in zip(devices, expected_addresses):
            groups = device._scheduler.get_next_groups()
            for group in groups:
                for point in group.points:
                    assert point.address == expected_addr

    def test_create_stride_custom_id_format(self):
        """自訂 ID 格式應正確"""
        tpl = _make_template()
        base_config = DeviceConfig(device_id="bms", unit_id=1)

        devices = DeviceFactory.create_stride(
            tpl,
            base_config=base_config,
            client_factory=lambda cfg: _make_mock_client(),
            count=2,
            stride=100,
            id_format="unit_{base_id}_{index}",
        )

        assert devices[0].device_id == "unit_bms_1"
        assert devices[1].device_id == "unit_bms_2"

    def test_create_stride_with_overrides(self):
        """步幅建立也應支援覆寫"""
        tpl = _make_template()
        base_config = DeviceConfig(device_id="sub", unit_id=1)

        overrides = {"voltage": PointOverride(name="cell_voltage")}
        devices = DeviceFactory.create_stride(
            tpl,
            base_config=base_config,
            client_factory=lambda cfg: _make_mock_client(),
            count=2,
            stride=100,
            overrides=overrides,
        )

        for device in devices:
            groups = device._scheduler.get_next_groups()
            point_names = {p.name for g in groups for p in g.points}
            assert "cell_voltage" in point_names
            assert "voltage" not in point_names

    def test_create_stride_count_one(self):
        """count=1 應建立一個設備，偏移 0"""
        rp = ReadPoint(name="pt", address=10, data_type=UInt16())
        tpl = EquipmentTemplate(model="TEST", always_points=(rp,))
        base_config = DeviceConfig(device_id="single", unit_id=1)

        devices = DeviceFactory.create_stride(
            tpl,
            base_config=base_config,
            client_factory=lambda cfg: _make_mock_client(),
            count=1,
            stride=100,
        )

        assert len(devices) == 1
        assert devices[0].device_id == "single_1"
        groups = devices[0]._scheduler.get_next_groups()
        for group in groups:
            for point in group.points:
                assert point.address == 10  # offset 0 * 100 = 0
