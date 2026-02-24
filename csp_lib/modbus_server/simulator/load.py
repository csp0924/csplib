# =============== Modbus Server - Load Simulator ===============
#
# 負載模擬器

from __future__ import annotations

from typing import Any

from csp_lib.core import get_logger
from csp_lib.modbus import Float32, UInt16

from ..behaviors import NoiseBehavior, RampBehavior
from ..config import ControllabilityMode, LoadSimConfig, SimulatedDeviceConfig, SimulatedPoint
from .base import BaseDeviceSimulator

logger = get_logger("csp_lib.modbus_server.simulator.load")


def default_load_config(
    device_id: str = "load_1",
    unit_id: int = 30,
    base_address: int = 0,
    controllable: bool = True,
) -> SimulatedDeviceConfig:
    """建立預設負載配置"""
    f32 = Float32()
    u16 = UInt16()
    addr = base_address

    points = [
        SimulatedPoint(
            name="p_setpoint",
            address=addr,
            data_type=f32,
            initial_value=0.0,
            writable=controllable,
        ),
    ]
    addr += f32.register_count

    points.append(SimulatedPoint(name="p_actual", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="q_actual", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="voltage", address=addr, data_type=f32, initial_value=380.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="current", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="frequency", address=addr, data_type=f32, initial_value=60.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="status", address=addr, data_type=u16, initial_value=1))

    return SimulatedDeviceConfig(device_id=device_id, unit_id=unit_id, points=tuple(points))


class LoadSimulator(BaseDeviceSimulator):
    """
    負載模擬器

    Features:
    - CONTROLLABLE: 回應 setpoint 寫入，用 RampBehavior 調整
    - UNCONTROLLABLE: 忽略寫入，用 NoiseBehavior 自行變化
    - 功率因數可配置
    """

    def __init__(
        self,
        config: SimulatedDeviceConfig | None = None,
        sim_config: LoadSimConfig | None = None,
        controllability: ControllabilityMode = ControllabilityMode.CONTROLLABLE,
        power_factor: float = 0.9,
        ramp_rate: float = 50.0,
        base_load: float = 0.0,
        load_noise: float = 2.0,
        tick_interval: float = 1.0,
    ) -> None:
        if sim_config is None:
            sim_config = LoadSimConfig(
                controllability=controllability,
                power_factor=power_factor,
                ramp_rate=ramp_rate,
                base_load=base_load,
                load_noise=load_noise,
                tick_interval=tick_interval,
            )
        self._sim_config = sim_config

        if config is None:
            config = default_load_config(
                controllable=(self._sim_config.controllability == ControllabilityMode.CONTROLLABLE)
            )
        super().__init__(config)

        self._controllability = self._sim_config.controllability
        self._power_factor = self._sim_config.power_factor
        self._tick_interval = self._sim_config.tick_interval

        # Controllable mode
        self._p_ramp = RampBehavior(ramp_rate=self._sim_config.ramp_rate)

        # Uncontrollable mode
        self._noise = NoiseBehavior(base_value=self._sim_config.base_load, amplitude=self._sim_config.load_noise)

    @property
    def controllability(self) -> ControllabilityMode:
        return self._controllability

    @property
    def power_factor(self) -> float:
        return self._power_factor

    def set_base_load(self, power: float) -> None:
        """設定基礎負載（不可控模式用）"""
        self._noise.base_value = power

    def on_write(self, name: str, old_value: Any, new_value: Any) -> None:
        """處理 client 寫入"""
        super().on_write(name, old_value, new_value)

        if name == "p_setpoint":
            if self._controllability == ControllabilityMode.CONTROLLABLE:
                self._p_ramp.target = float(new_value)
                logger.debug(f"Load {self.device_id}: P setpoint → {new_value}")
            else:
                logger.debug(f"Load {self.device_id}: Ignoring setpoint write (uncontrollable)")

    async def update(self) -> None:
        """模擬更新"""
        if self._controllability == ControllabilityMode.CONTROLLABLE:
            p = self._p_ramp.update(self._tick_interval)
        else:
            p = max(0.0, self._noise.update())

        self.set_value("p_actual", p)

        # Q = P * tan(acos(pf))
        import math

        if self._power_factor < 1.0:
            q = p * math.tan(math.acos(self._power_factor))
        else:
            q = 0.0
        self.set_value("q_actual", q)

        # 電流
        voltage = float(self.get_value("voltage") or 380.0)
        s = (p**2 + q**2) ** 0.5
        current = s / (1.732 * voltage) if voltage > 1e-6 else 0.0
        self.set_value("current", current)

    def reset(self) -> None:
        """重置到初始狀態"""
        super().reset()
        self._p_ramp.reset()
        self._noise.reset()


__all__ = ["LoadSimulator", "default_load_config"]
