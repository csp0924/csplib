"""RedisMonitorPublisher 單元測試"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.equipment.alarm.definition import AlarmDefinition, AlarmLevel
from csp_lib.equipment.alarm.state import AlarmEvent, AlarmEventType
from csp_lib.monitor.collector import ModuleHealthSnapshot, ModuleStatus, SystemMetrics
from csp_lib.monitor.config import MonitorConfig
from csp_lib.monitor.publisher import RedisMonitorPublisher
from csp_lib.core import HealthStatus


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    return redis


@pytest.fixture
def config():
    return MonitorConfig(redis_key_prefix="test", metrics_ttl=30)


@pytest.fixture
def publisher(mock_redis, config):
    return RedisMonitorPublisher(mock_redis, config)


class TestPublishMetrics:
    @pytest.mark.asyncio
    async def test_hset_called_with_metrics(self, publisher, mock_redis):
        metrics = SystemMetrics(cpu_percent=45.0, ram_percent=60.0)
        await publisher.publish_metrics(metrics)

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == "test:metrics"
        mapping = call_args[0][1]
        assert "cpu_percent" in mapping
        assert "updated_at" in mapping

    @pytest.mark.asyncio
    async def test_expire_called(self, publisher, mock_redis):
        await publisher.publish_metrics(SystemMetrics())
        mock_redis.expire.assert_called_once_with("test:metrics", 30)

    @pytest.mark.asyncio
    async def test_publish_channel(self, publisher, mock_redis):
        await publisher.publish_metrics(SystemMetrics(cpu_percent=55.0))
        mock_redis.publish.assert_called_once()
        channel = mock_redis.publish.call_args[0][0]
        assert channel == "channel:test:metrics"
        message = json.loads(mock_redis.publish.call_args[0][1])
        assert message["cpu_percent"] == 55.0


class TestPublishModuleHealth:
    @pytest.mark.asyncio
    async def test_hset_with_module_data(self, publisher, mock_redis):
        snapshot = ModuleHealthSnapshot(
            modules=[ModuleStatus(name="redis", status=HealthStatus.HEALTHY, message="ok")],
            overall_status=HealthStatus.HEALTHY,
        )
        await publisher.publish_module_health(snapshot)

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == "test:modules"
        mapping = call_args[0][1]
        assert mapping["overall_status"] == "healthy"
        assert "module:redis" in mapping

    @pytest.mark.asyncio
    async def test_expire_called(self, publisher, mock_redis):
        snapshot = ModuleHealthSnapshot(modules=[], overall_status=HealthStatus.HEALTHY)
        await publisher.publish_module_health(snapshot)
        mock_redis.expire.assert_called_once_with("test:modules", 30)

    @pytest.mark.asyncio
    async def test_publish_channel(self, publisher, mock_redis):
        snapshot = ModuleHealthSnapshot(modules=[], overall_status=HealthStatus.HEALTHY)
        await publisher.publish_module_health(snapshot)
        channel = mock_redis.publish.call_args[0][0]
        assert channel == "channel:test:modules"


class TestPublishAlarmEvent:
    @pytest.mark.asyncio
    async def test_triggered_adds_to_set(self, publisher, mock_redis):
        alarm = AlarmDefinition(code="SYS_CPU_HIGH", name="CPU 高", level=AlarmLevel.WARNING)
        event = AlarmEvent(
            event_type=AlarmEventType.TRIGGERED,
            alarm=alarm,
            timestamp=datetime.now(timezone.utc),
        )
        await publisher.publish_alarm_event(event)

        mock_redis.sadd.assert_called_once_with("test:alarms", "SYS_CPU_HIGH")
        mock_redis.srem.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleared_removes_from_set(self, publisher, mock_redis):
        alarm = AlarmDefinition(code="SYS_CPU_HIGH", name="CPU 高", level=AlarmLevel.WARNING)
        event = AlarmEvent(
            event_type=AlarmEventType.CLEARED,
            alarm=alarm,
            timestamp=datetime.now(timezone.utc),
        )
        await publisher.publish_alarm_event(event)

        mock_redis.srem.assert_called_once_with("test:alarms", "SYS_CPU_HIGH")
        mock_redis.sadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_alarm_channel(self, publisher, mock_redis):
        alarm = AlarmDefinition(code="SYS_RAM_HIGH", name="RAM 高", level=AlarmLevel.WARNING)
        event = AlarmEvent(
            event_type=AlarmEventType.TRIGGERED,
            alarm=alarm,
            timestamp=datetime.now(timezone.utc),
        )
        await publisher.publish_alarm_event(event)

        channel = mock_redis.publish.call_args[0][0]
        assert channel == "channel:test:alarm"
        message = json.loads(mock_redis.publish.call_args[0][1])
        assert message["type"] == "triggered"
        assert message["alarm"]["code"] == "SYS_RAM_HIGH"
        assert message["alarm"]["level"] == AlarmLevel.WARNING.value


class TestKeyPrefixCustomization:
    @pytest.mark.asyncio
    async def test_custom_prefix(self, mock_redis):
        config = MonitorConfig(redis_key_prefix="site01")
        pub = RedisMonitorPublisher(mock_redis, config)
        await pub.publish_metrics(SystemMetrics())
        assert mock_redis.hset.call_args[0][0] == "site01:metrics"
