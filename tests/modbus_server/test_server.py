# =============== Modbus Server Tests - Server ===============
#
# SimulationServer 單元測試

import pytest

from csp_lib.modbus import Float32, UInt16
from csp_lib.modbus_server.config import ServerConfig, SimulatedDeviceConfig, SimulatedPoint
from csp_lib.modbus_server.server import SimulatorDataBlock
from csp_lib.modbus_server.simulator.base import BaseDeviceSimulator


class SimpleSimulator(BaseDeviceSimulator):
    """測試用簡單模擬器"""

    def __init__(self, config: SimulatedDeviceConfig):
        super().__init__(config)
        self.update_count = 0
        self.write_log: list[tuple[str, object, object]] = []

    def on_write(self, name, old_value, new_value):
        super().on_write(name, old_value, new_value)
        self.write_log.append((name, old_value, new_value))

    async def update(self):
        self.update_count += 1


def _make_sim(unit_id: int = 1) -> SimpleSimulator:
    return SimpleSimulator(
        SimulatedDeviceConfig(
            device_id=f"test_{unit_id}",
            unit_id=unit_id,
            points=(
                SimulatedPoint(name="voltage", address=0, data_type=Float32(), initial_value=380.0),
                SimulatedPoint(name="setpoint", address=2, data_type=Float32(), initial_value=0.0, writable=True),
                SimulatedPoint(name="status", address=4, data_type=UInt16(), initial_value=1),
            ),
        )
    )


class TestSimulatorDataBlock:
    """SimulatorDataBlock 測試"""

    def test_read_values(self):
        """讀取 register 值"""
        sim = _make_sim()
        block = SimulatorDataBlock(sim)

        # Float32(380.0) 佔 address 0-1
        regs = block.getValues(0, 2)
        assert len(regs) == 2
        # 透過 codec 解碼驗證
        from csp_lib.modbus import ModbusCodec

        codec = ModbusCodec()
        value = codec.decode(Float32(), regs)
        assert abs(value - 380.0) < 0.01

    def test_write_triggers_on_write(self):
        """寫入觸發 on_write 回調"""
        sim = _make_sim()
        block = SimulatorDataBlock(sim)

        # 編碼新值
        from csp_lib.modbus import ModbusCodec

        codec = ModbusCodec()
        new_regs = codec.encode(Float32(), 100.0)

        block.setValues(2, new_regs)

        # 驗證 on_write 被呼叫
        assert len(sim.write_log) == 1
        name, old_val, new_val = sim.write_log[0]
        assert name == "setpoint"
        assert abs(old_val - 0.0) < 0.01
        assert abs(new_val - 100.0) < 0.01

    def test_write_readonly_no_callback(self):
        """寫入唯讀 register 不觸發 on_write"""
        sim = _make_sim()
        block = SimulatorDataBlock(sim)

        # voltage 是唯讀的
        from csp_lib.modbus import ModbusCodec

        codec = ModbusCodec()
        new_regs = codec.encode(Float32(), 220.0)
        block.setValues(0, new_regs)

        assert len(sim.write_log) == 0

    def test_write_no_change_no_callback(self):
        """值未變化不觸發 on_write"""
        sim = _make_sim()
        block = SimulatorDataBlock(sim)

        from csp_lib.modbus import ModbusCodec

        codec = ModbusCodec()
        # 寫入相同值
        same_regs = codec.encode(Float32(), 0.0)
        block.setValues(2, same_regs)

        assert len(sim.write_log) == 0


class TestSimulationServerConfig:
    """SimulationServer 配置測試"""

    def test_add_simulator(self):
        from csp_lib.modbus_server.server import SimulationServer

        server = SimulationServer()
        sim = _make_sim(unit_id=1)
        server.add_simulator(sim)
        assert 1 in server.simulators

    def test_add_duplicate_unit_id_raises(self):
        from csp_lib.modbus_server.server import SimulationServer

        server = SimulationServer()
        server.add_simulator(_make_sim(unit_id=1))
        with pytest.raises(ValueError, match="Unit ID 1 already registered"):
            server.add_simulator(_make_sim(unit_id=1))
