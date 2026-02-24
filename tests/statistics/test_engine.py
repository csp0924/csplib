# =============== Statistics Tests - Engine ===============
#
# StatisticsEngine 單元測試
#
# 測試覆蓋：
# - 單設備能源追蹤
# - 多設備能源追蹤
# - 功率加總（real-time + 記錄建立）
# - 非數值讀取跳過

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from csp_lib.statistics.config import (
    DeviceMeterType,
    MetricDefinition,
    PowerSumDefinition,
    StatisticsConfig,
)
from csp_lib.statistics.engine import PowerSumRecord, StatisticsEngine


# ======================== Energy Tracking ========================


class TestEngineEnergyTracking:
    """能源追蹤測試"""

    @pytest.fixture
    def engine(self) -> StatisticsEngine:
        config = StatisticsConfig(
            metrics=[
                MetricDefinition("pcs_01", DeviceMeterType.CUMULATIVE, "kwh_total"),
            ],
            intervals_minutes=(15,),
        )
        return StatisticsEngine(config)

    def test_process_read_no_boundary(self, engine: StatisticsEngine):
        """未跨越邊界不產生記錄"""
        records = engine.process_read(
            "pcs_01",
            {"kwh_total": 100.0},
            datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
        )
        assert records == []

    def test_process_read_boundary_crossing(self, engine: StatisticsEngine):
        """跨越邊界產生記錄"""
        engine.process_read(
            "pcs_01",
            {"kwh_total": 100.0},
            datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
        )
        engine.process_read(
            "pcs_01",
            {"kwh_total": 110.0},
            datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc),
        )
        records = engine.process_read(
            "pcs_01",
            {"kwh_total": 120.0},
            datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc),
        )

        assert len(records) == 1
        assert records[0].device_id == "pcs_01"
        assert records[0].kwh == pytest.approx(10.0)

    def test_process_read_unknown_device(self, engine: StatisticsEngine):
        """未配置的設備不追蹤"""
        records = engine.process_read(
            "unknown_device",
            {"kwh_total": 100.0},
            datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
        )
        assert records == []

    def test_process_read_missing_point(self, engine: StatisticsEngine):
        """讀取值中缺少指定 point 時不追蹤"""
        records = engine.process_read(
            "pcs_01",
            {"other_point": 100.0},
            datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
        )
        assert records == []

    def test_process_read_non_numeric_skipped(self, engine: StatisticsEngine):
        """非數值讀取應跳過"""
        records = engine.process_read(
            "pcs_01",
            {"kwh_total": "not_a_number"},
            datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
        )
        assert records == []


class TestEngineMultiDevice:
    """多設備能源追蹤測試"""

    def test_multiple_devices(self):
        config = StatisticsConfig(
            metrics=[
                MetricDefinition("pcs_01", DeviceMeterType.CUMULATIVE, "kwh_total"),
                MetricDefinition("pcs_02", DeviceMeterType.INSTANTANEOUS, "active_power"),
            ],
            intervals_minutes=(15,),
        )
        engine = StatisticsEngine(config)

        # Feed both devices
        engine.process_read(
            "pcs_01", {"kwh_total": 100.0}, datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc)
        )
        engine.process_read(
            "pcs_02", {"active_power": 50.0}, datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc)
        )

        # Cross boundary for both
        engine.process_read(
            "pcs_01", {"kwh_total": 110.0}, datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc)
        )
        engine.process_read(
            "pcs_02", {"active_power": 60.0}, datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc)
        )

        r1 = engine.process_read(
            "pcs_01", {"kwh_total": 120.0}, datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc)
        )
        r2 = engine.process_read(
            "pcs_02", {"active_power": 70.0}, datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc)
        )

        assert len(r1) == 1
        assert r1[0].device_id == "pcs_01"
        assert r1[0].meter_type == "cumulative"

        assert len(r2) == 1
        assert r2[0].device_id == "pcs_02"
        assert r2[0].meter_type == "instantaneous"


