# =============== Modbus Server Tests - Simulator Base ===============
#
# BaseDeviceSimulator 單元測試

import pytest

from csp_lib.modbus import Float32, UInt16
from csp_lib.modbus_server.config import SimulatedDeviceConfig, SimulatedPoint
from csp_lib.modbus_server.simulator.base import BaseDeviceSimulator


class ConcreteSimulator(BaseDeviceSimulator):
    """測試用具體模擬器"""

    def __init__(self, config: SimulatedDeviceConfig):
        super().__init__(config)
        self.update_count = 0

    async def update(self):
        self.update_count += 1


def _make_config() -> SimulatedDeviceConfig:
    f32 = Float32()
    u16 = UInt16()
    return SimulatedDeviceConfig(
        device_id="test_device",
        unit_id=1,
        points=(
            SimulatedPoint(name="voltage", address=0, data_type=f32, initial_value=380.0),
            SimulatedPoint(name="power", address=2, data_type=f32, initial_value=0.0, writable=True),
            SimulatedPoint(name="status", address=4, data_type=u16, initial_value=1),
        ),
    )


class TestBaseDeviceSimulator:
    """BaseDeviceSimulator 測試"""

    def test_properties(self):
        config = _make_config()
        sim = ConcreteSimulator(config)
        assert sim.device_id == "test_device"
        assert sim.unit_id == 1

    def test_initial_values(self):
        """初始值正確設定"""
        sim = ConcreteSimulator(_make_config())
        assert abs(sim.get_value("voltage") - 380.0) < 0.01
        assert abs(sim.get_value("power") - 0.0) < 0.01
        assert sim.get_value("status") == 1

    def test_set_and_get_value(self):
        """設定和讀取值"""
        sim = ConcreteSimulator(_make_config())
        sim.set_value("voltage", 220.0)
        assert abs(sim.get_value("voltage") - 220.0) < 0.01

    def test_register_block_sync(self):
        """set_value 同步更新 register_block"""
        sim = ConcreteSimulator(_make_config())
        sim.set_value("power", 50.0)

        # 透過 register_block 讀取
        block_value = sim.register_block.get_value("power")
        assert abs(block_value - 50.0) < 0.01

    def test_on_write_default(self):
        """預設 on_write 更新 _values"""
        sim = ConcreteSimulator(_make_config())
        sim.on_write("power", 0.0, 100.0)
        assert sim.get_value("power") == 100.0

    def test_reset(self):
        """重置到初始狀態"""
        sim = ConcreteSimulator(_make_config())
        sim.set_value("voltage", 220.0)
        sim.set_value("power", 100.0)
        sim.set_value("status", 0)

        sim.reset()

        assert abs(sim.get_value("voltage") - 380.0) < 0.01
        assert abs(sim.get_value("power") - 0.0) < 0.01
        assert sim.get_value("status") == 1

    @pytest.mark.asyncio
    async def test_update(self):
        """update 被呼叫"""
        sim = ConcreteSimulator(_make_config())
        await sim.update()
        assert sim.update_count == 1
