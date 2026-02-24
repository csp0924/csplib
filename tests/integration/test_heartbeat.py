"""Tests for HeartbeatService."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.integration.heartbeat import HeartbeatService
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import HeartbeatMapping, HeartbeatMode


def _make_device(device_id: str, responsive: bool = True) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    dev.write = AsyncMock()
    return dev


class TestHeartbeatMapping:
    def test_toggle_mode_default(self):
        m = HeartbeatMapping(point_name="heartbeat", trait="pcs")
        assert m.mode == HeartbeatMode.TOGGLE

    def test_device_id_mode(self):
        m = HeartbeatMapping(point_name="heartbeat", device_id="pcs_01")
        assert m.device_id == "pcs_01"
        assert m.trait is None

    def test_both_device_and_trait_raises(self):
        with pytest.raises(ValueError, match="Cannot set both"):
            HeartbeatMapping(point_name="hb", device_id="a", trait="b")

    def test_neither_device_nor_trait_raises(self):
        with pytest.raises(ValueError, match="Must set either"):
            HeartbeatMapping(point_name="hb")


class TestHeartbeatServiceNextValue:
    """Test value generation logic without running the async loop."""

    def _make_service(self, mappings: list[HeartbeatMapping]) -> HeartbeatService:
        reg = DeviceRegistry()
        return HeartbeatService(reg, mappings)

    def test_toggle_alternates(self):
        mapping = HeartbeatMapping(point_name="hb", trait="pcs", mode=HeartbeatMode.TOGGLE)
        svc = self._make_service([mapping])
        v1 = svc._next_value_for_mapping(mapping)
        v2 = svc._next_value_for_mapping(mapping)
        v3 = svc._next_value_for_mapping(mapping)
        assert v1 == 1
        assert v2 == 0
        assert v3 == 1

    def test_increment_wraps(self):
        mapping = HeartbeatMapping(point_name="hb", trait="pcs", mode=HeartbeatMode.INCREMENT, increment_max=2)
        svc = self._make_service([mapping])
        values = [svc._next_value_for_mapping(mapping) for _ in range(5)]
        assert values == [1, 2, 0, 1, 2]

    def test_constant_returns_fixed_value(self):
        mapping = HeartbeatMapping(point_name="hb", trait="pcs", mode=HeartbeatMode.CONSTANT, constant_value=42)
        svc = self._make_service([mapping])
        v1 = svc._next_value_for_mapping(mapping)
        v2 = svc._next_value_for_mapping(mapping)
        assert v1 == 42
        assert v2 == 42

    def test_reset_counters(self):
        mapping = HeartbeatMapping(point_name="hb", trait="pcs", mode=HeartbeatMode.TOGGLE)
        svc = self._make_service([mapping])
        svc._next_value_for_mapping(mapping)  # 1
        svc.reset_counters()
        assert svc._next_value_for_mapping(mapping) == 1  # starts fresh


class TestHeartbeatServiceAsync:
    @pytest.mark.asyncio
    async def test_writes_to_device_by_device_id(self):
        dev = _make_device("pcs_01")
        reg = DeviceRegistry()
        reg.register(dev, traits=["pcs"])

        mapping = HeartbeatMapping(point_name="heartbeat", device_id="pcs_01")
        svc = HeartbeatService(reg, [mapping], interval=0.05)

        await svc.start()
        await asyncio.sleep(0.12)
        await svc.stop()

        assert dev.write.call_count >= 1
        dev.write.assert_any_call("heartbeat", 1)

    @pytest.mark.asyncio
    async def test_writes_to_devices_by_trait(self):
        dev1 = _make_device("pcs_01")
        dev2 = _make_device("pcs_02")
        reg = DeviceRegistry()
        reg.register(dev1, traits=["pcs"])
        reg.register(dev2, traits=["pcs"])

        mapping = HeartbeatMapping(point_name="heartbeat", trait="pcs")
        svc = HeartbeatService(reg, [mapping], interval=0.05)

        await svc.start()
        await asyncio.sleep(0.12)
        await svc.stop()

        assert dev1.write.call_count >= 1
        assert dev2.write.call_count >= 1

    @pytest.mark.asyncio
    async def test_skips_unresponsive_device(self):
        dev = _make_device("pcs_01", responsive=False)
        reg = DeviceRegistry()
        reg.register(dev, traits=["pcs"])

        mapping = HeartbeatMapping(point_name="heartbeat", device_id="pcs_01")
        svc = HeartbeatService(reg, [mapping], interval=0.05)

        await svc.start()
        await asyncio.sleep(0.12)
        await svc.stop()

        dev.write.assert_not_called()

    @pytest.mark.asyncio
    async def test_pause_stops_writes(self):
        dev = _make_device("pcs_01")
        reg = DeviceRegistry()
        reg.register(dev, traits=["pcs"])

        mapping = HeartbeatMapping(point_name="heartbeat", device_id="pcs_01")
        svc = HeartbeatService(reg, [mapping], interval=0.05)

        await svc.start()
        await asyncio.sleep(0.08)
        assert dev.write.call_count >= 1  # confirm writes happened before pause

        svc.pause()
        assert svc.is_paused is True
        dev.write.reset_mock()

        await asyncio.sleep(0.12)
        assert dev.write.call_count == 0  # no writes while paused

        await svc.stop()

    @pytest.mark.asyncio
    async def test_resume_restarts_writes(self):
        dev = _make_device("pcs_01")
        reg = DeviceRegistry()
        reg.register(dev, traits=["pcs"])

        mapping = HeartbeatMapping(point_name="heartbeat", device_id="pcs_01")
        svc = HeartbeatService(reg, [mapping], interval=0.05)

        await svc.start()
        svc.pause()
        dev.write.reset_mock()

        await asyncio.sleep(0.08)
        assert dev.write.call_count == 0

        svc.resume()
        assert svc.is_paused is False
        await asyncio.sleep(0.12)
        assert dev.write.call_count >= 1

        await svc.stop()

    @pytest.mark.asyncio
    async def test_write_failure_does_not_crash(self):
        from csp_lib.core.errors import DeviceError

        dev = _make_device("pcs_01")
        dev.write = AsyncMock(side_effect=DeviceError("pcs_01", "write failed"))
        reg = DeviceRegistry()
        reg.register(dev, traits=["pcs"])

        mapping = HeartbeatMapping(point_name="heartbeat", device_id="pcs_01")
        svc = HeartbeatService(reg, [mapping], interval=0.05)

        await svc.start()
        await asyncio.sleep(0.12)
        await svc.stop()

        # service should still be running despite write failures
        assert dev.write.call_count >= 1

    @pytest.mark.asyncio
    async def test_is_running_property(self):
        reg = DeviceRegistry()
        mapping = HeartbeatMapping(point_name="hb", trait="pcs")
        svc = HeartbeatService(reg, [mapping], interval=0.05)

        assert svc.is_running is False
        await svc.start()
        assert svc.is_running is True
        await svc.stop()
        assert svc.is_running is False

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self):
        reg = DeviceRegistry()
        mapping = HeartbeatMapping(point_name="hb", trait="pcs")
        svc = HeartbeatService(reg, [mapping], interval=0.05)

        await svc.start()
        task1 = svc._task
        await svc.start()  # should not create a second task
        assert svc._task is task1
        await svc.stop()


class TestBypassSuppressHeartbeat:
    def test_bypass_strategy_suppresses_heartbeat(self):
        from csp_lib.controller.strategies import BypassStrategy

        strategy = BypassStrategy()
        assert strategy.suppress_heartbeat is True

    def test_default_strategy_does_not_suppress(self):
        from csp_lib.controller.strategies import PQModeStrategy, StopStrategy

        assert PQModeStrategy().suppress_heartbeat is False
        assert StopStrategy().suppress_heartbeat is False
