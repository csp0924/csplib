# =============== Modbus Server Tests - Config ===============
#
# 配置 dataclasses 單元測試

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.modbus import ByteOrder, Float32, RegisterOrder, UInt16
from csp_lib.modbus_server.config import (
    AlarmPointConfig,
    AlarmResetMode,
    ControllabilityMode,
    MicrogridConfig,
    ServerConfig,
    SimulatedDeviceConfig,
    SimulatedPoint,
)


class TestAlarmResetMode:
    """告警重置模式列舉測試"""

    def test_enum_values(self):
        assert AlarmResetMode.AUTO.value == "auto"
        assert AlarmResetMode.MANUAL.value == "manual"
        assert AlarmResetMode.LATCHED.value == "latched"

    def test_from_string(self):
        assert AlarmResetMode("auto") == AlarmResetMode.AUTO
        assert AlarmResetMode("manual") == AlarmResetMode.MANUAL


class TestControllabilityMode:
    """可控性模式列舉測試"""

    def test_enum_values(self):
        assert ControllabilityMode.CONTROLLABLE.value == "controllable"
        assert ControllabilityMode.UNCONTROLLABLE.value == "uncontrollable"


class TestSimulatedPoint:
    """模擬點位配置測試"""

    def test_basic_creation(self):
        point = SimulatedPoint(name="voltage", address=0, data_type=Float32())
        assert point.name == "voltage"
        assert point.address == 0
        assert isinstance(point.data_type, Float32)
        assert point.initial_value == 0
        assert point.writable is False

    def test_writable_point(self):
        point = SimulatedPoint(
            name="setpoint",
            address=10,
            data_type=Float32(),
            initial_value=100.0,
            writable=True,
        )
        assert point.writable is True
        assert point.initial_value == 100.0

    def test_custom_byte_order(self):
        point = SimulatedPoint(
            name="test",
            address=0,
            data_type=UInt16(),
            byte_order=ByteOrder.LITTLE_ENDIAN,
            register_order=RegisterOrder.LOW_FIRST,
        )
        assert point.byte_order == ByteOrder.LITTLE_ENDIAN
        assert point.register_order == RegisterOrder.LOW_FIRST

    def test_frozen(self):
        point = SimulatedPoint(name="test", address=0, data_type=UInt16())
        with pytest.raises(FrozenInstanceError):
            point.name = "other"  # type: ignore[misc]


class TestAlarmPointConfig:
    """告警點位配置測試"""

    def test_auto_reset(self):
        cfg = AlarmPointConfig(alarm_code="OVER_TEMP", bit_position=0)
        assert cfg.reset_mode == AlarmResetMode.AUTO
        assert cfg.reset_address is None

    def test_manual_reset(self):
        cfg = AlarmPointConfig(
            alarm_code="DC_OV",
            bit_position=3,
            reset_mode=AlarmResetMode.MANUAL,
            reset_address=100,
            reset_value=1,
        )
        assert cfg.reset_mode == AlarmResetMode.MANUAL
        assert cfg.reset_address == 100
        assert cfg.reset_value == 1


class TestSimulatedDeviceConfig:
    """模擬設備配置測試"""

    def test_defaults(self):
        cfg = SimulatedDeviceConfig(device_id="test", unit_id=1)
        assert cfg.device_id == "test"
        assert cfg.unit_id == 1
        assert cfg.points == ()
        assert cfg.alarm_points == ()
        assert cfg.update_interval == 1.0

    def test_with_points(self):
        points = (
            SimulatedPoint(name="v", address=0, data_type=Float32()),
            SimulatedPoint(name="i", address=2, data_type=Float32()),
        )
        cfg = SimulatedDeviceConfig(device_id="meter", unit_id=1, points=points)
        assert len(cfg.points) == 2


class TestServerConfig:
    """伺服器配置測試"""

    def test_defaults(self):
        cfg = ServerConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 5020
        assert cfg.tick_interval == 1.0

    def test_custom(self):
        cfg = ServerConfig(host="0.0.0.0", port=5021, tick_interval=0.5)
        assert cfg.port == 5021
        assert cfg.tick_interval == 0.5


class TestMicrogridConfig:
    """微電網配置測試"""

    def test_defaults(self):
        cfg = MicrogridConfig()
        assert cfg.grid_voltage == 380.0
        assert cfg.grid_frequency == 60.0
        assert cfg.voltage_noise == 2.0
        assert cfg.frequency_noise == 0.02
