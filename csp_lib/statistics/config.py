# =============== Statistics - Config ===============
#
# 統計模組配置
#
# 提供能源統計的配置定義：
#   - DeviceMeterType: 設備電表類型（累計/瞬時）
#   - MetricDefinition: 單一設備的能源計量定義
#   - PowerSumDefinition: 跨設備功率加總定義
#   - StatisticsConfig: 統計模組整體配置

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DeviceMeterType(Enum):
    """
    設備電表類型

    CUMULATIVE: 累計型電表，回報累計 kWh，使用差值計算區間能耗
    INSTANTANEOUS: 瞬時型電表，回報瞬時 kW，使用梯形積分計算區間能耗
    """

    CUMULATIVE = "cumulative"
    INSTANTANEOUS = "instantaneous"


@dataclass(frozen=True)
class MetricDefinition:
    """
    單一設備的能源計量定義

    Attributes:
        device_id: 設備 ID
        meter_type: 電表類型
        point_name: 讀取點名稱（如 "kwh_total" 或 "active_power"）
    """

    device_id: str
    meter_type: DeviceMeterType
    point_name: str


@dataclass(frozen=True)
class PowerSumDefinition:
    """
    跨設備功率加總定義

    透過 DeviceRegistry trait 解析所屬設備，加總指定 point 的值。

    Attributes:
        name: 加總名稱（如 "p_total_pcs"）
        trait: DeviceRegistry trait 標籤
        point_name: 要加總的讀取點名稱（如 "active_power"）
    """

    name: str
    trait: str
    point_name: str


@dataclass(frozen=True)
class StatisticsConfig:
    """
    統計模組整體配置

    Attributes:
        metrics: 設備能源計量定義列表
        power_sums: 功率加總定義列表
        intervals_minutes: 統計區間（分鐘），預設 15/30/60
        collection_name: MongoDB collection 名稱
    """

    metrics: list[MetricDefinition] = field(default_factory=list)
    power_sums: list[PowerSumDefinition] = field(default_factory=list)
    intervals_minutes: tuple[int, ...] = (15, 30, 60)
    collection_name: str = "statistics"


__all__ = [
    "DeviceMeterType",
    "MetricDefinition",
    "PowerSumDefinition",
    "StatisticsConfig",
]
