# =============== Modbus Server - Configuration ===============
#
# 模擬伺服器所有配置 dataclasses

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from csp_lib.core.errors import ConfigurationError
from csp_lib.modbus import ByteOrder, ModbusDataType, RegisterOrder


class AlarmResetMode(Enum):
    """告警重置模式"""

    AUTO = "auto"  # 條件消失自動清除
    MANUAL = "manual"  # 需要寫入 reset 命令
    LATCHED = "latched"  # 需要完整 reset（force_reset）


class ControllabilityMode(Enum):
    """可控性模式"""

    CONTROLLABLE = "controllable"  # 回應 setpoint 寫入
    UNCONTROLLABLE = "uncontrollable"  # 忽略寫入，自行變化


@dataclass(frozen=True, slots=True)
class SimulatedPoint:
    """
    模擬點位定義

    Attributes:
        name: 點位名稱
        address: Register 起始位址
        data_type: Modbus 資料型別 (Float32, UInt16 等)
        initial_value: 初始值
        writable: 是否可寫入
        byte_order: 位元組順序
        register_order: 暫存器順序
    """

    name: str
    address: int
    data_type: ModbusDataType
    initial_value: Any = 0
    writable: bool = False
    byte_order: ByteOrder = ByteOrder.BIG_ENDIAN
    register_order: RegisterOrder = RegisterOrder.HIGH_FIRST


@dataclass(frozen=True, slots=True)
class AlarmPointConfig:
    """
    告警點位配置

    Attributes:
        alarm_code: 告警代碼（對應 AlarmDefinition.code）
        bit_position: alarm register 中的 bit 位置
        reset_mode: 重置模式
        reset_address: manual reset 時的目標 register 位址
        reset_value: 寫入什麼值觸發 reset
    """

    alarm_code: str
    bit_position: int
    reset_mode: AlarmResetMode = AlarmResetMode.AUTO
    reset_address: int | None = None
    reset_value: int | None = None


@dataclass(frozen=True, slots=True)
class SimulatedDeviceConfig:
    """
    模擬設備配置

    Attributes:
        device_id: 設備識別碼
        unit_id: Modbus slave ID (1-247)
        points: 點位定義
        alarm_points: 告警點位配置
        update_interval: 更新間隔（秒）
    """

    device_id: str
    unit_id: int
    points: tuple[SimulatedPoint, ...] = ()
    alarm_points: tuple[AlarmPointConfig, ...] = ()
    update_interval: float = 1.0


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """
    模擬伺服器配置

    Attributes:
        host: 監聽位址
        port: 監聽埠號
        tick_interval: tick loop 間隔（秒）
    """

    host: str = "127.0.0.1"
    port: int = 5020
    tick_interval: float = 1.0


@dataclass(frozen=True, slots=True)
class MicrogridConfig:
    """
    微電網聯動配置

    Attributes:
        grid_voltage: 電網標稱電壓 (V)
        grid_frequency: 電網標稱頻率 (Hz)
        voltage_noise: 電壓擾動範圍 (+/- V)
        frequency_noise: 頻率擾動範圍 (+/- Hz)
    """

    grid_voltage: float = 380.0
    grid_frequency: float = 60.0
    voltage_noise: float = 2.0
    frequency_noise: float = 0.02


@dataclass(frozen=True, slots=True)
class PowerMeterSimConfig:
    """
    電表模擬器配置

    Attributes:
        power_sign: 功率正負號配置（+1.0 或 -1.0）
        voltage_noise: 電壓擾動振幅 (V)
        frequency_noise: 頻率擾動振幅 (Hz)
    """

    power_sign: float = 1.0
    voltage_noise: float = 2.0
    frequency_noise: float = 0.02

    def __post_init__(self) -> None:
        if self.voltage_noise < 0:
            raise ConfigurationError(f"voltage_noise 必須 >= 0，收到: {self.voltage_noise}")
        if self.frequency_noise < 0:
            raise ConfigurationError(f"frequency_noise 必須 >= 0，收到: {self.frequency_noise}")


