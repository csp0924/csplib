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


@dataclass(frozen=True, slots=True)
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

    Boundary handling（修復 boundary truncation bug）：
      當 feed() 偵測到 timestamp 跨越 boundary 時，使用 prev sample 與剛抵達的 sample
      做 *線性內插* 估出 boundary 瞬間的 value：
          v_b = prev_value + (value - prev_value) * (boundary - prev_ts) / (ts - prev_ts)
      - INSTANTANEOUS: 補上 trapezoid 尾段 (prev_value + v_b)/2 * (boundary - prev_ts).hours
      - CUMULATIVE: kwh = v_b - first_value
      然後以 *floor(timestamp) 對應時刻的內插值* 為合成種子開啟下一個 interval（不是
      用「舊 boundary」的內插值，避免 timestamp 跨越 >1 個 interval 時把整段 gap
      能量灌進新 interval）。再 accumulate 真實抵達的 sample。這確保 boundary 兩側
      無 leakage；constant 信號完全精確；ramp 信號也只受兩 sample 間二階近似誤差影響。

      Multi-interval skip：當 timestamp 跨越 >1 個 boundary（取樣斷線後恢復），只
      finalize 第一個跨越的 interval；中間被跳過的 interval 不 emit record（缺乏
      足夠資訊重建 partial interval），新 interval 從 floor(timestamp) 起算。

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
        """目前區間的取樣數（不含 boundary 合成種子）"""
        return self._sample_count

    def feed(self, value: float, timestamp: datetime) -> IntervalRecord | None:
        """
        輸入一筆讀數

        若跨越區間邊界，會完成當前區間並返回記錄，然後以 boundary 內插值為種子
        開啟下一個區間（boundary truncation 修復）。

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
            # 線性內插：用 prev sample 與剛抵達的 sample 估算 boundary 瞬間值
            value_at_boundary = self._interpolate_at_boundary(value, timestamp, boundary)
            record = self._finalize(boundary, value_at_boundary)
            # Seed 新 interval：用 floor(timestamp) 對應時刻的內插值，而非舊 boundary
            # 的內插值。多 interval 跨越時這能避免把整段 gap 能量灌進新 interval。
            new_period_start = self._floor_timestamp(timestamp)
            value_at_period_start = self._interpolate_at_boundary(value, timestamp, new_period_start)
            self._period_start = new_period_start
            self._reset()
            self._seed_from_boundary(value_at_period_start, new_period_start)
            self._accumulate(value, timestamp)
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

    def _interpolate_at_boundary(
        self,
        value: float,
        timestamp: datetime,
        boundary: datetime,
    ) -> float:
        """
        對 boundary 瞬間做線性內插。

        防呆：prev_ts 應 < boundary <= timestamp。若 prev 不存在（理論上不會發生，
        因為 _period_start 已存在意味著至少有過一筆 sample），fallback 直接取 value。
        若 timestamp == prev_ts（同瞬間兩筆），回傳 value 避免除以零。
        """
        if self._prev_timestamp is None or self._prev_value is None:
            return value
        span_seconds = (timestamp - self._prev_timestamp).total_seconds()
        if span_seconds <= 0.0:
            return value
        offset_seconds = (boundary - self._prev_timestamp).total_seconds()
        ratio = offset_seconds / span_seconds
        # 夾在 [0, 1] 避免 boundary 落在 prev 之前的退化情境（理論上不會發生）
        ratio = max(0.0, min(1.0, ratio))
        return self._prev_value + (value - self._prev_value) * ratio

    def _start_sample(self, value: float, timestamp: datetime) -> None:
        """開始新的取樣（首筆真實 sample）。

        兩種模式都記錄 prev_value / prev_timestamp 以支援 boundary 內插。
        """
        self._sample_count = 1
        self._prev_value = value
        self._prev_timestamp = timestamp
        if self._meter_type == DeviceMeterType.CUMULATIVE:
            self._first_value = value
            self._last_value = value
        else:
            self._kwh_accumulated = 0.0

    def _seed_from_boundary(self, value_at_boundary: float, boundary: datetime) -> None:
        """
        以 boundary 內插值為新 interval 的起點種子。

        此 sample 是合成的（非真實量測），不計入 sample_count，但設好內部狀態
        讓後續 _accumulate 可以從 boundary 起算 trapezoid / 差值。
        """
        self._prev_value = value_at_boundary
        self._prev_timestamp = boundary
        if self._meter_type == DeviceMeterType.CUMULATIVE:
            self._first_value = value_at_boundary
            self._last_value = value_at_boundary
        else:
            self._kwh_accumulated = 0.0

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

    def _finalize(self, boundary: datetime, value_at_boundary: float) -> IntervalRecord:
        """
        完成當前區間，返回記錄。

        Args:
            boundary: 區間結束邊界
            value_at_boundary: boundary 瞬間的內插值，用於補齊尾段能耗

        Returns:
            IntervalRecord 含已含尾段補償的 kwh
        """
        if self._meter_type == DeviceMeterType.CUMULATIVE:
            # 用 boundary 內插值取代「最後一筆 sample」，跨 interval 連續、無 leakage
            kwh = value_at_boundary - (self._first_value or 0.0)
        else:
            # INSTANTANEOUS：補上 prev_ts → boundary 的 trapezoid 尾段
            tail_kwh = 0.0
            if self._prev_timestamp is not None and self._prev_value is not None:
                dt_hours = (boundary - self._prev_timestamp).total_seconds() / 3600.0
                if dt_hours > 0.0:
                    tail_kwh = (self._prev_value + value_at_boundary) / 2.0 * dt_hours
            kwh = self._kwh_accumulated + tail_kwh

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
