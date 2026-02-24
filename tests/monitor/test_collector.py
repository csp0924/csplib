"""SystemMetricsCollector / ModuleHealthCollector 單元測試"""

from unittest.mock import MagicMock, patch

import pytest

from csp_lib.core import HealthReport, HealthStatus
from csp_lib.monitor.collector import (
    ModuleHealthCollector,
    ModuleHealthSnapshot,
    ModuleStatus,
    SystemMetrics,
    SystemMetricsCollector,
)
from csp_lib.monitor.config import MonitorConfig


# ================ SystemMetrics ================


class TestSystemMetrics:
    def test_defaults(self):
        m = SystemMetrics()
        assert m.cpu_percent == 0.0
        assert m.ram_percent == 0.0
        assert m.disk_usage == {}

    def test_to_dict(self):
        m = SystemMetrics(
            cpu_percent=55.123,
            ram_percent=70.456,
            ram_used_mb=8192.789,
            ram_total_mb=16384.0,
            disk_usage={"/": 45.678},
            net_bytes_sent=1000,
            net_bytes_recv=2000,
            net_send_rate=100.567,
            net_recv_rate=200.123,
        )
        d = m.to_dict()
        assert d["cpu_percent"] == 55.1
        assert d["ram_percent"] == 70.5
        assert d["ram_used_mb"] == 8192.8
        assert d["disk_usage"]["/"] == 45.7
        assert d["net_send_rate"] == 100.6


# ================ ModuleHealthSnapshot ================


class TestModuleHealthSnapshot:
    def test_to_dict(self):
        snap = ModuleHealthSnapshot(
            modules=[
                ModuleStatus(name="redis", status=HealthStatus.HEALTHY, message="ok"),
                ModuleStatus(name="mongo", status=HealthStatus.DEGRADED, message="slow"),
            ],
            overall_status=HealthStatus.DEGRADED,
        )
        d = snap.to_dict()
        assert d["overall_status"] == "degraded"
        assert d["modules"]["redis"]["status"] == "healthy"
        assert d["modules"]["mongo"]["status"] == "degraded"


# ================ SystemMetricsCollector ================


class TestSystemMetricsCollector:
    def _mock_psutil(self):
        """建立 mock psutil 模組"""
        mock = MagicMock()
        mock.cpu_percent.return_value = 45.0

        mem_mock = MagicMock()
        mem_mock.percent = 60.0
        mem_mock.used = 8 * 1024 * 1024 * 1024  # 8 GB
        mem_mock.total = 16 * 1024 * 1024 * 1024  # 16 GB
        mock.virtual_memory.return_value = mem_mock

        disk_mock = MagicMock()
        disk_mock.percent = 50.0
        mock.disk_usage.return_value = disk_mock

        net_mock = MagicMock()
        net_mock.bytes_sent = 1000
        net_mock.bytes_recv = 2000
        mock.net_io_counters.return_value = net_mock

        return mock

    def test_collect_all_enabled(self):
        config = MonitorConfig()
        collector = SystemMetricsCollector(config)
        mock_psutil = self._mock_psutil()

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            metrics = collector.collect()

        assert metrics.cpu_percent == 45.0
        assert metrics.ram_percent == 60.0
        assert metrics.ram_used_mb == pytest.approx(8192.0)
        assert metrics.ram_total_mb == pytest.approx(16384.0)
        assert "/" in metrics.disk_usage
        assert metrics.disk_usage["/"] == 50.0

    def test_collect_cpu_disabled(self):
        config = MonitorConfig(enable_cpu=False)
        collector = SystemMetricsCollector(config)
        mock_psutil = self._mock_psutil()

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            metrics = collector.collect()

        assert metrics.cpu_percent == 0.0
        mock_psutil.cpu_percent.assert_not_called()

    def test_collect_ram_disabled(self):
        config = MonitorConfig(enable_ram=False)
        collector = SystemMetricsCollector(config)
        mock_psutil = self._mock_psutil()

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            metrics = collector.collect()

        assert metrics.ram_percent == 0.0
        mock_psutil.virtual_memory.assert_not_called()

    def test_collect_disk_disabled(self):
        config = MonitorConfig(enable_disk=False)
        collector = SystemMetricsCollector(config)
        mock_psutil = self._mock_psutil()

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            metrics = collector.collect()

        assert metrics.disk_usage == {}
        mock_psutil.disk_usage.assert_not_called()

    def test_collect_network_disabled(self):
        config = MonitorConfig(enable_network=False)
        collector = SystemMetricsCollector(config)
        mock_psutil = self._mock_psutil()

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            metrics = collector.collect()

        assert metrics.net_bytes_sent == 0
        assert metrics.net_bytes_recv == 0
        mock_psutil.net_io_counters.assert_not_called()

    def test_network_rate_calculation(self):
        config = MonitorConfig()
        collector = SystemMetricsCollector(config)
        mock_psutil = self._mock_psutil()

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            # 第一次收集：建立基準，rate 為 0
            m1 = collector.collect()
            assert m1.net_send_rate == 0.0
            assert m1.net_recv_rate == 0.0

            # 更新網路計數器
            net_mock2 = MagicMock()
            net_mock2.bytes_sent = 2000  # +1000
            net_mock2.bytes_recv = 4000  # +2000
            mock_psutil.net_io_counters.return_value = net_mock2

            # 模擬時間流逝
            collector._last_net_time -= 1.0  # 回推 1 秒

            m2 = collector.collect()
            assert m2.net_send_rate > 0
            assert m2.net_recv_rate > 0

    def test_disk_path_error_handled(self):
        config = MonitorConfig(disk_paths=("/nonexistent",))
        collector = SystemMetricsCollector(config)
        mock_psutil = self._mock_psutil()
        mock_psutil.disk_usage.side_effect = OSError("No such path")

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            metrics = collector.collect()

        assert metrics.disk_usage == {}


