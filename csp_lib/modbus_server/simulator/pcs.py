# =============== Modbus Server - PCS Simulator ===============
#
# PCS (Power Conversion System) 模擬器 — 最複雜的設備

from __future__ import annotations

import math
from typing import Any

from csp_lib.core import get_logger
from csp_lib.modbus import Float32, UInt16

from ..behaviors import AlarmBehavior, RampBehavior
from ..config import AlarmPointConfig, AlarmResetMode, PCSSimConfig, SimulatedDeviceConfig, SimulatedPoint
from .base import BaseDeviceSimulator

logger = get_logger("csp_lib.modbus_server.simulator.pcs")


def default_pcs_config(
    device_id: str = "pcs_1",
    unit_id: int = 10,
    base_address: int = 0,
    alarm_points: tuple[AlarmPointConfig, ...] = (),
) -> SimulatedDeviceConfig:
    """建立預設 PCS 配置"""
    f32 = Float32()
    u16 = UInt16()
    addr = base_address

    points = [
        SimulatedPoint(name="p_setpoint", address=addr, data_type=f32, initial_value=0.0, writable=True),
    ]
    addr += f32.register_count

    points.append(SimulatedPoint(name="q_setpoint", address=addr, data_type=f32, initial_value=0.0, writable=True))
    addr += f32.register_count

    points.append(SimulatedPoint(name="p_actual", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="q_actual", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="soc", address=addr, data_type=f32, initial_value=50.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="operating_mode", address=addr, data_type=u16, initial_value=0))
    addr += u16.register_count

    points.append(SimulatedPoint(name="alarm_register_1", address=addr, data_type=u16, initial_value=0))
    addr += u16.register_count

    points.append(SimulatedPoint(name="alarm_register_2", address=addr, data_type=u16, initial_value=0))
    addr += u16.register_count

    points.append(SimulatedPoint(name="alarm_reset_cmd", address=addr, data_type=u16, initial_value=0, writable=True))
    addr += u16.register_count

    points.append(SimulatedPoint(name="start_cmd", address=addr, data_type=u16, initial_value=0, writable=True))
    addr += u16.register_count

    points.append(SimulatedPoint(name="voltage", address=addr, data_type=f32, initial_value=380.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="frequency", address=addr, data_type=f32, initial_value=60.0))

    return SimulatedDeviceConfig(
        device_id=device_id,
        unit_id=unit_id,
        points=tuple(points),
        alarm_points=alarm_points,
    )


