"""Tests for RemoteCommandRouter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.controller.core import Command
from csp_lib.integration.distributed.command_router import RemoteCommandRouter
from csp_lib.integration.distributed.config import DistributedConfig, RemoteSiteConfig
from csp_lib.integration.schema import CommandMapping


def _make_subscriber(
    online: dict[str, bool] | None = None,
    alarms: dict[str, set[str]] | None = None,
) -> MagicMock:
    sub = MagicMock()
    sub.device_online = online or {}
    sub.device_alarms = alarms or {}
    return sub


def _make_redis() -> MagicMock:
    redis = MagicMock()
    redis.publish = AsyncMock(return_value=1)
    return redis


class TestRemoteCommandRouterRoute:
    @pytest.mark.asyncio
    async def test_route_single_device(self):
        site = RemoteSiteConfig(site_id="s1", device_ids=["d1"])
        config = DistributedConfig(sites=[site])
        redis = _make_redis()
        sub = _make_subscriber(online={"d1": True})
        mappings = [CommandMapping(command_field="p_target", point_name="active_power", device_id="d1")]

        router = RemoteCommandRouter(config, redis, sub, mappings)
        cmd = Command(p_target=100.0)
        await router.route(cmd)

        redis.publish.assert_called_once()
        call_args = redis.publish.call_args
        assert call_args[0][0] == "channel:commands:s1:write"
        import json

        payload = json.loads(call_args[0][1])
        assert payload["device_id"] == "d1"
        assert payload["point_name"] == "active_power"
        assert payload["value"] == 100.0

    @pytest.mark.asyncio
    async def test_route_skips_offline_device(self):
        site = RemoteSiteConfig(site_id="s1", device_ids=["d1"])
        config = DistributedConfig(sites=[site])
        redis = _make_redis()
        sub = _make_subscriber(online={"d1": False})
        mappings = [CommandMapping(command_field="p_target", point_name="active_power", device_id="d1")]

        router = RemoteCommandRouter(config, redis, sub, mappings)
        await router.route(Command(p_target=100.0))

        redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_skips_alarmed_device(self):
        site = RemoteSiteConfig(site_id="s1", device_ids=["d1"])
        config = DistributedConfig(sites=[site])
        redis = _make_redis()
        sub = _make_subscriber(online={"d1": True}, alarms={"d1": {"OV_001"}})
        mappings = [CommandMapping(command_field="p_target", point_name="active_power", device_id="d1")]

        router = RemoteCommandRouter(config, redis, sub, mappings)
        await router.route(Command(p_target=100.0))

        redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_trait_broadcast(self):
        s1 = RemoteSiteConfig(site_id="s1", device_ids=["d1"])
        s2 = RemoteSiteConfig(site_id="s2", device_ids=["d2"])
        config = DistributedConfig(
            sites=[s1, s2],
            trait_device_map={"inverter": ["d1", "d2"]},
        )
        redis = _make_redis()
        sub = _make_subscriber(online={"d1": True, "d2": True})
        mappings = [CommandMapping(command_field="p_target", point_name="sp", trait="inverter")]

        router = RemoteCommandRouter(config, redis, sub, mappings)
        await router.route(Command(p_target=50.0))

        assert redis.publish.call_count == 2
        # Check channels
        channels = [c[0][0] for c in redis.publish.call_args_list]
        assert "channel:commands:s1:write" in channels
        assert "channel:commands:s2:write" in channels

    @pytest.mark.asyncio
    async def test_route_trait_partial_online(self):
        s1 = RemoteSiteConfig(site_id="s1", device_ids=["d1"])
        s2 = RemoteSiteConfig(site_id="s2", device_ids=["d2"])
        config = DistributedConfig(
            sites=[s1, s2],
            trait_device_map={"inverter": ["d1", "d2"]},
        )
        redis = _make_redis()
        sub = _make_subscriber(online={"d1": True, "d2": False})
        mappings = [CommandMapping(command_field="p_target", point_name="sp", trait="inverter")]

        router = RemoteCommandRouter(config, redis, sub, mappings)
        await router.route(Command(p_target=50.0))

        # Only d1 should be published
        assert redis.publish.call_count == 1
        assert "channel:commands:s1:write" in redis.publish.call_args[0][0]

    @pytest.mark.asyncio
    async def test_route_with_transform(self):
        site = RemoteSiteConfig(site_id="s1", device_ids=["d1"])
        config = DistributedConfig(sites=[site])
        redis = _make_redis()
        sub = _make_subscriber(online={"d1": True})
        mappings = [
            CommandMapping(
                command_field="p_target",
                point_name="sp",
                device_id="d1",
                transform=lambda v: v * 10,
            )
        ]

        router = RemoteCommandRouter(config, redis, sub, mappings)
        await router.route(Command(p_target=5.0))

        import json

        payload = json.loads(redis.publish.call_args[0][1])
        assert payload["value"] == 50.0

    @pytest.mark.asyncio
    async def test_route_skips_none_value(self):
        site = RemoteSiteConfig(site_id="s1", device_ids=["d1"])
        config = DistributedConfig(sites=[site])
        redis = _make_redis()
        sub = _make_subscriber(online={"d1": True})
        mappings = [CommandMapping(command_field="p_target", point_name="sp", device_id="d1")]

        router = RemoteCommandRouter(config, redis, sub, mappings)
        # Command with default p_target=0.0 but we test with a field that is None
        cmd = Command()
        # q_target defaults to 0.0, not None, so route with an explicit mapping for non-existent field
        mappings2 = [CommandMapping(command_field="nonexistent", point_name="sp", device_id="d1")]
        router2 = RemoteCommandRouter(config, redis, sub, mappings2)
        await router2.route(cmd)

        redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_unknown_device_in_site_map(self):
        config = DistributedConfig(sites=[])
        redis = _make_redis()
        sub = _make_subscriber(online={"d1": True})
        mappings = [CommandMapping(command_field="p_target", point_name="sp", device_id="d1")]

        router = RemoteCommandRouter(config, redis, sub, mappings)
        await router.route(Command(p_target=100.0))

        # d1 not found in any site
        redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_transform_error(self):
        site = RemoteSiteConfig(site_id="s1", device_ids=["d1"])
        config = DistributedConfig(sites=[site])
        redis = _make_redis()
        sub = _make_subscriber(online={"d1": True})

        def bad_transform(v):
            raise ValueError("bad")

        mappings = [
            CommandMapping(command_field="p_target", point_name="sp", device_id="d1", transform=bad_transform)
        ]

        router = RemoteCommandRouter(config, redis, sub, mappings)
        await router.route(Command(p_target=100.0))

        redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_publish_error(self):
        site = RemoteSiteConfig(site_id="s1", device_ids=["d1"])
        config = DistributedConfig(sites=[site])
        redis = _make_redis()
        redis.publish = AsyncMock(side_effect=ConnectionError("Redis down"))
        sub = _make_subscriber(online={"d1": True})
        mappings = [CommandMapping(command_field="p_target", point_name="sp", device_id="d1")]

        router = RemoteCommandRouter(config, redis, sub, mappings)
        # Should not raise
        await router.route(Command(p_target=100.0))