@dataclass(frozen=True, slots=True)
class PCSSimConfig:
    """
    PCS 模擬器配置

    Attributes:
        capacity_kwh: 電池容量 (kWh)
        p_ramp_rate: 有功功率斜率 (kW/s)
        q_ramp_rate: 無功功率斜率 (kVar/s)
        tick_interval: 模擬更新間隔（秒）
    """

    capacity_kwh: float = 100.0
    p_ramp_rate: float = 100.0
    q_ramp_rate: float = 100.0
    tick_interval: float = 1.0

    def __post_init__(self) -> None:
        if self.capacity_kwh <= 0:
            raise ConfigurationError(f"capacity_kwh 必須大於 0，收到: {self.capacity_kwh}")
        if self.p_ramp_rate <= 0:
            raise ConfigurationError(f"p_ramp_rate 必須大於 0，收到: {self.p_ramp_rate}")
        if self.q_ramp_rate <= 0:
            raise ConfigurationError(f"q_ramp_rate 必須大於 0，收到: {self.q_ramp_rate}")
        if self.tick_interval <= 0:
            raise ConfigurationError(f"tick_interval 必須大於 0，收到: {self.tick_interval}")


@dataclass(frozen=True, slots=True)
class SolarSimConfig:
    """
    太陽能模擬器配置

    Attributes:
        efficiency: DC → AC 轉換效率 (0~1)
        power_noise: 功率擾動振幅 (kW)
        tick_interval: 模擬更新間隔（秒）
    """

    efficiency: float = 0.95
    power_noise: float = 0.5
    tick_interval: float = 1.0

    def __post_init__(self) -> None:
        if not (0 < self.efficiency <= 1.0):
            raise ConfigurationError(f"efficiency 必須在 (0, 1] 範圍內，收到: {self.efficiency}")
        if self.power_noise < 0:
            raise ConfigurationError(f"power_noise 必須 >= 0，收到: {self.power_noise}")
        if self.tick_interval <= 0:
            raise ConfigurationError(f"tick_interval 必須大於 0，收到: {self.tick_interval}")


@dataclass(frozen=True, slots=True)
class GeneratorSimConfig:
    """
    發電機模擬器配置

    Attributes:
        startup_delay: 啟動延遲（秒）
        ramp_rate: 功率斜率 (kW/s)
        shutdown_delay: 停機延遲（秒）
        rated_rpm: 額定轉速 (RPM)
        power_factor: 功率因數
        tick_interval: 模擬更新間隔（秒）
    """

    startup_delay: float = 5.0
    ramp_rate: float = 50.0
    shutdown_delay: float = 3.0
    rated_rpm: float = 1800.0
    power_factor: float = 0.8
    tick_interval: float = 1.0

    def __post_init__(self) -> None:
        if self.startup_delay <= 0:
            raise ConfigurationError(f"startup_delay 必須大於 0，收到: {self.startup_delay}")
        if self.ramp_rate <= 0:
            raise ConfigurationError(f"ramp_rate 必須大於 0，收到: {self.ramp_rate}")
        if self.shutdown_delay <= 0:
            raise ConfigurationError(f"shutdown_delay 必須大於 0，收到: {self.shutdown_delay}")
        if self.rated_rpm <= 0:
            raise ConfigurationError(f"rated_rpm 必須大於 0，收到: {self.rated_rpm}")
        if not (0 < self.power_factor <= 1.0):
            raise ConfigurationError(f"power_factor 必須在 (0, 1] 範圍內，收到: {self.power_factor}")
        if self.tick_interval <= 0:
            raise ConfigurationError(f"tick_interval 必須大於 0，收到: {self.tick_interval}")


@dataclass(frozen=True, slots=True)
class DeviceLinkConfig:
    """
    設備到電表的連結配置。

    loss_factor=0.02 表示 2% 功率損耗。

    Attributes:
        source_device_id: 來源設備 ID
        target_meter_id: 目標電表 ID
        loss_factor: 功率損耗因子 [0.0, 1.0)
    """

    source_device_id: str
    target_meter_id: str
    loss_factor: float = 0.0

    def __post_init__(self) -> None:
        if not self.source_device_id:
            raise ConfigurationError("source_device_id 不可為空")
        if not self.target_meter_id:
            raise ConfigurationError("target_meter_id 不可為空")
        if not (0.0 <= self.loss_factor < 1.0):
            raise ConfigurationError(f"loss_factor 須在 [0.0, 1.0) 範圍: {self.loss_factor}")


