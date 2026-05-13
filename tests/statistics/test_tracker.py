# =============== Statistics Tests - Tracker ===============
#
# IntervalAccumulator / DeviceEnergyTracker 單元測試
#
# 測試覆蓋：
# - 時鐘對齊邊界（15/30/60 分鐘）
# - 累計型電表：差值計算
# - 瞬時型電表：梯形積分
# - DeviceEnergyTracker 多區間追蹤

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from csp_lib.statistics.config import DeviceMeterType
from csp_lib.statistics.tracker import (
    DeviceEnergyTracker,
    IntervalAccumulator,
    IntervalRecord,
)

# ======================== IntervalAccumulator — Clock Alignment ========================


class TestClockAlignment:
    """時鐘對齊邊界測試"""

    def test_15min_floor(self):
        """15 分鐘區間應對齊到 :00/:15/:30/:45"""
        acc = IntervalAccumulator("dev1", 15, DeviceMeterType.CUMULATIVE)
        ts = datetime(2025, 1, 1, 10, 7, 30, tzinfo=timezone.utc)
        floored = acc._floor_timestamp(ts)
        assert floored == datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    def test_15min_floor_on_boundary(self):
        """恰好在邊界上應保持不變"""
        acc = IntervalAccumulator("dev1", 15, DeviceMeterType.CUMULATIVE)
        ts = datetime(2025, 1, 1, 10, 15, 0, tzinfo=timezone.utc)
        floored = acc._floor_timestamp(ts)
        assert floored == datetime(2025, 1, 1, 10, 15, 0, tzinfo=timezone.utc)

    def test_30min_floor(self):
        """30 分鐘區間應對齊到 :00/:30"""
        acc = IntervalAccumulator("dev1", 30, DeviceMeterType.CUMULATIVE)
        ts = datetime(2025, 1, 1, 10, 22, 0, tzinfo=timezone.utc)
        floored = acc._floor_timestamp(ts)
        assert floored == datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    def test_60min_floor(self):
        """60 分鐘區間應對齊到 :00"""
        acc = IntervalAccumulator("dev1", 60, DeviceMeterType.CUMULATIVE)
        ts = datetime(2025, 1, 1, 10, 45, 0, tzinfo=timezone.utc)
        floored = acc._floor_timestamp(ts)
        assert floored == datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


# ======================== IntervalAccumulator — Cumulative ========================


class TestCumulativeAccumulator:
    """累計型電表累積器測試"""

    @pytest.fixture
    def acc(self) -> IntervalAccumulator:
        return IntervalAccumulator("dev1", 15, DeviceMeterType.CUMULATIVE)

    def test_first_feed_returns_none(self, acc: IntervalAccumulator):
        """第一筆讀數不產生記錄"""
        ts = datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc)
        result = acc.feed(100.0, ts)
        assert result is None
        assert acc.period_start == datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    def test_within_interval_returns_none(self, acc: IntervalAccumulator):
        """同區間內的讀數不產生記錄"""
        base = datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc)
        acc.feed(100.0, base)
        result = acc.feed(105.0, datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc))
        assert result is None
        assert acc.sample_count == 2

    def test_boundary_crossing_returns_record(self, acc: IntervalAccumulator):
        """跨越邊界應返回完成的區間記錄（kwh 以 boundary 內插值結算）"""
        acc.feed(100.0, datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc))
        acc.feed(110.0, datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc))
        record = acc.feed(120.0, datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc))

        assert record is not None
        assert record.device_id == "dev1"
        assert record.interval_minutes == 15
        assert record.period_start == datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert record.period_end == datetime(2025, 1, 1, 10, 15, 0, tzinfo=timezone.utc)
        # 內插 boundary 10:15：v_b = 110 + (120-110)*(15-10)/(16-10) = 118.333
        # kwh = v_b - first(100) = 18.333
        assert record.kwh == pytest.approx(110.0 + 10.0 * 5.0 / 6.0 - 100.0)
        assert record.sample_count == 2
        assert record.meter_type == "cumulative"

    def test_multiple_intervals(self, acc: IntervalAccumulator):
        """連續跨越多個區間（boundary 內插值結算 + 跨 interval 連續）"""
        acc.feed(100.0, datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc))
        r1 = acc.feed(110.0, datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc))
        assert r1 is not None
        # 內插 boundary 10:15：v_b = 100 + (110-100)*(13/14) = 109.2857
        v_b1 = 100.0 + 10.0 * 13.0 / 14.0
        assert r1.kwh == pytest.approx(v_b1 - 100.0)

        # 新 interval seed 從 v_b1@10:15 起，再餵 110@10:16 / 130@10:25 / 140@10:31
        acc.feed(130.0, datetime(2025, 1, 1, 10, 25, 0, tzinfo=timezone.utc))
        r2 = acc.feed(140.0, datetime(2025, 1, 1, 10, 31, 0, tzinfo=timezone.utc))
        assert r2 is not None
        # 內插 boundary 10:30：prev=130@10:25, curr=140@10:31 → v_b2 = 130 + 10*5/6 = 138.333
        v_b2 = 130.0 + 10.0 * 5.0 / 6.0
        assert r2.kwh == pytest.approx(v_b2 - v_b1)

    def test_zero_energy_when_single_sample(self):
        """單一真實 sample 跨 boundary：內插仍能算出有意義能耗"""
        acc = IntervalAccumulator("dev1", 15, DeviceMeterType.CUMULATIVE)
        acc.feed(500.0, datetime(2025, 1, 1, 10, 14, 0, tzinfo=timezone.utc))
        record = acc.feed(510.0, datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc))

        assert record is not None
        # 內插 boundary 10:15：v_b = 500 + (510-500)*(1/2) = 505 → kwh = 505 - 500 = 5
        assert record.kwh == pytest.approx(5.0)
        assert record.sample_count == 1


