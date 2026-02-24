"""SystemMonitor 單元測試"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from csp_lib.core import HealthReport, HealthStatus
from csp_lib.monitor.collector import SystemMetrics
from csp_lib.monitor.config import MonitorConfig
from csp_lib.monitor.manager import SystemMonitor


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    return redis


@pytest.fixture
def mock_dispatcher():
    dispatcher = AsyncMock()
    dispatcher.dispatch = AsyncMock()
    return dispatcher


@pytest.fixture
def config():
    return MonitorConfig(interval_seconds=0.1, hysteresis_activate=1, hysteresis_clear=1)


def _mock_psutil():
    mock = MagicMock()
    mock.cpu_percent.return_value = 45.0
    mem = MagicMock()
    mem.percent = 60.0
    mem.used = 8 * 1024 * 1024 * 1024
    mem.total = 16 * 1024 * 1024 * 1024
    mock.virtual_memory.return_value = mem
    disk = MagicMock()
    disk.percent = 50.0
    mock.disk_usage.return_value = disk
    net = MagicMock()
    net.bytes_sent = 1000
    net.bytes_recv = 2000
    mock.net_io_counters.return_value = net
    return mock


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, mock_redis, config):
        monitor = SystemMonitor(redis_client=mock_redis, config=config)
        assert not monitor.is_running

        with patch.dict("sys.modules", {"psutil": _mock_psutil()}):
            await monitor.start()
            assert monitor.is_running

            await asyncio.sleep(0.05)
            await monitor.stop()
            assert not monitor.is_running

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_redis, config):
        with patch.dict("sys.modules", {"psutil": _mock_psutil()}):
            async with SystemMonitor(redis_client=mock_redis, config=config) as monitor:
                assert monitor.is_running
                await asyncio.sleep(0.05)
            assert not monitor.is_running

    @pytest.mark.asyncio
    async def test_collects_metrics(self, mock_redis, config):
        with patch.dict("sys.modules", {"psutil": _mock_psutil()}):
            async with SystemMonitor(redis_client=mock_redis, config=config) as monitor:
                await asyncio.sleep(0.25)
                assert monitor.last_metrics is not None
                assert monitor.last_metrics.cpu_percent == 45.0

    @pytest.mark.asyncio
    async def test_publishes_to_redis(self, mock_redis, config):
        with patch.dict("sys.modules", {"psutil": _mock_psutil()}):
            async with SystemMonitor(redis_client=mock_redis, config=config):
                await asyncio.sleep(0.25)

        assert mock_redis.hset.called
        assert mock_redis.expire.called
        assert mock_redis.publish.called


class TestAlarmNotification:
    @pytest.mark.asyncio
    async def test_alarm_triggers_notification(self, mock_redis, mock_dispatcher):
        config = MonitorConfig(interval_seconds=0.1, hysteresis_activate=1, hysteresis_clear=1)
        mock_psutil = _mock_psutil()
        mock_psutil.cpu_percent.return_value = 95.0  # 超過閾值

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            async with SystemMonitor(
                redis_client=mock_redis, dispatcher=mock_dispatcher, config=config
            ) as monitor:
                await asyncio.sleep(0.25)
                assert "SYS_CPU_HIGH" in monitor.active_alarms

        assert mock_dispatcher.dispatch.called
        notification = mock_dispatcher.dispatch.call_args[0][0]
        assert notification.device_id == "__system__"
        assert "SYS_CPU_HIGH" in notification.alarm_key

    @pytest.mark.asyncio
    async def test_alarm_publishes_to_redis_set(self, mock_redis):
        config = MonitorConfig(interval_seconds=0.1, hysteresis_activate=1, hysteresis_clear=1)
        mock_psutil = _mock_psutil()
        mock_psutil.cpu_percent.return_value = 95.0

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            async with SystemMonitor(redis_client=mock_redis, config=config):
                await asyncio.sleep(0.25)

        assert mock_redis.sadd.called


class TestRedisFailureResilience:
    @pytest.mark.asyncio
    async def test_continues_on_redis_failure(self, config):
        redis = AsyncMock()
        redis.hset.side_effect = ConnectionError("Redis down")
        redis.expire.side_effect = ConnectionError("Redis down")
        redis.publish.side_effect = ConnectionError("Redis down")

        with patch.dict("sys.modules", {"psutil": _mock_psutil()}):
            async with SystemMonitor(redis_client=redis, config=config) as monitor:
                await asyncio.sleep(0.25)
                # 即使 Redis 失敗也應繼續運行
                assert monitor.is_running
                assert monitor.last_metrics is not None


class TestModuleHealth:
    @pytest.mark.asyncio
    async def test_register_module(self, mock_redis, config):
        module = MagicMock()
        module.health.return_value = HealthReport(
            status=HealthStatus.HEALTHY, component="test", message="ok"
        )

        with patch.dict("sys.modules", {"psutil": _mock_psutil()}):
            monitor = SystemMonitor(redis_client=mock_redis, config=config)
            monitor.register_module("test", module)

            async with monitor:
                await asyncio.sleep(0.25)
                assert monitor.last_module_health is not None
                assert len(monitor.last_module_health.modules) == 1

    @pytest.mark.asyncio
    async def test_register_check(self, mock_redis, config):
        def check() -> HealthReport:
            return HealthReport(status=HealthStatus.DEGRADED, component="redis", message="slow")

        with patch.dict("sys.modules", {"psutil": _mock_psutil()}):
            monitor = SystemMonitor(redis_client=mock_redis, config=config)
            monitor.register_check("redis", check)

            async with monitor:
                await asyncio.sleep(0.25)
                assert monitor.last_module_health is not None
                assert monitor.last_module_health.overall_status == HealthStatus.DEGRADED


class TestHealthReport:
    def test_not_running(self):
        monitor = SystemMonitor()
        report = monitor.health()
        assert report.status == HealthStatus.UNHEALTHY
        assert report.component == "SystemMonitor"

    @pytest.mark.asyncio
    async def test_healthy_when_running(self, mock_redis, config):
        with patch.dict("sys.modules", {"psutil": _mock_psutil()}):
            async with SystemMonitor(redis_client=mock_redis, config=config) as monitor:
                await asyncio.sleep(0.15)
                report = monitor.health()
                assert report.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_degraded_with_active_alarms(self, mock_redis):
        config = MonitorConfig(interval_seconds=0.1, hysteresis_activate=1, hysteresis_clear=1)
        mock_psutil = _mock_psutil()
        mock_psutil.cpu_percent.return_value = 95.0

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            async with SystemMonitor(redis_client=mock_redis, config=config) as monitor:
                await asyncio.sleep(0.25)
                report = monitor.health()
                assert report.status == HealthStatus.DEGRADED
                assert "SYS_CPU_HIGH" in report.details["active_alarms"]


class TestNoRedis:
    @pytest.mark.asyncio
    async def test_works_without_redis(self, config):
        with patch.dict("sys.modules", {"psutil": _mock_psutil()}):
            async with SystemMonitor(config=config) as monitor:
                await asyncio.sleep(0.25)
                assert monitor.is_running
                assert monitor.last_metrics is not None