# ======================== Power Sums ========================


class TestEnginePowerSums:
    """功率加總測試"""

    @pytest.fixture
    def engine(self) -> StatisticsEngine:
        config = StatisticsConfig(
            power_sums=[
                PowerSumDefinition("p_total_pcs", "pcs", "active_power"),
            ],
            intervals_minutes=(15,),
        )
        engine = StatisticsEngine(config)
        engine.register_power_sum_devices("p_total_pcs", ["pcs_01", "pcs_02"])
        return engine

    def test_initial_power_sum_is_zero(self, engine: StatisticsEngine):
        """初始功率加總應為 0"""
        assert engine.get_power_sum("p_total_pcs") == 0.0

    def test_power_sum_updates_on_read(self, engine: StatisticsEngine):
        """讀取時更新功率加總"""
        engine.process_read(
            "pcs_01",
            {"active_power": 100.0},
            datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
        )
        assert engine.get_power_sum("p_total_pcs") == pytest.approx(100.0)

        engine.process_read(
            "pcs_02",
            {"active_power": 200.0},
            datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
        )
        assert engine.get_power_sum("p_total_pcs") == pytest.approx(300.0)

    def test_power_sum_updates_replace(self, engine: StatisticsEngine):
        """新讀取應取代舊值"""
        engine.process_read(
            "pcs_01",
            {"active_power": 100.0},
            datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
        )
        engine.process_read(
            "pcs_01",
            {"active_power": 150.0},
            datetime(2025, 1, 1, 10, 3, 0, tzinfo=timezone.utc),
        )
        assert engine.get_power_sum("p_total_pcs") == pytest.approx(150.0)

    def test_get_all_power_sums(self, engine: StatisticsEngine):
        """取得所有功率加總"""
        engine.process_read(
            "pcs_01",
            {"active_power": 100.0},
            datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
        )
        sums = engine.get_all_power_sums()
        assert "p_total_pcs" in sums
        assert sums["p_total_pcs"] == pytest.approx(100.0)

    def test_get_unknown_power_sum(self, engine: StatisticsEngine):
        """查詢未知功率加總應回傳 0"""
        assert engine.get_power_sum("nonexistent") == 0.0


class TestEnginePowerSumRecords:
    """功率加總記錄建立測試"""

    def test_build_power_sum_records(self):
        config = StatisticsConfig(
            power_sums=[
                PowerSumDefinition("p_total_pcs", "pcs", "active_power"),
            ],
            intervals_minutes=(15,),
        )
        engine = StatisticsEngine(config)
        engine.register_power_sum_devices("p_total_pcs", ["pcs_01", "pcs_02"])

        engine.process_read(
            "pcs_01",
            {"active_power": 100.0},
            datetime(2025, 1, 1, 10, 5, 0, tzinfo=timezone.utc),
        )
        engine.process_read(
            "pcs_02",
            {"active_power": 200.0},
            datetime(2025, 1, 1, 10, 5, 0, tzinfo=timezone.utc),
        )

        records = engine.build_power_sum_records(
            interval_minutes=15,
            period_start=datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            period_end=datetime(2025, 1, 1, 10, 15, 0, tzinfo=timezone.utc),
        )

        assert len(records) == 1
        assert records[0].name == "p_total_pcs"
        assert records[0].total_power == pytest.approx(300.0)
        assert records[0].device_count == 2
        assert records[0].interval_minutes == 15

    def test_build_records_frozen(self):
        record = PowerSumRecord(
            name="p_total",
            interval_minutes=15,
            period_start=datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            period_end=datetime(2025, 1, 1, 10, 15, 0, tzinfo=timezone.utc),
            total_power=300.0,
            device_count=2,
        )
        with pytest.raises(AttributeError):
            record.total_power = 0.0  # type: ignore[misc]
