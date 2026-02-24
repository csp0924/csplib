# =============== Modbus Server Tests - Solar ===============
#
# 太陽能模擬器單元測試

import pytest

from csp_lib.modbus_server.config import AlarmPointConfig, AlarmResetMode
from csp_lib.modbus_server.simulator.solar import SolarSimulator, SolarState, default_solar_config


class TestSolarSimulator:
    """SolarSimulator 測試"""

    def test_default_config(self):
        sim = SolarSimulator()
        assert sim.device_id == "solar_1"
        assert sim.unit_id == 20
        assert sim.state == SolarState.STANDBY

    def test_set_target_power_starts_running(self):
        """設定目標功率後進入 RUNNING"""
        sim = SolarSimulator()
        sim.set_target_power(50.0)
        assert sim.state == SolarState.RUNNING
        assert sim.target_dc_power == 50.0

    def test_zero_power_returns_to_standby(self):
        """功率歸零後回到 STANDBY"""
        sim = SolarSimulator()
        sim.set_target_power(50.0)
        sim.set_target_power(0.0)
        assert sim.state == SolarState.STANDBY

    @pytest.mark.asyncio
    async def test_running_produces_power(self):
        """RUNNING 狀態產出功率"""
        sim = SolarSimulator(power_noise=0.0)
        sim.set_target_power(100.0)

        await sim.update()
        dc = sim.get_value("dc_power")
        ac = sim.get_value("ac_power")
        assert dc > 0
        assert ac > 0
        assert ac <= dc  # AC ≤ DC (efficiency)

    @pytest.mark.asyncio
    async def test_standby_zero_power(self):
        """STANDBY 狀態功率為零"""
        sim = SolarSimulator()
        await sim.update()
        assert sim.get_value("dc_power") == 0.0
        assert sim.get_value("ac_power") == 0.0

    @pytest.mark.asyncio
    async def test_fault_zero_power(self):
        """FAULT 狀態功率為零"""
        sim = SolarSimulator()
        sim.set_target_power(100.0)
        sim.set_fault()

        await sim.update()
        assert sim.get_value("dc_power") == 0.0
        assert sim.get_value("ac_power") == 0.0

    def test_fault_and_clear(self):
        """故障設定與清除"""
        sim = SolarSimulator()
        sim.set_fault()
        assert sim.state == SolarState.FAULT
        sim.clear_fault()
        assert sim.state == SolarState.STANDBY

    @pytest.mark.asyncio
    async def test_daily_energy_accumulates(self):
        """日發電量累積"""
        sim = SolarSimulator(power_noise=0.0, tick_interval=3600.0)
        sim.set_target_power(100.0)

        await sim.update()
        # dc_power ≈ 100, ac_power ≈ 95 (efficiency=0.95)
        # daily_energy = 95 * 3600 / 3600 ≈ 95 kWh
        energy = sim.get_value("daily_energy")
        assert energy > 0

    def test_alarm_trigger_and_clear(self):
        """告警觸發與清除"""
        alarm_cfg = (AlarmPointConfig(alarm_code="GRID_FAULT", bit_position=0, reset_mode=AlarmResetMode.AUTO),)
        config = default_solar_config(alarm_points=alarm_cfg)
        sim = SolarSimulator(config=config)

        sim.trigger_alarm("GRID_FAULT")
        assert sim.get_value("alarm_register") & 0x01 == 1

        sim.clear_alarm_condition("GRID_FAULT")
        assert sim.get_value("alarm_register") & 0x01 == 0

    def test_reset(self):
        """重置到初始狀態"""
        sim = SolarSimulator()
        sim.set_target_power(100.0)
        sim.reset()
        assert sim.state == SolarState.STANDBY
        assert sim.target_dc_power == 0.0