@dataclass(frozen=True, slots=True)
class MeterAggregationConfig:
    """
    電表聚合配置 — 多個子電表功率累加到父電表。

    Attributes:
        source_meter_ids: 來源電表 ID 集合
        target_meter_id: 目標（父）電表 ID
    """

    source_meter_ids: tuple[str, ...]
    target_meter_id: str

    def __post_init__(self) -> None:
        if not self.source_meter_ids:
            raise ConfigurationError("source_meter_ids 不可為空")
        if self.target_meter_id in self.source_meter_ids:
            raise ConfigurationError(f"target_meter_id '{self.target_meter_id}' 不可在 source_meter_ids 中")


@dataclass(frozen=True, slots=True)
class BMSSimConfig:
    """BMS 模擬器配置

    Attributes:
        capacity_kwh: 電池容量 (kWh)
        initial_soc: 初始 SOC (%)
        nominal_voltage: 額定電壓 (V)
        cells_in_series: 串聯電芯數
        min_cell_voltage: 電芯最低電壓 (V)
        max_cell_voltage: 電芯最高電壓 (V)
        charge_efficiency: 充電效率 (0~1)
        tick_interval: 模擬步長 (s)
    """

    capacity_kwh: float = 100.0
    initial_soc: float = 50.0
    nominal_voltage: float = 700.0
    cells_in_series: int = 192
    min_cell_voltage: float = 2.8
    max_cell_voltage: float = 4.2
    charge_efficiency: float = 0.95
    tick_interval: float = 1.0

    def __post_init__(self) -> None:
        if self.capacity_kwh <= 0:
            raise ConfigurationError(f"capacity_kwh 必須大於 0，收到: {self.capacity_kwh}")
        if not (0.0 <= self.initial_soc <= 100.0):
            raise ConfigurationError(f"initial_soc 必須在 [0, 100] 範圍，收到: {self.initial_soc}")
        if self.nominal_voltage <= 0:
            raise ConfigurationError(f"nominal_voltage 必須大於 0，收到: {self.nominal_voltage}")
        if self.cells_in_series <= 0:
            raise ConfigurationError(f"cells_in_series 必須大於 0，收到: {self.cells_in_series}")
        if self.min_cell_voltage >= self.max_cell_voltage:
            raise ConfigurationError(
                f"min_cell_voltage ({self.min_cell_voltage}) 必須小於 max_cell_voltage ({self.max_cell_voltage})"
            )
        if not (0.0 < self.charge_efficiency <= 1.0):
            raise ConfigurationError(f"charge_efficiency 必須在 (0, 1] 範圍，收到: {self.charge_efficiency}")
        if self.tick_interval <= 0:
            raise ConfigurationError(f"tick_interval 必須大於 0，收到: {self.tick_interval}")


@dataclass(frozen=True, slots=True)
class LoadSimConfig:
    """
    負載模擬器配置

    Attributes:
        controllability: 可控性模式
        power_factor: 功率因數
        ramp_rate: 功率斜率 (kW/s)
        base_load: 基礎負載 (kW)
        load_noise: 負載擾動振幅 (kW)
        tick_interval: 模擬更新間隔（秒）
    """

    controllability: ControllabilityMode = ControllabilityMode.CONTROLLABLE
    power_factor: float = 0.9
    ramp_rate: float = 50.0
    base_load: float = 0.0
    load_noise: float = 2.0
    tick_interval: float = 1.0

    def __post_init__(self) -> None:
        if not (0 < self.power_factor <= 1.0):
            raise ConfigurationError(f"power_factor 必須在 (0, 1] 範圍內，收到: {self.power_factor}")
        if self.ramp_rate <= 0:
            raise ConfigurationError(f"ramp_rate 必須大於 0，收到: {self.ramp_rate}")
        if self.load_noise < 0:
            raise ConfigurationError(f"load_noise 必須 >= 0，收到: {self.load_noise}")
        if self.tick_interval <= 0:
            raise ConfigurationError(f"tick_interval 必須大於 0，收到: {self.tick_interval}")


__all__ = [
    "AlarmPointConfig",
    "AlarmResetMode",
    "BMSSimConfig",
    "ControllabilityMode",
    "DeviceLinkConfig",
    "GeneratorSimConfig",
    "LoadSimConfig",
    "MeterAggregationConfig",
    "MicrogridConfig",
    "PCSSimConfig",
    "PowerMeterSimConfig",
    "ServerConfig",
    "SimulatedDeviceConfig",
    "SimulatedPoint",
    "SolarSimConfig",
]
