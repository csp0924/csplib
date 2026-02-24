# =============== Modbus Server Tests - Generator ===============
#
# 發電機模擬器單元測試

import pytest

from csp_lib.modbus_server.config import AlarmPointConfig, AlarmResetMode
from csp_lib.modbus_server.simulator.generator import GeneratorSimulator, GeneratorState, default_generator_config


class TestGeneratorStateMachine:
    """發電機狀態機測試"""

    def test_initial_standby(self):
        sim = GeneratorSimulator()
        assert sim.state == GeneratorState.STANDBY

    def test_start_command_transitions_to_starting(self):
        sim = GeneratorSimulator()
        sim.on_write("start_cmd", 0, 1)
        assert sim.state == GeneratorState.STARTING
        assert sim.get_value("operating_state") == GeneratorState.STARTING

    @pytest.mark.asyncio
    async def test_starting_to_running(self):
        """啟動延遲後進入 RUNNING"""
        sim = GeneratorSimulator(startup_delay=2.0, tick_interval=1.0)
        sim.on_write("start_cmd", 0, 1)

        await sim.update()  # 1s elapsed, timer = 1.0
        assert sim.state == GeneratorState.STARTING

        await sim.update()  # 2s elapsed, timer = 0.0
        assert sim.state == GeneratorState.RUNNING
        assert sim.get_value("operating_state") == GeneratorState.RUNNING
        assert sim.get_value("rpm") == 1800.0

    @pytest.mark.asyncio
    async def test_stop_command_transitions_to_stopping(self):
        """RUNNING → stop → STOPPING"""
        sim = GeneratorSimulator(startup_delay=0.5, shutdown_delay=1.0, tick_interval=1.0)
        sim.on_write("start_cmd", 0, 1)
        await sim.update()  # → RUNNING
        assert sim.state == GeneratorState.RUNNING

        sim.on_write("start_cmd", 1, 0)
        assert sim.state == GeneratorState.STOPPING

    @pytest.mark.asyncio
    async def test_stopping_to_standby(self):
        """STOPPING → STANDBY"""
        sim = GeneratorSimulator(startup_delay=0.5, shutdown_delay=1.0, tick_interval=1.0)
        sim.on_write("start_cmd", 0, 1)
        await sim.update()  # → RUNNING

        sim.on_write("start_cmd", 1, 0)
        await sim.update()  # → STANDBY
        assert sim.state == GeneratorState.STANDBY
        assert sim.get_value("p_actual") == 0.0
        assert sim.get_value("rpm") == 0.0

    def test_start_cmd_ignored_when_not_standby(self):
        """非 STANDBY 狀態忽略啟動命令"""
        sim = GeneratorSimulator()
        sim.on_write("start_cmd", 0, 1)  # → STARTING
        sim.on_write("start_cmd", 1, 1)  # 重複寫入忽略
        assert sim.state == GeneratorState.STARTING


class TestGeneratorPowerRamp:
    """發電機功率爬升測試"""

    @pytest.mark.asyncio
    async def test_power_ramp_when_running(self):
        """RUNNING 狀態下功率按斜率爬升"""
        sim = GeneratorSimulator(startup_delay=0.5, ramp_rate=25.0, tick_interval=1.0)
        sim.on_write("start_cmd", 0, 1)
        await sim.update()  # → RUNNING

        sim.on_write("p_setpoint", 0.0, 100.0)
        await sim.update()
        p = sim.get_value("p_actual")
        assert abs(p - 25.0) < 0.01

    @pytest.mark.asyncio
    async def test_setpoint_ignored_when_not_running(self):
        """非 RUNNING 狀態忽略 setpoint"""
        sim = GeneratorSimulator()
        sim.on_write("p_setpoint", 0.0, 100.0)
        # STANDBY 狀態，不處理 setpoint
        await sim.update()
        assert abs(sim.get_value("p_actual") - 0.0) < 0.01


class TestGeneratorAlarms:
    """發電機告警測試"""

    def test_alarm_trigger(self):
        alarm_cfg = (
            AlarmPointConfig(alarm_code="LOW_OIL", bit_position=0, reset_mode=AlarmResetMode.AUTO),
        )
        config = default_generator_config(alarm_points=alarm_cfg)
        sim = GeneratorSimulator(config=config)

        sim.trigger_alarm("LOW_OIL")
        assert sim.get_value("alarm_register") & 0x01 == 1

        sim.clear_alarm_condition("LOW_OIL")
        assert sim.get_value("alarm_register") & 0x01 == 0


class TestGeneratorReset:
    """發電機重置測試"""

    @pytest.mark.asyncio
    async def test_reset(self):
        sim = GeneratorSimulator(startup_delay=0.5, tick_interval=1.0)
        sim.on_write("start_cmd", 0, 1)
        await sim.update()  # → RUNNING

        sim.reset()
        assert sim.state == GeneratorState.STANDBY
        assert sim.get_value("p_actual") == 0.0
