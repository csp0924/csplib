# =============== Modbus Server - Solar Simulator ===============
#
# 太陽能模擬器

from __future__ import annotations

from enum import IntEnum

from csp_lib.core import get_logger
from csp_lib.modbus import Float32, UInt16

from ..behaviors import AlarmBehavior, NoiseBehavior
from ..config import AlarmPointConfig, SimulatedDeviceConfig, SimulatedPoint, SolarSimConfig
from .base import BaseDeviceSimulator

logger = get_logger(__name__)


class SolarState(IntEnum):
    """太陽能狀態"""

    STANDBY = 0
    RUNNING = 1
    FAULT = 2


def default_solar_config(
    device_id: str = "solar_1",
    unit_id: int = 20,
    base_address: int = 0,
    alarm_points: tuple[AlarmPointConfig, ...] = (),
) -> SimulatedDeviceConfig:
    """建立預設太陽能配置"""
    f32 = Float32()
    u16 = UInt16()
    addr = base_address

    points = [
        SimulatedPoint(name="dc_power", address=addr, data_type=f32, initial_value=0.0),
    ]
    addr += f32.register_count

    points.append(SimulatedPoint(name="ac_power", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="ac_voltage", address=addr, data_type=f32, initial_value=380.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="ac_current", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="frequency", address=addr, data_type=f32, initial_value=60.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="daily_energy", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="status", address=addr, data_type=u16, initial_value=SolarState.STANDBY))
    addr += u16.register_count

    points.append(SimulatedPoint(name="alarm_register", address=addr, data_type=u16, initial_value=0))

    return SimulatedDeviceConfig(
        device_id=device_id,
        unit_id=unit_id,
        points=tuple(points),
        alarm_points=alarm_points,
    )


class SolarSimulator(BaseDeviceSimulator):
    """
    太陽能模擬器

    Features:
    - 可設定目標 DC 功率（模擬日照變化）
    - 可配置轉換效率 (DC → AC)
    - NoiseBehavior 產生功率波動
    - 狀態機: standby → running → fault
    - 告警管理
    """

    def __init__(
        self,
        config: SimulatedDeviceConfig | None = None,
        sim_config: SolarSimConfig | None = None,
        efficiency: float = 0.95,
        power_noise: float = 0.5,
        tick_interval: float = 1.0,
    ) -> None:
        if config is None:
            config = default_solar_config()
        super().__init__(config)

        if sim_config is None:
            sim_config = SolarSimConfig(
                efficiency=efficiency,
                power_noise=power_noise,
                tick_interval=tick_interval,
            )
        self._sim_config = sim_config
        self._efficiency = self._sim_config.efficiency
        self._tick_interval = self._sim_config.tick_interval
        self._target_dc_power: float = 0.0
        self._state = SolarState.STANDBY
        self._daily_energy: float = 0.0
        self._power_noise = NoiseBehavior(amplitude=self._sim_config.power_noise)

        # Alarm behaviors
        self._alarms: dict[str, AlarmBehavior] = {}
        for ap in config.alarm_points:
            self._alarms[ap.alarm_code] = AlarmBehavior(
                alarm_code=ap.alarm_code,
                bit_position=ap.bit_position,
                reset_mode=ap.reset_mode,
            )

    @property
    def state(self) -> SolarState:
        return self._state

    @property
    def target_dc_power(self) -> float:
        return self._target_dc_power

    def set_target_power(self, dc_power: float) -> None:
        """設定目標 DC 功率（模擬日照變化）"""
        self._target_dc_power = max(0.0, dc_power)
        if dc_power > 0 and self._state == SolarState.STANDBY:
            self._state = SolarState.RUNNING
            self.set_value("status", SolarState.RUNNING)
        elif dc_power <= 0 and self._state == SolarState.RUNNING:
            self._state = SolarState.STANDBY
            self.set_value("status", SolarState.STANDBY)

    def set_fault(self) -> None:
        """進入故障狀態"""
        self._state = SolarState.FAULT
        self.set_value("status", SolarState.FAULT)

    def clear_fault(self) -> None:
        """清除故障狀態"""
        if self._state == SolarState.FAULT:
            self._state = SolarState.STANDBY
            self.set_value("status", SolarState.STANDBY)

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
        if self._state == SolarState.FAULT:
            self.set_value("dc_power", 0.0)
            self.set_value("ac_power", 0.0)
            self.set_value("ac_current", 0.0)
            return

        if self._state == SolarState.STANDBY or self._target_dc_power <= 0:
            self.set_value("dc_power", 0.0)
            self.set_value("ac_power", 0.0)
            self.set_value("ac_current", 0.0)
            return

        # DC 功率加擾動
        self._power_noise.base_value = self._target_dc_power
        dc_power = max(0.0, self._power_noise.update())
        self.set_value("dc_power", dc_power)

        # AC = DC * efficiency
        ac_power = dc_power * self._efficiency
        self.set_value("ac_power", ac_power)

        # 電流
        voltage = float(self.get_value("ac_voltage") or 380.0)
        current = ac_power / (1.732 * voltage) if voltage > 1e-6 else 0.0
        self.set_value("ac_current", current)

        # 累積日發電量
        self._daily_energy += ac_power * self._tick_interval / 3600.0
        self.set_value("daily_energy", self._daily_energy)

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
        self._state = SolarState.STANDBY
        self._target_dc_power = 0.0
        self._daily_energy = 0.0
        for alarm in self._alarms.values():
            alarm.reset()


__all__ = ["SolarSimulator", "SolarState", "default_solar_config"]
