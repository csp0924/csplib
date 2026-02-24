"""Tests for DeviceStateSubscriber."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.integration.distributed.config import DistributedConfig, RemoteSiteConfig
from csp_lib.integration.distributed.subscriber import DeviceStateSubscriber


def _make_redis_client(
    state_data: dict | None = None,
    online_data: dict | None = None,
    alarm_data: dict | None = None,
) -> MagicMock:
    """Create a mock RedisClient with configured responses."""
    client = MagicMock()

    # hgetall: device:{id}:state
    state_data = state_data or {}

    async def mock_hgetall(key):
        for device_id, values in state_data.items():
            if key == f"device:{device_id}:state":
                return values
        return {}

    client.hgetall = AsyncMock(side_effect=mock_hgetall)

    # get: device:{id}:online
    online_data = online_data or {}

    async def mock_get(key):
        for device_id, value in online_data.items():
            if key == f"device:{device_id}:online":
                return value
        return None

    client.get = AsyncMock(side_effect=mock_get)

    # smembers: device:{id}:alarms
    alarm_data = alarm_data or {}

    async def mock_smembers(key):
        for device_id, alarms in alarm_data.items():
            if key == f"device:{device_id}:alarms":
                return alarms
        return set()

    client.smembers = AsyncMock(side_effect=mock_smembers)

    return client


def _make_config(device_ids: list[str] | None = None) -> DistributedConfig:
    return DistributedConfig(
        sites=[RemoteSiteConfig(site_id="test_site", device_ids=device_ids or ["d1", "d2"])],
        poll_interval=0.1,
    )


class TestDeviceStateSubscriberInit:
    def test_initial_state(self):
        config = _make_config()
        redis = _make_redis_client()
        sub = DeviceStateSubscriber(config, redis)
        assert sub.device_states == {}
        assert sub.device_online == {}
        assert sub.device_alarms == {}


class TestDeviceStateSubscriberPoll:
    @pytest.mark.asyncio
    async def test_poll_reads_state(self):
        config = _make_config(["d1"])
        redis = _make_redis_client(
            state_data={"d1": {"voltage": 220.0, "current": 10.5}},
            online_data={"d1": "1"},
            alarm_data={"d1": {"OV_001"}},
        )
        sub = DeviceStateSubscriber(config, redis)

        await sub._poll_all()

        assert sub.device_states["d1"] == {"voltage": 220.0, "current": 10.5}
        assert sub.device_online["d1"] is True
        assert sub.device_alarms["d1"] == {"OV_001"}

    @pytest.mark.asyncio
    async def test_poll_offline_device(self):
        config = _make_config(["d1"])
        redis = _make_redis_client(
            state_data={},
            online_data={"d1": "0"},
        )
        sub = DeviceStateSubscriber(config, redis)

        await sub._poll_all()

        assert "d1" not in sub.device_states
        assert sub.device_online["d1"] is False

    @pytest.mark.asyncio
    async def test_poll_missing_online_key(self):
        config = _make_config(["d1"])
        redis = _make_redis_client()
        sub = DeviceStateSubscriber(config, redis)

        await sub._poll_all()

        assert sub.device_online["d1"] is False

    @pytest.mark.asyncio
    async def test_poll_handles_redis_error(self):
        config = _make_config(["d1"])
        redis = _make_redis_client()
        redis.hgetall = AsyncMock(side_effect=ConnectionError("Redis down"))
        redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        redis.smembers = AsyncMock(side_effect=ConnectionError("Redis down"))
        sub = DeviceStateSubscriber(config, redis)

        # Should not raise
        await sub._poll_all()

        assert sub.device_online["d1"] is False
        assert sub.device_alarms["d1"] == set()


class TestDeviceStateSubscriberLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        config = _make_config()
        redis = _make_redis_client()
        sub = DeviceStateSubscriber(config, redis)

        await sub.start()
        assert sub._task is not None
        assert not sub._task.done()

        await sub.stop()
        assert sub._task is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        config = _make_config()
        redis = _make_redis_client()
        sub = DeviceStateSubscriber(config, redis)

        async with sub:
            assert sub._task is not None
        assert sub._task is None

    @pytest.mark.asyncio
    async def test_poll_loop_runs(self):
        config = _make_config(["d1"])
        redis = _make_redis_client(
            state_data={"d1": {"v": 1}},
            online_data={"d1": "1"},
        )
        sub = DeviceStateSubscriber(config, redis)

        async with sub:
            # Wait for at least one poll cycle
            await asyncio.sleep(0.2)
            assert sub.device_states.get("d1") == {"v": 1}
            assert sub.device_online.get("d1") is True
