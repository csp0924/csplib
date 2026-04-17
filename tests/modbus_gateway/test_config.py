"""Tests for modbus_gateway config dataclasses — validation and defaults."""

import pytest

from csp_lib.modbus import ByteOrder, RegisterOrder
from csp_lib.modbus.types.numeric import UInt16
from csp_lib.modbus_gateway.config import (
    GatewayRegisterDef,
    GatewayServerConfig,
    RegisterType,
    WatchdogConfig,
    WriteRule,
)

# ===========================================================================
# GatewayRegisterDef
# ===========================================================================


class TestGatewayRegisterDef:
    def test_valid_construction(self):
        reg = GatewayRegisterDef(name="power", address=100, data_type=UInt16())
        assert reg.name == "power"
        assert reg.address == 100
        assert reg.scale == 1.0
        assert reg.register_type == RegisterType.HOLDING

    def test_frozen(self):
        reg = GatewayRegisterDef(name="power", address=100, data_type=UInt16())
        with pytest.raises(AttributeError):
            reg.name = "other"  # type: ignore[misc]

    def test_negative_address_raises(self):
        with pytest.raises(ValueError, match="address must be >= 0"):
            GatewayRegisterDef(name="bad", address=-1, data_type=UInt16())

    def test_zero_scale_raises(self):
        with pytest.raises(ValueError, match="scale must not be zero"):
            GatewayRegisterDef(name="bad", address=0, data_type=UInt16(), scale=0)

    def test_valid_with_all_fields(self):
        reg = GatewayRegisterDef(
            name="voltage",
            address=200,
            data_type=UInt16(),
            register_type=RegisterType.INPUT,
            scale=10.0,
            unit="V",
            initial_value=2200,
            description="Bus voltage",
            byte_order=ByteOrder.LITTLE_ENDIAN,
            register_order=RegisterOrder.LOW_FIRST,
        )
        assert reg.unit == "V"
        assert reg.register_type == RegisterType.INPUT


# ===========================================================================
# WriteRule
# ===========================================================================


class TestWriteRule:
    def test_defaults(self):
        rule = WriteRule(register_name="test")
        assert rule.min_value is None
        assert rule.max_value is None
        assert rule.clamp is False

    def test_with_bounds(self):
        rule = WriteRule(register_name="test", min_value=-1000, max_value=1000, clamp=True)
        assert rule.min_value == -1000
        assert rule.max_value == 1000
        assert rule.clamp is True


# ===========================================================================
# WatchdogConfig
# ===========================================================================


class TestWatchdogConfig:
    def test_defaults(self):
        cfg = WatchdogConfig()
        assert cfg.timeout_seconds == 60.0
        assert cfg.check_interval == 5.0
        assert cfg.enabled is True

    def test_zero_timeout_raises(self):
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            WatchdogConfig(timeout_seconds=0)

    def test_negative_timeout_raises(self):
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            WatchdogConfig(timeout_seconds=-1)

    def test_zero_check_interval_raises(self):
        with pytest.raises(ValueError, match="check_interval must be > 0"):
            WatchdogConfig(check_interval=0)

    def test_negative_check_interval_raises(self):
        with pytest.raises(ValueError, match="check_interval must be > 0"):
            WatchdogConfig(check_interval=-5)

    def test_disabled(self):
        cfg = WatchdogConfig(enabled=False)
        assert cfg.enabled is False


# ===========================================================================
# GatewayServerConfig
# ===========================================================================


class TestGatewayServerConfig:
    def test_defaults(self):
        cfg = GatewayServerConfig()
        # v0.7.3 SEC-011: 預設 bind localhost（安全限定）
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 502
        assert cfg.unit_id == 1
        assert cfg.byte_order == ByteOrder.BIG_ENDIAN
        assert cfg.register_order == RegisterOrder.HIGH_FIRST
        assert cfg.register_space_size == 10000

    def test_unit_id_too_low_raises(self):
        with pytest.raises(ValueError, match="unit_id must be 1-247"):
            GatewayServerConfig(unit_id=0)

    def test_unit_id_too_high_raises(self):
        with pytest.raises(ValueError, match="unit_id must be 1-247"):
            GatewayServerConfig(unit_id=248)

    def test_port_negative_raises(self):
        with pytest.raises(ValueError, match="port must be 0-65535"):
            GatewayServerConfig(port=-1)

    def test_port_too_high_raises(self):
        with pytest.raises(ValueError, match="port must be 0-65535"):
            GatewayServerConfig(port=70000)

    def test_valid_boundary_values(self):
        """Test boundary values that should be valid."""
        cfg_low = GatewayServerConfig(unit_id=1, port=0)
        assert cfg_low.unit_id == 1
        assert cfg_low.port == 0

        cfg_high = GatewayServerConfig(unit_id=247, port=65535)
        assert cfg_high.unit_id == 247
        assert cfg_high.port == 65535
