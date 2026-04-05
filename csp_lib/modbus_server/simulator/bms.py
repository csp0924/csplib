# =============== Modbus Server - BMS Simulator ===============
#
# BMS (Battery Management System) 模擬器

from __future__ import annotations

from csp_lib.core import get_logger
from csp_lib.modbus import Float32, UInt16

from ..config import BMSSimConfig, SimulatedDeviceConfig, SimulatedPoint
from .base import BaseDeviceSimulator

logger = get_logger(__name__)


def default_bms_config(
    device_id: str = "bms_1",
    unit_id: int = 20,
    base_address: int = 0,
) -> SimulatedDeviceConfig:
    """建立預設 BMS 配置

    Args:
        device_id: 設備識別碼
        unit_id: Modbus slave ID
        base_address: Register 起始位址

    Returns:
        預設 BMS 模擬設備配置
    """
    f32 = Float32()
    u16 = UInt16()
    addr = base_address

    points: list[SimulatedPoint] = []

    points.append(SimulatedPoint(name="soc", address=addr, data_type=f32, initial_value=50.0, writable=True))
    addr += f32.register_count

    points.append(SimulatedPoint(name="soh", address=addr, data_type=f32, initial_value=100.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="voltage", address=addr, data_type=f32, initial_value=700.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="current", address=addr, data_type=f32, initial_value=0.0))
    addr += f32.register_count

    points.append(SimulatedPoint(name="temperature", address=addr, data_type=f32, initial_value=25.0, writable=True))
    addr += f32.register_count

    points.append(SimulatedPoint(name="cell_voltage_min", address=addr, data_type=f32, initial_value=3.5))
    addr += f32.register_count

    points.append(SimulatedPoint(name="cell_voltage_max", address=addr, data_type=f32, initial_value=3.5))
    addr += f32.register_count

    points.append(SimulatedPoint(name="alarm_register", address=addr, data_type=u16, initial_value=0))
    addr += u16.register_count

    points.append(SimulatedPoint(name="status", address=addr, data_type=u16, initial_value=0))

    return SimulatedDeviceConfig(device_id=device_id, unit_id=unit_id, points=tuple(points))


