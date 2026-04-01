"""Tests for csp_lib.core.errors."""

import pytest

from csp_lib.core.errors import (
    AlarmError,
    CommunicationError,
    ConfigurationError,
    DeviceConnectionError,
    DeviceError,
    DeviceRegistryError,
    ProtectionError,
    StrategyExecutionError,
)


class TestDeviceError:
    def test_device_id_in_message(self):
        err = DeviceError("pcs1", "something failed")
        assert err.device_id == "pcs1"
        assert "[pcs1]" in str(err)
        assert "something failed" in str(err)

    def test_subclass_caught_by_device_error(self):
        with pytest.raises(DeviceError):
            raise DeviceConnectionError("pcs1", "connection lost")

    def test_connection_error(self):
        err = DeviceConnectionError("pcs2", "timeout")
        assert isinstance(err, DeviceError)
        assert err.device_id == "pcs2"

    def test_communication_error(self):
        err = CommunicationError("pcs3", "decode failed")
        assert isinstance(err, DeviceError)
        assert err.device_id == "pcs3"


class TestAlarmError:
    def test_alarm_code(self):
        err = AlarmError("pcs1", "OVER_TEMP", "temperature exceeded")
        assert err.device_id == "pcs1"
        assert err.alarm_code == "OVER_TEMP"
        assert "temperature exceeded" in str(err)

    def test_caught_by_device_error(self):
        with pytest.raises(DeviceError):
            raise AlarmError("pcs1", "SOC_LOW", "soc too low")


class TestConfigurationError:
    def test_independent_of_device_error(self):
        err = ConfigurationError("invalid mapping")
        assert not isinstance(err, DeviceError)
        assert isinstance(err, Exception)
        assert "invalid mapping" in str(err)


class TestStrategyExecutionError:
    def test_instantiation_and_attributes(self):
        err = StrategyExecutionError("PQStrategy", "power limit exceeded")
        assert err.strategy_name == "PQStrategy"
        assert "Strategy 'PQStrategy': power limit exceeded" == str(err)

    def test_not_device_error(self):
        err = StrategyExecutionError("FPStrategy", "frequency drift")
        assert not isinstance(err, DeviceError)
        assert isinstance(err, Exception)

    def test_caught_by_own_type(self):
        with pytest.raises(StrategyExecutionError):
            raise StrategyExecutionError("QVStrategy", "voltage out of range")


class TestProtectionError:
    def test_instantiation_and_attributes(self):
        err = ProtectionError("over_voltage", "voltage above 110%")
        assert err.rule_name == "over_voltage"
        assert "Protection rule 'over_voltage': voltage above 110%" == str(err)

    def test_not_device_error(self):
        err = ProtectionError("under_frequency", "freq below 59.5Hz")
        assert not isinstance(err, DeviceError)
        assert isinstance(err, Exception)

    def test_caught_by_own_type(self):
        with pytest.raises(ProtectionError):
            raise ProtectionError("soc_limit", "SOC below minimum")


class TestDeviceRegistryError:
    def test_instantiation_and_attributes(self):
        err = DeviceRegistryError("pcs1", "device not found")
        assert err.device_id == "pcs1"
        assert "[pcs1]" in str(err)
        assert "device not found" in str(err)

    def test_is_device_error(self):
        err = DeviceRegistryError("bms2", "already registered")
        assert isinstance(err, DeviceError)
        assert isinstance(err, Exception)

    def test_caught_by_device_error(self):
        with pytest.raises(DeviceError):
            raise DeviceRegistryError("pcs3", "lookup failed")
