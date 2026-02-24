"""Tests for RemoteSiteRunner."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.integration.distributed.config import RemoteSiteConfig
from csp_lib.integration.distributed.site_runner import RemoteSiteRunner


def _make_unified_manager(has_command_manager: bool = True) -> MagicMock:
    mgr = MagicMock()
    mgr.start = AsyncMock()
    mgr.stop = AsyncMock()
    type(mgr).is_running = PropertyMock(return_value=False)

    if has_command_manager:
        mgr.command_manager = MagicMock()
    else:
        mgr.command_manager = None

    return mgr


def _make_redis() -> MagicMock:
    redis = MagicMock()
    redis._client = MagicMock()
    # Mock pubsub for RedisCommandAdapter
    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.aclose = AsyncMock()
    pubsub.get_message = AsyncMock(return_value=None)
    redis._client.pubsub = MagicMock(return_value=pubsub)
    return redis


class TestRemoteSiteRunnerInit:
    def test_basic_init(self):
        config = RemoteSiteConfig(site_id="test", device_ids=["d1"])
        mgr = _make_unified_manager()
        redis = _make_redis()
        runner = RemoteSiteRunner(config, mgr, redis)

        assert runner.site_id == "test"
        assert runner.unified_manager is mgr
        assert runner.adapter is None

    def test_is_running_delegates_to_manager(self):
        config = RemoteSiteConfig(site_id="test", device_ids=["d1"])
        mgr = _make_unified_manager()
        redis = _make_redis()
        runner = RemoteSiteRunner(config, mgr, redis)

        assert runner.is_running is False


class TestRemoteSiteRunnerLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        config = RemoteSiteConfig(site_id="test", device_ids=["d1"])
        mgr = _make_unified_manager()
        redis = _make_redis()
        runner = RemoteSiteRunner(config, mgr, redis)

        await runner.start()
        mgr.start.assert_called_once()
        assert runner.adapter is not None

        await runner.stop()
        mgr.stop.assert_called_once()
        assert runner.adapter is None

    @pytest.mark.asyncio
    async def test_start_without_command_manager(self):
        config = RemoteSiteConfig(site_id="test", device_ids=["d1"])
        mgr = _make_unified_manager(has_command_manager=False)
        redis = _make_redis()
        runner = RemoteSiteRunner(config, mgr, redis)

        await runner.start()
        mgr.start.assert_called_once()
        assert runner.adapter is None

        await runner.stop()

    @pytest.mark.asyncio
    async def test_custom_channels(self):
        config = RemoteSiteConfig(
            site_id="test",
            device_ids=["d1"],
            command_channel="custom:cmd",
            result_channel="custom:res",
        )
        mgr = _make_unified_manager()
        redis = _make_redis()
        runner = RemoteSiteRunner(config, mgr, redis)

        await runner.start()
        assert runner.adapter is not None
        assert runner.adapter._command_channel == "custom:cmd"
        assert runner.adapter._result_channel == "custom:res"

        await runner.stop()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        config = RemoteSiteConfig(site_id="test", device_ids=["d1"])
        mgr = _make_unified_manager()
        redis = _make_redis()
        runner = RemoteSiteRunner(config, mgr, redis)

        async with runner:
            mgr.start.assert_called_once()

        mgr.stop.assert_called_once()
