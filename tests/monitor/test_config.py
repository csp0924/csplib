"""MonitorConfig / MetricThresholds 單元測試"""

import pytest

from csp_lib.monitor.config import MetricThresholds, MonitorConfig


# ================ MetricThresholds ================


class TestMetricThresholds:
    def test_defaults(self):
        t = MetricThresholds()
        assert t.cpu_percent == 90.0
        assert t.ram_percent == 85.0
        assert t.disk_percent == 95.0

    def test_frozen(self):
        t = MetricThresholds()
        with pytest.raises(AttributeError):
            t.cpu_percent = 50.0  # type: ignore[misc]

    def test_custom_values(self):
        t = MetricThresholds(cpu_percent=80.0, ram_percent=70.0, disk_percent=90.0)
        assert t.cpu_percent == 80.0
        assert t.ram_percent == 70.0
        assert t.disk_percent == 90.0

    @pytest.mark.parametrize("field", ["cpu_percent", "ram_percent", "disk_percent"])
    def test_invalid_zero(self, field):
        with pytest.raises(ValueError):
            MetricThresholds(**{field: 0.0})

    @pytest.mark.parametrize("field", ["cpu_percent", "ram_percent", "disk_percent"])
    def test_invalid_negative(self, field):
        with pytest.raises(ValueError):
            MetricThresholds(**{field: -10.0})

    @pytest.mark.parametrize("field", ["cpu_percent", "ram_percent", "disk_percent"])
    def test_invalid_over_100(self, field):
        with pytest.raises(ValueError):
            MetricThresholds(**{field: 101.0})

    def test_boundary_100(self):
        t = MetricThresholds(cpu_percent=100.0, ram_percent=100.0, disk_percent=100.0)
        assert t.cpu_percent == 100.0


# ================ MonitorConfig ================


class TestMonitorConfig:
    def test_defaults(self):
        c = MonitorConfig()
        assert c.interval_seconds == 5.0
        assert c.metrics_ttl == 30
        assert c.hysteresis_activate == 3
        assert c.hysteresis_clear == 3
        assert c.disk_paths == ("/",)
        assert c.redis_key_prefix == "system"
        assert c.enable_cpu is True
        assert c.enable_ram is True
        assert c.enable_disk is True
        assert c.enable_network is True
        assert c.enable_module_health is True

    def test_frozen(self):
        c = MonitorConfig()
        with pytest.raises(AttributeError):
            c.interval_seconds = 10.0  # type: ignore[misc]

    def test_invalid_interval(self):
        with pytest.raises(ValueError):
            MonitorConfig(interval_seconds=0)

    def test_invalid_negative_interval(self):
        with pytest.raises(ValueError):
            MonitorConfig(interval_seconds=-1.0)

    def test_invalid_metrics_ttl(self):
        with pytest.raises(ValueError):
            MonitorConfig(metrics_ttl=0)

    def test_invalid_hysteresis_activate(self):
        with pytest.raises(ValueError):
            MonitorConfig(hysteresis_activate=0)

    def test_invalid_hysteresis_clear(self):
        with pytest.raises(ValueError):
            MonitorConfig(hysteresis_clear=0)

    def test_empty_disk_paths(self):
        with pytest.raises(ValueError):
            MonitorConfig(disk_paths=())

    def test_empty_redis_key_prefix(self):
        with pytest.raises(ValueError):
            MonitorConfig(redis_key_prefix="")

    def test_custom_config(self):
        c = MonitorConfig(
            interval_seconds=10.0,
            thresholds=MetricThresholds(cpu_percent=80.0),
            enable_network=False,
            redis_key_prefix="test",
            metrics_ttl=60,
            hysteresis_activate=5,
            hysteresis_clear=5,
            disk_paths=("/", "/data"),
        )
        assert c.interval_seconds == 10.0
        assert c.thresholds.cpu_percent == 80.0
        assert c.enable_network is False
        assert c.redis_key_prefix == "test"
        assert c.disk_paths == ("/", "/data")
