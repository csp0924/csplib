# =============== Statistics Tests - Config ===============
#
# StatisticsConfig 單元測試
#
# 測試覆蓋：
# - DeviceMeterType 列舉值
# - MetricDefinition 建構與凍結
# - PowerSumDefinition 建構與凍結
# - StatisticsConfig 預設值與自訂值

from __future__ import annotations

from csp_lib.statistics.config import (
    DeviceMeterType,
    MetricDefinition,
    PowerSumDefinition,
    StatisticsConfig,
)


class TestDeviceMeterType:
    """DeviceMeterType 列舉測試"""

    def test_cumulative_value(self):
        assert DeviceMeterType.CUMULATIVE.value == "cumulative"

    def test_instantaneous_value(self):
        assert DeviceMeterType.INSTANTANEOUS.value == "instantaneous"

    def test_from_string(self):
        assert DeviceMeterType("cumulative") is DeviceMeterType.CUMULATIVE
        assert DeviceMeterType("instantaneous") is DeviceMeterType.INSTANTANEOUS


class TestMetricDefinition:
    """MetricDefinition 測試"""

    def test_create(self):
        metric = MetricDefinition(
            device_id="pcs_01",
            meter_type=DeviceMeterType.CUMULATIVE,
            point_name="kwh_total",
        )
        assert metric.device_id == "pcs_01"
        assert metric.meter_type == DeviceMeterType.CUMULATIVE
        assert metric.point_name == "kwh_total"

    def test_frozen(self):
        metric = MetricDefinition(
            device_id="pcs_01",
            meter_type=DeviceMeterType.CUMULATIVE,
            point_name="kwh_total",
        )
        import pytest

        with pytest.raises(AttributeError):
            metric.device_id = "pcs_02"  # type: ignore[misc]


class TestPowerSumDefinition:
    """PowerSumDefinition 測試"""

    def test_create(self):
        ps = PowerSumDefinition(
            name="p_total_pcs",
            trait="pcs",
            point_name="active_power",
        )
        assert ps.name == "p_total_pcs"
        assert ps.trait == "pcs"
        assert ps.point_name == "active_power"

    def test_frozen(self):
        ps = PowerSumDefinition(
            name="p_total_pcs",
            trait="pcs",
            point_name="active_power",
        )
        import pytest

        with pytest.raises(AttributeError):
            ps.name = "other"  # type: ignore[misc]


class TestStatisticsConfig:
    """StatisticsConfig 測試"""

    def test_defaults(self):
        config = StatisticsConfig()
        assert config.metrics == []
        assert config.power_sums == []
        assert config.intervals_minutes == (15, 30, 60)
        assert config.collection_name == "statistics"

    def test_custom_values(self):
        metric = MetricDefinition("pcs_01", DeviceMeterType.CUMULATIVE, "kwh_total")
        ps = PowerSumDefinition("p_total", "pcs", "active_power")
        config = StatisticsConfig(
            metrics=[metric],
            power_sums=[ps],
            intervals_minutes=(15,),
            collection_name="energy_stats",
        )
        assert len(config.metrics) == 1
        assert len(config.power_sums) == 1
        assert config.intervals_minutes == (15,)
        assert config.collection_name == "energy_stats"

    def test_frozen(self):
        config = StatisticsConfig()
        import pytest

        with pytest.raises(AttributeError):
            config.collection_name = "other"  # type: ignore[misc]