class PCSSimulator(BaseDeviceSimulator):
    """
    PCS 模擬器

    Features:
    - P/Q setpoint 寫入 → RampBehavior 按斜率趨近
    - SOC 追蹤：根據 p_actual 動態計算
    - 告警管理：auto-reset (register_1) + manual-reset (register_2)
    - 啟停控制：start_cmd 寫入

    Sign convention: +discharge / -charge
    """

    def __init__(
        self,
        config: SimulatedDeviceConfig | None = None,
        sim_config: PCSSimConfig | None = None,
        capacity_kwh: float = 100.0,
        p_ramp_rate: float = 100.0,
        q_ramp_rate: float = 100.0,
        tick_interval: float = 1.0,
    ) -> None:
        if config is None:
            config = default_pcs_config()
        super().__init__(config)

        if sim_config is None:
            sim_config = PCSSimConfig(
                capacity_kwh=capacity_kwh,
                p_ramp_rate=p_ramp_rate,
                q_ramp_rate=q_ramp_rate,
                tick_interval=tick_interval,
            )
        self._sim_config = sim_config
        self._capacity_kwh = self._sim_config.capacity_kwh
        self._tick_interval = self._sim_config.tick_interval
        self._running = False

        # Ramp behaviors
        self._p_ramp = RampBehavior(ramp_rate=self._sim_config.p_ramp_rate)
        self._q_ramp = RampBehavior(ramp_rate=self._sim_config.q_ramp_rate)

        # Alarm behaviors — 從 config 建立
        self._alarms: dict[str, AlarmBehavior] = {}
        for ap in config.alarm_points:
            self._alarms[ap.alarm_code] = AlarmBehavior(
                alarm_code=ap.alarm_code,
                bit_position=ap.bit_position,
                reset_mode=ap.reset_mode,
            )
        self._alarm_config_map: dict[str, AlarmPointConfig] = {ap.alarm_code: ap for ap in config.alarm_points}

    @property
    def capacity_kwh(self) -> float:
        return self._capacity_kwh

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def alarms(self) -> dict[str, AlarmBehavior]:
        return dict(self._alarms)

    def on_write(self, name: str, old_value: Any, new_value: Any) -> None:
        """處理 client 寫入"""
        super().on_write(name, old_value, new_value)

        if name == "p_setpoint":
            self._p_ramp.target = float(new_value)
            logger.debug(f"PCS {self.device_id}: P setpoint → {new_value}")

        elif name == "q_setpoint":
            self._q_ramp.target = float(new_value)
            logger.debug(f"PCS {self.device_id}: Q setpoint → {new_value}")

        elif name == "start_cmd":
            if int(new_value) == 1:
                self._running = True
                self.set_value("operating_mode", 1)
                logger.info(f"PCS {self.device_id}: Started")
            elif int(new_value) == 0:
                self._running = False
                self._p_ramp.target = 0.0
                self._q_ramp.target = 0.0
                self.set_value("operating_mode", 0)
                logger.info(f"PCS {self.device_id}: Stopped")

        elif name == "alarm_reset_cmd":
            if int(new_value) == 1:
                self._handle_alarm_reset()
                # 自動清除 reset 命令
                self.set_value("alarm_reset_cmd", 0)

    def trigger_alarm(self, alarm_code: str) -> None:
        """觸發指定告警"""
        alarm = self._alarms.get(alarm_code)
        if alarm:
            alarm.update(trigger_condition=True)
            self._update_alarm_registers()

    def clear_alarm_condition(self, alarm_code: str) -> None:
        """清除告警觸發條件（auto-reset 的會自動清除）"""
        alarm = self._alarms.get(alarm_code)
        if alarm:
            alarm.update(trigger_condition=False)
            self._update_alarm_registers()

    def update_soc(self, dt: float) -> None:
        """
        根據實際功率更新 SOC

        ΔSOC = -P_actual * dt / capacity_kwh / 3600 * 100
        放電(+P) → SOC 減少，充電(-P) → SOC 增加
        """
        p_actual = float(self.get_value("p_actual") or 0.0)
        if abs(p_actual) < 1e-6:
            return

        current_soc = float(self.get_value("soc") or 50.0)
        delta_soc = -p_actual * dt / self._capacity_kwh / 3600.0 * 100.0
        new_soc = max(0.0, min(100.0, current_soc + delta_soc))
        self.set_value("soc", new_soc)

    async def update(self) -> None:
        """模擬更新"""
        if not self._running:
            # 停機時功率歸零
            if abs(float(self.get_value("p_actual") or 0.0)) > 1e-6:
                self._p_ramp.target = 0.0
                p = self._p_ramp.update(self._tick_interval)
                self.set_value("p_actual", p)
            if abs(float(self.get_value("q_actual") or 0.0)) > 1e-6:
                self._q_ramp.target = 0.0
                q = self._q_ramp.update(self._tick_interval)
                self.set_value("q_actual", q)
            return

        # Ramp P/Q toward setpoints
        p = self._p_ramp.update(self._tick_interval)
        q = self._q_ramp.update(self._tick_interval)
        self.set_value("p_actual", p)
        self.set_value("q_actual", q)

    def _handle_alarm_reset(self) -> None:
        """處理告警重置命令"""
        for alarm in self._alarms.values():
            if alarm.reset_mode == AlarmResetMode.MANUAL:
                alarm.manual_reset()
            elif alarm.reset_mode == AlarmResetMode.LATCHED:
                alarm.force_reset()
        self._update_alarm_registers()
        logger.info(f"PCS {self.device_id}: Alarm reset executed")

    def _update_alarm_registers(self) -> None:
        """更新 alarm register 值"""
        reg1_value = 0
        reg2_value = 0

        for code, alarm in self._alarms.items():
            if not alarm.is_active:
                continue
            cfg = self._alarm_config_map.get(code)
            if cfg is None:
                continue
            # auto-reset alarms → register_1, manual/latched → register_2
            if alarm.reset_mode == AlarmResetMode.AUTO:
                reg1_value |= 1 << alarm.bit_position
            else:
                reg2_value |= 1 << alarm.bit_position

        self.set_value("alarm_register_1", reg1_value)
        self.set_value("alarm_register_2", reg2_value)

    def reset(self) -> None:
        """重置到初始狀態"""
        super().reset()
        self._running = False
        self._p_ramp.reset()
        self._q_ramp.reset()
        for alarm in self._alarms.values():
            alarm.reset()


__all__ = ["PCSSimulator", "default_pcs_config"]