# ======================== IntervalAccumulator — Instantaneous ========================


class TestInstantaneousAccumulator:
    """瞬時型電表累積器測試"""

    @pytest.fixture
    def acc(self) -> IntervalAccumulator:
        return IntervalAccumulator("dev1", 15, DeviceMeterType.INSTANTANEOUS)

    def test_first_feed_returns_none(self, acc: IntervalAccumulator):
        """第一筆讀數不產生記錄"""
        ts = datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc)
        result = acc.feed(50.0, ts)
        assert result is None

    def test_trapezoidal_integration(self, acc: IntervalAccumulator):
        """梯形積分計算正確（含 boundary 尾段補償）"""
        # 50 kW 恆定，10:02 ~ 10:12 ~ boundary 10:15：應覆蓋 10:02 → 10:15 = 13 分鐘
        acc.feed(50.0, datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc))
        acc.feed(50.0, datetime(2025, 1, 1, 10, 12, 0, tzinfo=timezone.utc))
        record = acc.feed(50.0, datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc))

        assert record is not None
        # 已 accumulate (10:02→10:12) = 50*10/60；尾段 (10:12→10:15) 內插 v_b=50：50*3/60
        expected = 50.0 * 10.0 / 60.0 + 50.0 * 3.0 / 60.0
        assert record.kwh == pytest.approx(expected, rel=1e-6)
        assert record.meter_type == "instantaneous"

    def test_varying_power(self, acc: IntervalAccumulator):
        """功率變化時的梯形積分（含 boundary 內插尾段）"""
        # 0 → 100 over 10:02 → 10:12，再 100 在 10:16 跨 boundary 10:15
        acc.feed(0.0, datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc))
        acc.feed(100.0, datetime(2025, 1, 1, 10, 12, 0, tzinfo=timezone.utc))
        record = acc.feed(100.0, datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc))

        assert record is not None
        # 主段 (10:02→10:12): (0+100)/2 * 10/60 = 8.333
        # 尾段內插：prev=100@10:12, curr=100@10:16 → v_b@10:15 = 100，(100+100)/2 * 3/60 = 5.0
        expected = (0.0 + 100.0) / 2.0 * (10.0 / 60.0) + (100.0 + 100.0) / 2.0 * (3.0 / 60.0)
        assert record.kwh == pytest.approx(expected, rel=1e-6)

    def test_multiple_samples(self, acc: IntervalAccumulator):
        """多筆讀數的梯形積分（含 boundary 尾段補償）"""
        # 100 kW 持續到 10:10，到 10:16 為 200 kW（跨 boundary 10:15）
        acc.feed(100.0, datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc))
        acc.feed(100.0, datetime(2025, 1, 1, 10, 5, 0, tzinfo=timezone.utc))
        acc.feed(200.0, datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc))
        record = acc.feed(200.0, datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc))

        assert record is not None
        # segment 1 (10:00→10:05): 100*5/60
        # segment 2 (10:05→10:10): (100+200)/2*5/60
        # 尾段 (10:10→10:15): prev=200@10:10, curr=200@10:16 → v_b=200，(200+200)/2 * 5/60
        expected = 100.0 * 5.0 / 60.0 + (100.0 + 200.0) / 2.0 * 5.0 / 60.0 + (200.0 + 200.0) / 2.0 * 5.0 / 60.0
        assert record.kwh == pytest.approx(expected, rel=1e-6)


# ======================== DeviceEnergyTracker ========================


class TestDeviceEnergyTracker:
    """DeviceEnergyTracker 多區間追蹤測試"""

    def test_feed_multiple_intervals(self):
        """feed 應同時追蹤所有區間"""
        tracker = DeviceEnergyTracker(
            device_id="dev1",
            intervals=(15, 30),
            meter_type=DeviceMeterType.CUMULATIVE,
        )

        # Fill some data
        tracker.feed(100.0, datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc))
        tracker.feed(110.0, datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc))

        # Cross 15-min boundary only
        records = tracker.feed(120.0, datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc))
        assert len(records) == 1
        assert records[0].interval_minutes == 15

    def test_feed_crosses_both_boundaries(self):
        """同時跨越 15 和 30 分鐘邊界"""
        tracker = DeviceEnergyTracker(
            device_id="dev1",
            intervals=(15, 30),
            meter_type=DeviceMeterType.CUMULATIVE,
        )

        tracker.feed(100.0, datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc))
        tracker.feed(115.0, datetime(2025, 1, 1, 10, 20, 0, tzinfo=timezone.utc))

        # Cross both 30-min boundary (:30) and 15-min boundary (:30)
        records = tracker.feed(130.0, datetime(2025, 1, 1, 10, 31, 0, tzinfo=timezone.utc))
        assert len(records) == 2
        interval_set = {r.interval_minutes for r in records}
        assert interval_set == {15, 30}

    def test_feed_no_boundary(self):
        """未跨越邊界應返回空列表"""
        tracker = DeviceEnergyTracker(
            device_id="dev1",
            intervals=(15, 30, 60),
            meter_type=DeviceMeterType.CUMULATIVE,
        )

        tracker.feed(100.0, datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc))
        records = tracker.feed(105.0, datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc))
        assert records == []


# ======================== IntervalRecord ========================


class TestIntervalRecord:
    """IntervalRecord 測試"""

    def test_frozen(self):
        record = IntervalRecord(
            device_id="dev1",
            interval_minutes=15,
            period_start=datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            period_end=datetime(2025, 1, 1, 10, 15, 0, tzinfo=timezone.utc),
            kwh=10.0,
            sample_count=5,
            meter_type="cumulative",
        )
        with pytest.raises(AttributeError):
            record.kwh = 20.0  # type: ignore[misc]
