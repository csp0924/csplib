# =============== Modbus Server - Power Meter Simulator ===============
#
# 電表模擬器（唯讀設備）

from __future__ import annotations

from typing import Any

from csp_lib.modbus import Float32, UInt16

from ..behaviors import NoiseBehavior
from ..behaviors.noise import NoiseType
from ..config import PowerMeterSimConfig, SimulatedDeviceConfig, SimulatedPoint
from .base import BaseDeviceSimulator


def default_meter_config(
    device_id: str = "meter_1",
    unit_id: int = 1,
    base_address: int = 0,
    power_sign: float = 1.0,
) -> SimulatedDeviceConfig:
    """建立預設電表配置"""
    f32 = Float32()
    u16 = UInt16()
    addr = base_address
    points = []

    for name in ("voltage_a", "voltage_b", "voltage_c"):
        points.append(SimulatedPoint(name=name, address=addr, data_type=f32, initial_value=380.0))
        addr += f32.register_count

    for name in ("current_a", "current_b", "current_c"):
        points.append(SimulatedPoint(name=name, address=addr, data_type=f32, initial_value=0.0))
        addr += f32.register_count

    points.append(SimulatedPoint(name="active_power", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="reactive_power", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="apparent_power", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="power_factor", address=addr, data_type=f32, initial_value=1.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="frequency", address=addr, data_type=f32, initial_value=60.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="energy_total", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="status", address=addr, data_type=u16, initial_value=1))

    return SimulatedDeviceConfig(device_id=device_id, unit_id=unit_id, points=tuple(points))


class PowerMeterSimulator(BaseDeviceSimulator):
    """
    電表模擬器

    唯讀設備，透過 NoiseBehavior 產生電壓/頻率波動。
    可透過 set_system_reading() 由 MicrogridSimulator 設定功率值。

    Attributes:
        power_sign: 功率正負號配置（+1.0 或 -1.0）
    """

    def __init__(
        self,
        config: SimulatedDeviceConfig | None = None,
        sim_config: PowerMeterSimConfig | None = None,
        power_sign: float = 1.0,
        voltage_noise: float = 2.0,
        frequency_noise: float = 0.02,
    ) -> None:
        if config is None:
            config = default_meter_config()
        super().__init__(config)
        if sim_config is None:
            sim_config = PowerMeterSimConfig(
                power_sign=power_sign,
                voltage_noise=voltage_noise,
                frequency_noise=frequency_noise,
            )
        self._sim_config = sim_config
        self._power_sign = self._sim_config.power_sign
        self._voltage_noise = NoiseBehavior(base_value=380.0, amplitude=self._sim_config.voltage_noise)
        self._frequency_noise = NoiseBehavior(base_value=60.0, amplitude=self._sim_config.frequency_noise)
        self._accumulated_energy: float = 0.0

    @property
    def power_sign(self) -> float:
        return self._power_sign

    def set_system_reading(self, v: float, f: float, p: float, q: float) -> None:
        """
        由 MicrogridSimulator 呼叫，設定系統功率平衡結果

        Args:
            v: 系統電壓 (V)
            f: 系統頻率 (Hz)
            p: 有功功率 (kW)
            q: 無功功率 (kVar)
        """
        signed_p = p * self._power_sign
        signed_q = q * self._power_sign

        # 設定三相電壓（加個別小擾動）
        for phase in ("voltage_a", "voltage_b", "voltage_c"):
            self._voltage_noise.base_value = v
            phase_v = self._voltage_noise.update()
            self.set_value(phase, phase_v)

        # 功率
        self.set_value("active_power", signed_p)
        self.set_value("reactive_power", signed_q)

        # 視在功率與功率因數
        s = (signed_p**2 + signed_q**2) ** 0.5
        pf = abs(signed_p / s) if s > 1e-6 else 1.0
        self.set_value("apparent_power", s)
        self.set_value("power_factor", pf)

        # 頻率
        self._frequency_noise.base_value = f
        self.set_value("frequency", self._frequency_noise.update())

        # 電流 (I = S / (sqrt(3) * V))
        current = s / (1.732 * v) if v > 1e-6 else 0.0
        for phase in ("current_a", "current_b", "current_c"):
            self.set_value(phase, current)

    def accumulate_energy(self, power_kw: float, dt: float) -> None:
        """累積電量 (kWh)"""
        self._accumulated_energy += power_kw * dt / 3600.0
        self.set_value("energy_total", self._accumulated_energy)

    async def update(self) -> None:
        """自主更新（無 MicrogridSimulator 時）"""
        # 電壓和頻率加擾動
        for phase in ("voltage_a", "voltage_b", "voltage_c"):
            self.set_value(phase, self._voltage_noise.update())
        self.set_value("frequency", self._frequency_noise.update())


__all__ = ["PowerMeterSimulator", "default_meter_config"]
