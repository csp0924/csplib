"""Tests for CommandRouter."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command
from csp_lib.core.errors import DeviceError
from csp_lib.integration.command_router import CommandRouter
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CommandMapping


def _make_device(device_id: str, responsive: bool = True, protected: bool = False) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    dev.write = AsyncMock()
    return dev


class TestCommandRouterDeviceIdMode:
    @pytest.mark.asyncio
    async def test_route_p_target(self):
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
        )
        await router.route(Command(p_target=1000.0, q_target=200.0))
        dev.write.assert_awaited_once_with("p_set", 1000.0)

    @pytest.mark.asyncio
    async def test_route_q_target(self):
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="q_target", point_name="q_set", device_id="pcs1")],
        )
        await router.route(Command(p_target=1000.0, q_target=200.0))
        dev.write.assert_awaited_once_with("q_set", 200.0)

    @pytest.mark.asyncio
    async def test_transform(self):
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        router = CommandRouter(
            reg,
            [
                CommandMapping(
                    command_field="p_target",
                    point_name="p_set",
                    device_id="pcs1",
                    transform=lambda p: p / 2,
                )
            ],
        )
        await router.route(Command(p_target=1000.0))
        dev.write.assert_awaited_once_with("p_set", 500.0)

    @pytest.mark.asyncio
    async def test_transform_exception_skips(self):
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        def bad_transform(v):
            raise ValueError("boom")

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1", transform=bad_transform)],
        )
        await router.route(Command(p_target=1000.0))
        dev.write.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_device_not_found(self):
        reg = DeviceRegistry()
        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", device_id="missing")],
        )
        # Should not raise
        await router.route(Command(p_target=1000.0))

    @pytest.mark.asyncio
    async def test_device_not_responsive(self):
        reg = DeviceRegistry()
        dev = _make_device("pcs1", responsive=False)
        reg.register(dev)

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
        )
        await router.route(Command(p_target=1000.0))
        dev.write.assert_not_awaited()


class TestCommandRouterTraitMode:
    @pytest.mark.asyncio
    async def test_broadcast_write(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1")
        d2 = _make_device("d2")
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", trait="pcs")],
        )
        await router.route(Command(p_target=1000.0))
        d1.write.assert_awaited_once_with("p_set", 1000.0)
        d2.write.assert_awaited_once_with("p_set", 1000.0)

    @pytest.mark.asyncio
    async def test_broadcast_with_transform(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1")
        d2 = _make_device("d2")
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        router = CommandRouter(
            reg,
            [
                CommandMapping(
                    command_field="p_target",
                    point_name="p_set",
                    trait="pcs",
                    transform=lambda p: p / 2,
                )
            ],
        )
        await router.route(Command(p_target=1000.0))
        d1.write.assert_awaited_once_with("p_set", 500.0)
        d2.write.assert_awaited_once_with("p_set", 500.0)

    @pytest.mark.asyncio
    async def test_single_device_failure_does_not_stop_others(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1")
        d2 = _make_device("d2")
        d1.write = AsyncMock(side_effect=DeviceError("d1", "write error"))
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", trait="pcs")],
        )
        await router.route(Command(p_target=1000.0))
        # d1 failed but d2 should still be written
        d2.write.assert_awaited_once_with("p_set", 1000.0)

    @pytest.mark.asyncio
    async def test_no_responsive_devices(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=False)
        reg.register(d1, traits=["pcs"])

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", trait="pcs")],
        )
        # Should not raise
        await router.route(Command(p_target=1000.0))
        d1.write.assert_not_awaited()


class TestCommandRouterMultipleMappings:
    @pytest.mark.asyncio
    async def test_multiple_mappings(self):
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        router = CommandRouter(
            reg,
            [
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
                CommandMapping(command_field="q_target", point_name="q_set", device_id="pcs1"),
            ],
        )
        await router.route(Command(p_target=1000.0, q_target=200.0))
        assert dev.write.await_count == 2
        dev.write.assert_any_await("p_set", 1000.0)
        dev.write.assert_any_await("q_set", 200.0)


class TestCommandRouterProtectedDevice:
    @pytest.mark.asyncio
    async def test_protected_device_skipped_single(self):
        """is_protected 設備在 device_id 模式下被跳過"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", protected=True)
        reg.register(dev)

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
        )
        await router.route(Command(p_target=1000.0))
        dev.write.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_protected_device_skipped_broadcast(self):
        """is_protected 設備在 trait 廣播中被過濾"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", protected=True)
        d2 = _make_device("d2", protected=False)
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", trait="pcs")],
        )
        await router.route(Command(p_target=1000.0))
        d1.write.assert_not_awaited()
        d2.write.assert_awaited_once_with("p_set", 1000.0)

    @pytest.mark.asyncio
    async def test_non_protected_device_written(self):
        """非 protected 設備正常寫入"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", protected=False)
        reg.register(dev)

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
        )
        await router.route(Command(p_target=1000.0))
        dev.write.assert_awaited_once_with("p_set", 1000.0)
