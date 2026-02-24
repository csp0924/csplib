# =============== Statistics - Tracker ===============
#
# 設備能源追蹤器
#
# 提供單一設備的區間能耗計算：
#   - IntervalRecord: 完成的區間能耗記錄
#   - IntervalAccumulator: 單一區間的累積器（含時鐘對齊）
#   - DeviceEnergyTracker: 管理多個區間的追蹤器

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from csp_lib.statistics.config import DeviceMeterType


@dataclass(frozen=True)
class IntervalRecord:
    """
    完成的區間能耗記錄

    Attributes:
        device_id: 設備 ID
        interval_minutes: 區間長度（分鐘）
        period_start: 區間開始時間（時鐘對齊）
        period_end: 區間結束時間（時鐘對齊）
        kwh: 區間能耗（kWh）
        sample_count: 取樣點數量
        meter_type: 電表類型字串
    """

    device_id: str
    interval_minutes: int
    period_start: datetime
    period_end: datetime
    kwh: float
    sample_count: int
    meter_type: str


class IntervalAccumulator:
    """
    單一區間的累積器

    追蹤單一設備在單一區間（如 15 分鐘）的能耗累積。
    支援時鐘對齊邊界（15min → :00/:15/:30/:45）。

    累計型 (CUMULATIVE): 記錄首末讀數，kWh = last - first
    瞬時型 (INSTANTANEOUS): 梯形積分 kW × 時間

    Args:
        device_id: 設備 ID
        interval_minutes: 區間長度（分鐘）
        meter_type: 電表類型
    """

    def __init__(self, device_id: str, interval_minutes: int, meter_type: DeviceMeterType) -> None:
        self._device_id = device_id
        self._interval_minutes = interval_minutes
        self._meter_type = meter_type

        self._period_start: datetime | None = None
        self._sample_count: int = 0

        # CUMULATIVE
        self._first_value: float | None = None
        self._last_value: float | None = None

        # INSTANTANEOUS
        self._kwh_accumulated: float = 0.0
        self._prev_value: float | None = None
        self._prev_timestamp: datetime | None = None

    @property
    def period_start(self) -> datetime | None:
        """目前區間的起始時間"""
        return self._period_start

    @property
    def sample_count(self) -> int:
        """目前區間的取樣數"""
        return self._sample_count

    def feed(self, value: float, timestamp: datetime) -> IntervalRecord | None:
        """
        輸入一筆讀數

        若跨越區間邊界，會完成當前區間並返回記錄，然後開始新區間。

        Args:
            value: 讀數值（kWh 或 kW）
            timestamp: 讀取時間

        Returns:
            跨越邊界時返回 IntervalRecord，否則返回 None
        """
        if self._period_start is None:
            self._period_start = self._floor_timestamp(timestamp)
            self._start_sample(value, timestamp)
            return None

        boundary = self._next_boundary()
        if timestamp >= boundary:
            record = self._finalize(boundary)
            self._period_start = self._floor_timestamp(timestamp)
            self._reset()
            self._start_sample(value, timestamp)
            return record

        self._accumulate(value, timestamp)
        return None

    def _floor_timestamp(self, ts: datetime) -> datetime:
        """將時間戳對齊到區間邊界（向下取整）"""
        floored_minute = (ts.minute // self._interval_minutes) * self._interval_minutes
        return ts.replace(minute=floored_minute, second=0, microsecond=0)

    def _next_boundary(self) -> datetime:
        """目前區間的結束邊界"""
        assert self._period_start is not None
        return self._period_start + timedelta(minutes=self._interval_minutes)

    def _start_sample(self, value: float, timestamp: datetime) -> None:
        """開始新的取樣"""
        self._sample_count = 1
        if self._meter_type == DeviceMeterType.CUMULATIVE:
            self._first_value = value
            self._last_value = value
        else:
            self._kwh_accumulated = 0.0
            self._prev_value = value
            self._prev_timestamp = timestamp

    def _accumulate(self, value: float, timestamp: datetime) -> None:
        """累積一筆讀數"""
        self._sample_count += 1
        if self._meter_type == DeviceMeterType.CUMULATIVE:
            self._last_value = value
        else:
            if self._prev_timestamp is not None and self._prev_value is not None:
                dt_hours = (timestamp - self._prev_timestamp).total_seconds() / 3600.0
                self._kwh_accumulated += (self._prev_value + value) / 2.0 * dt_hours
            self._prev_value = value
            self._prev_timestamp = timestamp

    def _finalize(self, boundary: datetime) -> IntervalRecord:
        """完成當前區間，返回記錄"""
        if self._meter_type == DeviceMeterType.CUMULATIVE:
            kwh = (self._last_value or 0.0) - (self._first_value or 0.0)
        else:
            kwh = self._kwh_accumulated

        return IntervalRecord(
            device_id=self._device_id,
            interval_minutes=self._interval_minutes,
            period_start=self._period_start,  # type: ignore[arg-type]
            period_end=boundary,
            kwh=kwh,
            sample_count=self._sample_count,
            meter_type=self._meter_type.value,
        )

    def _reset(self) -> None:
        """重置累積器狀態"""
        self._first_value = None
        self._last_value = None
        self._kwh_accumulated = 0.0
        self._prev_value = None
        self._prev_timestamp = None
        self._sample_count = 0


class DeviceEnergyTracker:
    """
    設備能源追蹤器

    管理單一設備在多個區間（如 15/30/60 分鐘）的能耗追蹤。

    Args:
        device_id: 設備 ID
        intervals: 區間長度列表（分鐘）
        meter_type: 電表類型
    """

    def __init__(
        self,
        device_id: str,
        intervals: tuple[int, ...],
        meter_type: DeviceMeterType,
    ) -> None:
        self._device_id = device_id
        self._accumulators = [IntervalAccumulator(device_id, interval, meter_type) for interval in intervals]

    def feed(self, value: float, timestamp: datetime) -> list[IntervalRecord]:
        """
        輸入一筆讀數至所有區間累積器

        Args:
            value: 讀數值（kWh 或 kW）
            timestamp: 讀取時間

        Returns:
            已完成區間的 IntervalRecord 列表
        """
        records: list[IntervalRecord] = []
        for acc in self._accumulators:
            record = acc.feed(value, timestamp)
            if record is not None:
                records.append(record)
        return records


__all__ = [
    "IntervalRecord",
    "IntervalAccumulator",
    "DeviceEnergyTracker",
]