class BMSSimulator(BaseDeviceSimulator):
    """
    BMS 模擬器

    模擬電池管理系統的物理行為：
    - SOC 追蹤：根據功率與電池容量動態計算
    - 電壓模型：基於 SOC 的線性電壓插值
    - 電芯電壓：Pack 電壓均攤 ± 擴散
    - 告警管理：過溫、過壓、欠壓、SOC 過高/過低
    - Debug 用 writable 點位：soc、temperature（透過 Modbus 寫入測試告警場景）

    Sign convention: +discharge / -charge（與 PCS 一致）
    """

    def __init__(
        self,
        config: SimulatedDeviceConfig | None = None,
        sim_config: BMSSimConfig | None = None,
        capacity_kwh: float = 100.0,
        initial_soc: float = 50.0,
        nominal_voltage: float = 700.0,
        cells_in_series: int = 192,
        min_cell_voltage: float = 2.8,
        max_cell_voltage: float = 4.2,
        charge_efficiency: float = 0.95,
        tick_interval: float = 1.0,
        **_kwargs: object,  # 忽略舊版 thermal_coefficient/ambient_temperature/cooling_rate
    ) -> None:
        if config is None:
            config = default_bms_config()
        super().__init__(config)

        if sim_config is None:
            sim_config = BMSSimConfig(
                capacity_kwh=capacity_kwh,
                initial_soc=initial_soc,
                nominal_voltage=nominal_voltage,
                cells_in_series=cells_in_series,
                min_cell_voltage=min_cell_voltage,
                max_cell_voltage=max_cell_voltage,
                charge_efficiency=charge_efficiency,
                tick_interval=tick_interval,
            )
        self._sim_config = sim_config
        self._capacity_kwh = sim_config.capacity_kwh
        self._cells_in_series = sim_config.cells_in_series
        self._min_cell_voltage = sim_config.min_cell_voltage
        self._max_cell_voltage = sim_config.max_cell_voltage
        self._charge_efficiency = sim_config.charge_efficiency
        self._tick_interval = sim_config.tick_interval

        # 初始化 SOC 與相關衍生值
        self._soc = sim_config.initial_soc
        self._temperature = 25.0
        self.set_value("soc", self._soc)
        self.set_value("temperature", self._temperature)
        self._update_voltage_from_soc()

    @property
    def capacity_kwh(self) -> float:
        """電池容量 (kWh)"""
        return self._capacity_kwh

    def _update_voltage_from_soc(self) -> None:
        """根據 SOC 更新 pack 電壓與電芯電壓。"""
        v_min = self._min_cell_voltage * self._cells_in_series
        v_max = self._max_cell_voltage * self._cells_in_series
        pack_voltage = v_min + (v_max - v_min) * self._soc / 100.0
        self.set_value("voltage", pack_voltage)

        cell_avg = pack_voltage / self._cells_in_series
        self.set_value("cell_voltage_min", cell_avg - 0.02)
        self.set_value("cell_voltage_max", cell_avg + 0.02)

    def _update_alarms(self) -> None:
        """更新告警 register（位元遮罩）。"""
        alarm = 0
        temp = float(self.get_value("temperature") or 0.0)
        cell_min = float(self.get_value("cell_voltage_min") or 0.0)
        cell_max = float(self.get_value("cell_voltage_max") or 0.0)
        soc = float(self.get_value("soc") or 0.0)

        if temp > 55.0:
            alarm |= 1 << 0  # bit0: 過溫
        if cell_min < 2.5:
            alarm |= 1 << 1  # bit1: 欠壓
        if cell_max > 4.25:
            alarm |= 1 << 2  # bit2: 過壓
        if soc < 5.0:
            alarm |= 1 << 3  # bit3: SOC 過低
        if soc > 95.0:
            alarm |= 1 << 4  # bit4: SOC 過高

        self.set_value("alarm_register", alarm)

    def on_write(self, name: str, old_value: object, new_value: object) -> None:
        """處理外部 Modbus 寫入（debug 用途）"""
        super().on_write(name, old_value, new_value)
        if name == "soc":
            self._soc = max(0.0, min(100.0, float(new_value)))  # type: ignore[arg-type]
            self._update_voltage_from_soc()
        elif name == "temperature":
            self._temperature = float(new_value)  # type: ignore[arg-type]

    def update_power(self, power_kw: float, dt: float) -> None:
        """
        根據外部功率更新 BMS 狀態

        核心物理模擬方法，由 MicrogridSimulator 在每個 tick 呼叫。

        Args:
            power_kw: 功率 (kW)，正值=放電，負值=充電
            dt: 時間步長 (秒)
        """
        # SOC 更新
        delta_soc = -power_kw * dt / (self._capacity_kwh * 3600.0) * 100.0
        if power_kw < 0:
            # 充電時考慮充電效率
            delta_soc *= self._charge_efficiency
        self._soc = max(0.0, min(100.0, self._soc + delta_soc))
        self.set_value("soc", self._soc)

        # 電壓（基於 SOC 線性插值）
        self._update_voltage_from_soc()

        # 電流 = P * 1000 / V（正值=放電，負值=充電）
        pack_voltage = float(self.get_value("voltage") or self._sim_config.nominal_voltage)
        if pack_voltage > 1e-6:
            current = power_kw * 1000.0 / pack_voltage
        else:
            current = 0.0
        self.set_value("current", current)

        # 溫度：讀取 register（可能被 Modbus 外部寫入）
        self._temperature = float(self.get_value("temperature") or self._temperature)

        # 狀態：0=standby, 1=charging, 2=discharging
        if abs(power_kw) < 0.1:
            status = 0
        elif power_kw < 0:
            status = 1
        else:
            status = 2
        self.set_value("status", status)

        # 告警檢查
        self._update_alarms()

    async def update(self) -> None:
        """
        自主更新（無外部功率輸入時）

        自然散熱 + 告警檢查。
        """
        # 溫度：讀取 register（可能被 Modbus 外部寫入）
        self._temperature = float(self.get_value("temperature") or self._temperature)

        # 告警檢查
        self._update_alarms()


__all__ = ["BMSSimulator", "default_bms_config"]
