from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.controller.core import Command
from csp_lib.integration.command_router import CommandRouter
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CommandMapping


def _make_device(device_id, responsive=True, protected=False):
    d = MagicMock()
    d.device_id = device_id
    d.is_responsive = responsive
    d.is_protected = protected
    d.write = AsyncMock()
    return d


class TestCommandRouterEdgeCases:
    @pytest.mark.asyncio
    async def test_transform_failure_skips_mapping(self):
        registry = DeviceRegistry()
        device = _make_device("dev1")
        registry.register(device)
        mapping = CommandMapping(
            command_field="p_target",
            point_name="p_out",
            device_id="dev1",
            transform=lambda x: 1 / 0,  # will raise ZeroDivisionError
        )
        router = CommandRouter(registry, [mapping])
        await router.route(Command(p_target=100))
        device.write.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nonexistent_device_logs_warning(self):
        registry = DeviceRegistry()
        mapping = CommandMapping(
            command_field="p_target",
            point_name="p_out",
            device_id="nonexistent",
        )
        router = CommandRouter(registry, [mapping])
        # Should not raise
        await router.route(Command(p_target=100))

    @pytest.mark.asyncio
    async def test_non_responsive_device_skipped(self):
        registry = DeviceRegistry()
        device = _make_device("dev1", responsive=False)
        registry.register(device)
        mapping = CommandMapping(
            command_field="p_target",
            point_name="p_out",
            device_id="dev1",
        )
        router = CommandRouter(registry, [mapping])
        await router.route(Command(p_target=100))
        device.write.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_mappings(self):
        registry = DeviceRegistry()
        router = CommandRouter(registry, [])
        await router.route(Command(p_target=100))  # should not raise

    @pytest.mark.asyncio
    async def test_protected_device_skipped(self):
        registry = DeviceRegistry()
        device = _make_device("dev1", responsive=True, protected=True)
        registry.register(device)
        mapping = CommandMapping(
            command_field="p_target",
            point_name="p_out",
            device_id="dev1",
        )
        router = CommandRouter(registry, [mapping])
        await router.route(Command(p_target=100))
        device.write.assert_not_awaited()
