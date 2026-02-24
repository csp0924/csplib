# =============== Modbus Server Tests - PCS ===============
#
# PCS 模擬器單元測試

import pytest

from csp_lib.modbus_server.config import AlarmPointConfig, AlarmResetMode
from csp_lib.modbus_server.simulator.pcs import PCSSimulator, default_pcs_config


class TestPCSSimulatorBasic:
    """PCS 基本操作測試"""

    def test_default_config(self):
        sim = PCSSimulator()
        assert sim.device_id == "pcs_1"
        assert sim.unit_id == 10
        assert not sim.is_running

    def test_initial_values(self):
        sim = PCSSimulator()
        assert abs(sim.get_value("p_setpoint") - 0.0) < 0.01
        assert abs(sim.get_value("soc") - 50.0) < 0.01
        assert sim.get_value("operating_mode") == 0

    def test_start_stop(self):
        sim = PCSSimulator()

        # Start
        sim.on_write("start_cmd", 0, 1)
        assert sim.is_running
        assert sim.get_value("operating_mode") == 1

        # Stop
        sim.on_write("start_cmd", 1, 0)
        assert not sim.is_running
        assert sim.get_value("operating_mode") == 0


class TestPCSRamp:
    """PCS 功率斜率測試"""

    @pytest.mark.asyncio
    async def test_p_ramp(self):
        """P 按斜率趨近 setpoint"""
        sim = PCSSimulator(p_ramp_rate=50.0, tick_interval=1.0)
        sim.on_write("start_cmd", 0, 1)
        sim.on_write("p_setpoint", 0.0, 100.0)

        # 第 1 tick: 0 → 50
        await sim.update()
        p = sim.get_value("p_actual")
        assert abs(p - 50.0) < 0.01

        # 第 2 tick: 50 → 100
        await sim.update()
        p = sim.get_value("p_actual")
        assert abs(p - 100.0) < 0.01

    @pytest.mark.asyncio
    async def test_q_ramp(self):
        """Q 按斜率趨近 setpoint"""
        sim = PCSSimulator(q_ramp_rate=30.0, tick_interval=1.0)
        sim.on_write("start_cmd", 0, 1)
        sim.on_write("q_setpoint", 0.0, 60.0)

        await sim.update()
        q = sim.get_value("q_actual")
        assert abs(q - 30.0) < 0.01

    @pytest.mark.asyncio
    async def test_stopped_power_returns_to_zero(self):
        """停機後功率歸零"""
        sim = PCSSimulator(p_ramp_rate=1000.0, tick_interval=1.0)
        sim.on_write("start_cmd", 0, 1)
        sim.on_write("p_setpoint", 0.0, 100.0)
        await sim.update()
        assert abs(sim.get_value("p_actual") - 100.0) < 0.01

        # Stop
        sim.on_write("start_cmd", 1, 0)
        await sim.update()  # 功率開始歸零
        # 大 ramp_rate 下應該直接歸零
        assert abs(sim.get_value("p_actual")) < 0.01


class TestPCSSOC:
    """PCS SOC 追蹤測試"""

    def test_discharge_decreases_soc(self):
        """放電(+P)降低 SOC"""
        sim = PCSSimulator(capacity_kwh=100.0)
        sim.set_value("soc", 50.0)
        sim.set_value("p_actual", 100.0)  # 100 kW discharge

        sim.update_soc(dt=3600.0)  # 1 hour
        soc = sim.get_value("soc")
        # ΔSOC = -100 * 3600 / 100 / 3600 * 100 = -100%
        # Clamped to 0
        assert soc == 0.0

    def test_charge_increases_soc(self):
        """充電(-P)增加 SOC"""
        sim = PCSSimulator(capacity_kwh=100.0)
        sim.set_value("soc", 50.0)
        sim.set_value("p_actual", -50.0)  # 50 kW charge

        sim.update_soc(dt=3600.0)  # 1 hour
        soc = sim.get_value("soc")
        # ΔSOC = -(-50) * 3600 / 100 / 3600 * 100 = +50%
        assert abs(soc - 100.0) < 0.01

    def test_soc_clamped(self):
        """SOC 限制在 0-100"""
        sim = PCSSimulator(capacity_kwh=100.0)
        sim.set_value("soc", 5.0)
        sim.set_value("p_actual", 1000.0)  # 大量放電
        sim.update_soc(dt=3600.0)
        assert sim.get_value("soc") == 0.0

        sim.set_value("soc", 95.0)
        sim.set_value("p_actual", -1000.0)  # 大量充電
        sim.update_soc(dt=3600.0)
        assert sim.get_value("soc") == 100.0


class TestPCSAlarms:
    """PCS 告警測試"""

    def _make_alarm_config(self) -> tuple[AlarmPointConfig, ...]:
        return (
            AlarmPointConfig(alarm_code="OVER_TEMP", bit_position=0, reset_mode=AlarmResetMode.AUTO),
            AlarmPointConfig(alarm_code="DC_OV", bit_position=1, reset_mode=AlarmResetMode.MANUAL),
            AlarmPointConfig(alarm_code="CRITICAL_FAULT", bit_position=0, reset_mode=AlarmResetMode.LATCHED),
        )

    def test_auto_alarm_trigger_and_clear(self):
        """AUTO alarm 觸發與自動清除"""
        config = default_pcs_config(alarm_points=self._make_alarm_config())
        sim = PCSSimulator(config=config)

        sim.trigger_alarm("OVER_TEMP")
        assert sim.get_value("alarm_register_1") & 0x01 == 1

        sim.clear_alarm_condition("OVER_TEMP")
        assert sim.get_value("alarm_register_1") & 0x01 == 0

    def test_manual_alarm_persists(self):
        """MANUAL alarm 條件清除後仍保持"""
        config = default_pcs_config(alarm_points=self._make_alarm_config())
        sim = PCSSimulator(config=config)

        sim.trigger_alarm("DC_OV")
        assert sim.get_value("alarm_register_2") & 0x02 == 2

        sim.clear_alarm_condition("DC_OV")
        # Manual alarm 仍在
        assert sim.get_value("alarm_register_2") & 0x02 == 2

    def test_alarm_reset_cmd(self):
        """寫入 alarm_reset_cmd 重置 manual/latched alarms"""
        config = default_pcs_config(alarm_points=self._make_alarm_config())
        sim = PCSSimulator(config=config)

        sim.trigger_alarm("DC_OV")
        assert sim.get_value("alarm_register_2") & 0x02 == 2

        # 寫入 reset 命令
        sim.on_write("alarm_reset_cmd", 0, 1)
        assert sim.get_value("alarm_register_2") == 0
        # Reset 命令自動清除
        assert sim.get_value("alarm_reset_cmd") == 0

    def test_reset_clears_alarms(self):
        """reset() 清除所有告警"""
        config = default_pcs_config(alarm_points=self._make_alarm_config())
        sim = PCSSimulator(config=config)

        sim.trigger_alarm("OVER_TEMP")
        sim.trigger_alarm("DC_OV")
        sim.reset()

        assert sim.get_value("alarm_register_1") == 0
        assert sim.get_value("alarm_register_2") == 0
