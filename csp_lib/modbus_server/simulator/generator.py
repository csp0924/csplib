# =============== Modbus Server - Generator Simulator ===============
#
# 發電機模擬器

from __future__ import annotations

import math
from enum import IntEnum
from typing import Any

from csp_lib.core import get_logger
from csp_lib.modbus import Float32, UInt16

from ..behaviors import AlarmBehavior, RampBehavior
from ..config import AlarmPointConfig, GeneratorSimConfig, SimulatedDeviceConfig, SimulatedPoint
from .base import BaseDeviceSimulator

logger = get_logger(__name__)


class GeneratorState(IntEnum):
    """發電機狀態"""

    STANDBY = 0
    STARTING = 1
    RUNNING = 2
    STOPPING = 3


def default_generator_config(
    device_id: str = "gen_1",
    unit_id: int = 40,
    base_address: int = 0,
    alarm_points: tuple[AlarmPointConfig, ...] = (),
) -> SimulatedDeviceConfig:
    """建立預設發電機配置"""
    f32 = Float32()
    u16 = UInt16()
    addr = base_address

    points = [
        SimulatedPoint(name="start_cmd", address=addr, data_type=u16, initial_value=0, writable=True),
    ]
    addr += u16.register_count

    points.append(SimulatedPoint(name="p_setpoint", address=addr, data_type=f32, initial_value=0.0, writable=True))
    addr += f32.register_count

    points.append(SimulatedPoint(name="p_actual", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="q_actual", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="frequency", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="voltage", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="rpm", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(
        SimulatedPoint(name="operating_state", address=addr, data_type=u16, initial_value=GeneratorState.STANDBY)
    )
    addr += u16.register_count

    points.append(SimulatedPoint(name="alarm_register", address=addr, data_type=u16, initial_value=0))

    return SimulatedDeviceConfig(
        device_id=device_id,
        unit_id=unit_id,
        points=tuple(points),
        alarm_points=alarm_points,
    )


class GeneratorSimulator(BaseDeviceSimulator):
    """
    發電機模擬器

    Features:
    - 狀態機: standby → starting(延遲) → running → stopping → standby
    - 啟動延遲 + RampBehavior 功率爬升
    - RPM / 頻率 / 電壓 聯動
    - 告警管理
    """

    def __init__(
        self,
        config: SimulatedDeviceConfig | None = None,
        sim_config: GeneratorSimConfig | None = None,
        startup_delay: float = 5.0,
        ramp_rate: float = 50.0,
        shutdown_delay: float = 3.0,
        rated_rpm: float = 1800.0,
        power_factor: float = 0.8,
        tick_interval: float = 1.0,
    ) -> None:
        if config is None:
            config = default_generator_config()
        super().__init__(config)

        if sim_config is None:
            sim_config = GeneratorSimConfig(
                startup_delay=startup_delay,
                ramp_rate=ramp_rate,
                shutdown_delay=shutdown_delay,
                rated_rpm=rated_rpm,
                power_factor=power_factor,
                tick_interval=tick_interval,
            )
        self._sim_config = sim_config
        self._startup_delay = self._sim_config.startup_delay
        self._shutdown_delay = self._sim_config.shutdown_delay
        self._rated_rpm = self._sim_config.rated_rpm
        self._power_factor = self._sim_config.power_factor
        self._tick_interval = self._sim_config.tick_interval

        self._state = GeneratorState.STANDBY
        self._state_timer: float = 0.0
        self._p_ramp = RampBehavior(ramp_rate=self._sim_config.ramp_rate)

        # Alarm behaviors
        self._alarms: dict[str, AlarmBehavior] = {}
        for ap in config.alarm_points:
            self._alarms[ap.alarm_code] = AlarmBehavior(
                alarm_code=ap.alarm_code,
                bit_position=ap.bit_position,
                reset_mode=ap.reset_mode,
            )

    @property
    def state(self) -> GeneratorState:
        return self._state

    def on_write(self, name: str, old_value: Any, new_value: Any) -> None:
        """處理 client 寫入"""
        super().on_write(name, old_value, new_value)

        if name == "start_cmd":
            cmd = int(new_value)
            if cmd == 1 and self._state == GeneratorState.STANDBY:
                self._state = GeneratorState.STARTING
                self._state_timer = self._startup_delay
                self.set_value("operating_state", GeneratorState.STARTING)
                logger.info(f"Generator {self.device_id}: Starting...")
            elif cmd == 0 and self._state == GeneratorState.RUNNING:
                self._state = GeneratorState.STOPPING
                self._state_timer = self._shutdown_delay
                self._p_ramp.target = 0.0
                self.set_value("operating_state", GeneratorState.STOPPING)
                logger.info(f"Generator {self.device_id}: Stopping...")

        elif name == "p_setpoint" and self._state == GeneratorState.RUNNING:
            self._p_ramp.target = float(new_value)

    def trigger_alarm(self, alarm_code: str) -> None:
        """觸發告警"""
        alarm = self._alarms.get(alarm_code)
        if alarm:
            alarm.update(trigger_condition=True)
            self._update_alarm_register()

    def clear_alarm_condition(self, alarm_code: str) -> None:
        """清除告警條件"""
        alarm = self._alarms.get(alarm_code)
        if alarm:
            alarm.update(trigger_condition=False)
            self._update_alarm_register()

    async def update(self) -> None:
        """模擬更新"""
        dt = self._tick_interval

        if self._state == GeneratorState.STARTING:
            self._state_timer -= dt
            if self._state_timer <= 0:
                self._state = GeneratorState.RUNNING
                self.set_value("operating_state", GeneratorState.RUNNING)
                self.set_value("rpm", self._rated_rpm)
                self.set_value("frequency", 60.0)
                self.set_value("voltage", 380.0)
                logger.info(f"Generator {self.device_id}: Running")
            else:
                # 啟動中 RPM 漸增
                progress = 1.0 - (self._state_timer / self._startup_delay)
                self.set_value("rpm", self._rated_rpm * progress)
            return

        if self._state == GeneratorState.STOPPING:
            self._state_timer -= dt
            p = self._p_ramp.update(dt)
            self.set_value("p_actual", p)
            if self._state_timer <= 0:
                self._state = GeneratorState.STANDBY
                self.set_value("operating_state", GeneratorState.STANDBY)
                self.set_value("p_actual", 0.0)
                self.set_value("q_actual", 0.0)
                self.set_value("rpm", 0.0)
                self.set_value("frequency", 0.0)
                self.set_value("voltage", 0.0)
                logger.info(f"Generator {self.device_id}: Standby")
            return

        if self._state == GeneratorState.RUNNING:
            p = self._p_ramp.update(dt)
            self.set_value("p_actual", p)

            # Q = P * tan(acos(pf))
            if self._power_factor < 1.0 and abs(p) > 1e-6:
                q = p * math.tan(math.acos(self._power_factor))
            else:
                q = 0.0
            self.set_value("q_actual", q)
            return

        # STANDBY — 所有值歸零已在 stopping → standby 設定

    def _update_alarm_register(self) -> None:
        """更新 alarm register"""
        reg_value = 0
        for alarm in self._alarms.values():
            if alarm.is_active:
                reg_value |= 1 << alarm.bit_position
        self.set_value("alarm_register", reg_value)

    def reset(self) -> None:
        """重置到初始狀態"""
        super().reset()
        self._state = GeneratorState.STANDBY
        self._state_timer = 0.0
        self._p_ramp.reset()
        for alarm in self._alarms.values():
            alarm.reset()


__all__ = ["GeneratorSimulator", "GeneratorState", "default_generator_config"]
