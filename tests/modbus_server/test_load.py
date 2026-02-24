# =============== Modbus Server Tests - Load ===============
#
# 負載模擬器單元測試

import pytest

from csp_lib.modbus_server.config import ControllabilityMode
from csp_lib.modbus_server.simulator.load import LoadSimulator


class TestLoadSimulatorControllable:
    """可控負載測試"""

    def test_default_controllable(self):
        sim = LoadSimulator()
        assert sim.controllability == ControllabilityMode.CONTROLLABLE

    def test_setpoint_write(self):
        """setpoint 寫入生效"""
        sim = LoadSimulator(ramp_rate=1000.0)
        sim.on_write("p_setpoint", 0.0, 50.0)

        # 由於 ramp_rate 很大，一步即到達
        import asyncio

        asyncio.get_event_loop().run_until_complete(sim.update())
        p = sim.get_value("p_actual")
        assert abs(p - 50.0) < 0.01

    @pytest.mark.asyncio
    async def test_ramp_to_setpoint(self):
        """按斜率趨近 setpoint"""
        sim = LoadSimulator(ramp_rate=20.0, tick_interval=1.0)
        sim.on_write("p_setpoint", 0.0, 50.0)

        await sim.update()
        p = sim.get_value("p_actual")
        assert abs(p - 20.0) < 0.01  # 1s * 20/s = 20

    @pytest.mark.asyncio
    async def test_q_calculated(self):
        """Q 由 power_factor 計算"""
        sim = LoadSimulator(power_factor=0.9, ramp_rate=1000.0, tick_interval=1.0)
        sim.on_write("p_setpoint", 0.0, 100.0)
        await sim.update()

        q = sim.get_value("q_actual")
        assert q > 0  # pf < 1 → Q > 0


class TestLoadSimulatorUncontrollable:
    """不可控負載測試"""

    def test_uncontrollable_ignores_setpoint(self):
        """不可控負載忽略 setpoint"""
        sim = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=100.0,
            load_noise=0.0,
        )
        sim.on_write("p_setpoint", 0.0, 200.0)
        # 寫入被忽略，不影響 base_load

    @pytest.mark.asyncio
    async def test_uncontrollable_uses_noise(self):
        """不可控負載用 NoiseBehavior"""
        sim = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=50.0,
            load_noise=0.0,
            tick_interval=1.0,
        )
        await sim.update()
        p = sim.get_value("p_actual")
        assert abs(p - 50.0) < 0.01

    def test_set_base_load(self):
        """設定基礎負載"""
        sim = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=0.0,
        )
        sim.set_base_load(75.0)
        # noise.base_value 更新
        assert sim._noise.base_value == 75.0

    def test_reset(self):
        """重置"""
        sim = LoadSimulator(ramp_rate=1000.0)
        sim.on_write("p_setpoint", 0.0, 100.0)
        sim.reset()
        assert abs(sim.get_value("p_actual") - 0.0) < 0.01
