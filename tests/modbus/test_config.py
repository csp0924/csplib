# =============== Modbus Tests - Config ===============
#
# 設定模組單元測試

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.modbus import (
    ByteOrder,
    ModbusConfigError,
    ModbusRtuConfig,
    ModbusTcpConfig,
    Parity,
    RegisterOrder,
)


class TestModbusTcpConfig:
    """ModbusTcpConfig 測試"""

    def test_valid_config(self):
        config = ModbusTcpConfig(host="192.168.1.100")
        assert config.host == "192.168.1.100"
        assert config.port == 502
        assert config.timeout == 0.5
        assert config.byte_order == ByteOrder.BIG_ENDIAN
        assert config.register_order == RegisterOrder.HIGH_FIRST

    def test_custom_values(self):
        config = ModbusTcpConfig(
            host="10.0.0.1",
            port=5020,
            timeout=1.0,
            byte_order=ByteOrder.LITTLE_ENDIAN,
            register_order=RegisterOrder.LOW_FIRST,
        )
        assert config.host == "10.0.0.1"
        assert config.port == 5020
        assert config.timeout == 1.0
        assert config.byte_order == ByteOrder.LITTLE_ENDIAN
        assert config.register_order == RegisterOrder.LOW_FIRST

    def test_empty_host_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusTcpConfig(host="")

    def test_port_too_low_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusTcpConfig(host="localhost", port=0)

    def test_port_too_high_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusTcpConfig(host="localhost", port=65536)

    def test_negative_timeout_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusTcpConfig(host="localhost", timeout=-1.0)

    def test_zero_timeout_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusTcpConfig(host="localhost", timeout=0)

    def test_config_is_frozen(self):
        config = ModbusTcpConfig(host="localhost")
        with pytest.raises(FrozenInstanceError):
            config.host = "changed"


class TestModbusRtuConfig:
    """ModbusRtuConfig 測試"""

    def test_valid_config(self):
        config = ModbusRtuConfig(port="COM1")
        assert config.port == "COM1"
        assert config.baudrate == 9600
        assert config.parity == Parity.NONE
        assert config.stopbits == 1
        assert config.bytesize == 8
        assert config.timeout == 0.5
        assert config.byte_order == ByteOrder.BIG_ENDIAN
        assert config.register_order == RegisterOrder.HIGH_FIRST

    def test_custom_values(self):
        config = ModbusRtuConfig(
            port="/dev/ttyUSB0",
            baudrate=115200,
            parity=Parity.EVEN,
            stopbits=2,
            bytesize=7,
            timeout=2.0,
        )
        assert config.port == "/dev/ttyUSB0"
        assert config.baudrate == 115200
        assert config.parity == Parity.EVEN
        assert config.stopbits == 2
        assert config.bytesize == 7
        assert config.timeout == 2.0

    def test_empty_port_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusRtuConfig(port="")

    def test_negative_baudrate_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusRtuConfig(port="COM1", baudrate=-9600)

    def test_zero_baudrate_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusRtuConfig(port="COM1", baudrate=0)

    def test_invalid_stopbits_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusRtuConfig(port="COM1", stopbits=3)

    def test_invalid_bytesize_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusRtuConfig(port="COM1", bytesize=9)

    def test_negative_timeout_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusRtuConfig(port="COM1", timeout=-1.0)

    def test_config_is_frozen(self):
        config = ModbusRtuConfig(port="COM1")
        with pytest.raises(FrozenInstanceError):
            config.baudrate = 19200
