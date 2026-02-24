# =============== Statistics - Engine ===============
#
# 統計計算引擎
#
# 提供多設備能源追蹤與功率加總：
#   - PowerSumRecord: 功率加總記錄
#   - StatisticsEngine: 統計計算核心

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from csp_lib.core import get_logger
from csp_lib.statistics.config import StatisticsConfig
from csp_lib.statistics.tracker import DeviceEnergyTracker, IntervalRecord

logger = get_logger(__name__)


@dataclass(frozen=True)
class PowerSumRecord:
    """
    功率加總記錄

    Attributes:
        name: 加總名稱（如 "p_total_pcs"）
        interval_minutes: 區間長度（分鐘）
        period_start: 區間開始時間
        period_end: 區間結束時間
        total_power: 加總功率（kW）
        device_count: 參與設備數
    """

    name: str
    interval_minutes: int
    period_start: datetime
    period_end: datetime
    total_power: float
    device_count: int


class StatisticsEngine:
    """
    統計計算引擎

    管理多設備的能源追蹤與跨設備功率加總。

    職責：
        1. 維護 per-device DeviceEnergyTracker
        2. 追蹤 real-time 功率加總
        3. 在區間邊界產生 IntervalRecord 與 PowerSumRecord

    Args:
        config: 統計配置
    """

    def __init__(self, config: StatisticsConfig) -> None:
        self._config = config
        self._intervals = config.intervals_minutes

        # Per-device energy trackers (from MetricDefinition)
        self._trackers: dict[str, DeviceEnergyTracker] = {}
        self._metric_point_map: dict[str, str] = {}  # device_id -> point_name
        for metric in config.metrics:
            self._trackers[metric.device_id] = DeviceEnergyTracker(
                device_id=metric.device_id,
                intervals=self._intervals,
                meter_type=metric.meter_type,
            )
            self._metric_point_map[metric.device_id] = metric.point_name

        # Power sums
        # power_sum_name -> {device_id: latest_power_value}
        self._power_device_values: dict[str, dict[str, float]] = {}
        # device_id -> list of (power_sum_name, point_name)
        self._device_power_sums: dict[str, list[tuple[str, str]]] = {}

        for ps in config.power_sums:
            self._power_device_values[ps.name] = {}

    def register_power_sum_devices(self, name: str, device_ids: list[str]) -> None:
        """
        註冊功率加總的參與設備

        由 StatisticsManager 呼叫，將 trait 解析後的 device_ids 注入引擎。

        Args:
            name: 功率加總名稱
            device_ids: 參與設備 ID 列表
        """
        ps_def = next((ps for ps in self._config.power_sums if ps.name == name), None)
        if ps_def is None:
            logger.warning(f"StatisticsEngine: 未知的功率加總定義: {name}")
            return

        point_name = ps_def.point_name
        for did in device_ids:
            if did not in self._device_power_sums:
                self._device_power_sums[did] = []
            self._device_power_sums[did].append((name, point_name))
            self._power_device_values[name][did] = 0.0

    def process_read(self, device_id: str, values: dict[str, Any], timestamp: datetime) -> list[IntervalRecord]:
        """
        處理一次設備讀取

        更新能源追蹤器與功率加總值。

        Args:
            device_id: 設備 ID
            values: 讀取值字典
            timestamp: 讀取時間

        Returns:
            已完成區間的 IntervalRecord 列表
        """
        records: list[IntervalRecord] = []

        # Energy tracking
        point_name = self._metric_point_map.get(device_id)
        if point_name and point_name in values:
            value = values[point_name]
            if isinstance(value, (int, float)):
                tracker = self._trackers[device_id]
                records.extend(tracker.feed(value, timestamp))

        # Power sum tracking
        for sum_name, ps_point in self._device_power_sums.get(device_id, []):
            if ps_point in values:
                value = values[ps_point]
                if isinstance(value, (int, float)):
                    self._power_device_values[sum_name][device_id] = float(value)

        return records

    def get_power_sum(self, name: str) -> float:
        """
        取得指定功率加總的目前值

        Args:
            name: 功率加總名稱

        Returns:
            目前的加總功率（kW）
        """
        return sum(self._power_device_values.get(name, {}).values())

    def get_all_power_sums(self) -> dict[str, float]:
        """
        取得所有功率加總的目前值

        Returns:
            功率加總名稱 → 目前值的字典
        """
        return {name: self.get_power_sum(name) for name in self._power_device_values}

    def build_power_sum_records(
        self, interval_minutes: int, period_start: datetime, period_end: datetime
    ) -> list[PowerSumRecord]:
        """
        建立功率加總記錄

        在區間邊界呼叫，快照目前的功率加總值。

        Args:
            interval_minutes: 區間長度（分鐘）
            period_start: 區間開始時間
            period_end: 區間結束時間

        Returns:
            各功率加總的 PowerSumRecord 列表
        """
        records: list[PowerSumRecord] = []
        for name, device_values in self._power_device_values.items():
            records.append(
                PowerSumRecord(
                    name=name,
                    interval_minutes=interval_minutes,
                    period_start=period_start,
                    period_end=period_end,
                    total_power=sum(device_values.values()),
                    device_count=len(device_values),
                )
            )
        return records


__all__ = [
    "PowerSumRecord",
    "StatisticsEngine",
]