# ================ ModuleHealthCollector ================


class TestModuleHealthCollector:
    def test_register_and_collect_module(self):
        collector = ModuleHealthCollector()
        module = MagicMock()
        module.health.return_value = HealthReport(
            status=HealthStatus.HEALTHY,
            component="test",
            message="ok",
        )
        collector.register_module("test", module)

        snapshot = collector.collect()
        assert len(snapshot.modules) == 1
        assert snapshot.modules[0].name == "test"
        assert snapshot.modules[0].status == HealthStatus.HEALTHY
        assert snapshot.overall_status == HealthStatus.HEALTHY

    def test_register_and_collect_check(self):
        collector = ModuleHealthCollector()

        def check() -> HealthReport:
            return HealthReport(status=HealthStatus.DEGRADED, component="redis", message="slow")

        collector.register_check("redis", check)

        snapshot = collector.collect()
        assert len(snapshot.modules) == 1
        assert snapshot.modules[0].status == HealthStatus.DEGRADED
        assert snapshot.overall_status == HealthStatus.DEGRADED

    def test_module_health_exception(self):
        collector = ModuleHealthCollector()
        module = MagicMock()
        module.health.side_effect = RuntimeError("boom")
        collector.register_module("broken", module)

        snapshot = collector.collect()
        assert snapshot.modules[0].status == HealthStatus.UNHEALTHY
        assert "boom" in snapshot.modules[0].message
        assert snapshot.overall_status == HealthStatus.UNHEALTHY

    def test_check_exception(self):
        collector = ModuleHealthCollector()

        def bad_check() -> HealthReport:
            raise RuntimeError("fail")

        collector.register_check("bad", bad_check)

        snapshot = collector.collect()
        assert snapshot.modules[0].status == HealthStatus.UNHEALTHY
        assert snapshot.overall_status == HealthStatus.UNHEALTHY

    def test_overall_healthy(self):
        collector = ModuleHealthCollector()
        for name in ("a", "b"):
            m = MagicMock()
            m.health.return_value = HealthReport(status=HealthStatus.HEALTHY, component=name)
            collector.register_module(name, m)

        snapshot = collector.collect()
        assert snapshot.overall_status == HealthStatus.HEALTHY

    def test_overall_degraded(self):
        collector = ModuleHealthCollector()
        m1 = MagicMock()
        m1.health.return_value = HealthReport(status=HealthStatus.HEALTHY, component="a")
        m2 = MagicMock()
        m2.health.return_value = HealthReport(status=HealthStatus.DEGRADED, component="b")
        collector.register_module("a", m1)
        collector.register_module("b", m2)

        snapshot = collector.collect()
        assert snapshot.overall_status == HealthStatus.DEGRADED

    def test_overall_unhealthy_takes_priority(self):
        collector = ModuleHealthCollector()
        m1 = MagicMock()
        m1.health.return_value = HealthReport(status=HealthStatus.DEGRADED, component="a")
        m2 = MagicMock()
        m2.health.return_value = HealthReport(status=HealthStatus.UNHEALTHY, component="b")
        collector.register_module("a", m1)
        collector.register_module("b", m2)

        snapshot = collector.collect()
        assert snapshot.overall_status == HealthStatus.UNHEALTHY

    def test_empty_collector(self):
        collector = ModuleHealthCollector()
        snapshot = collector.collect()
        assert snapshot.modules == []
        assert snapshot.overall_status == HealthStatus.HEALTHY
