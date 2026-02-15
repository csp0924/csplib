"""Tests for DeviceDataFeed."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from csp_lib.equipment.device.events import EVENT_READ_COMPLETE, ReadCompletePayload
from csp_lib.integration.data_feed import DeviceDataFeed
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import DataFeedMapping


def _make_device(device_id: str, responsive: bool = True) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    unsub_fn = MagicMock()
    dev.on = MagicMock(return_value=unsub_fn)
    dev._unsub_fn = unsub_fn
    return dev


def _make_pv_service() -> MagicMock:
    svc = MagicMock()
    svc.append = MagicMock()
    return svc


class TestDeviceDataFeedAttachDetach:
    def test_attach_device_id_mode(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)
        feed.attach()

        dev.on.assert_called_once_with(EVENT_READ_COMPLETE, feed._on_read_complete)

    def test_attach_trait_mode(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev, traits=["meter"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="meter"), pv)
        feed.attach()

        dev.on.assert_called_once_with(EVENT_READ_COMPLETE, feed._on_read_complete)

    def test_attach_no_device_found(self):
        reg = DeviceRegistry()
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="missing"), pv)
        feed.attach()  # should not raise, just log warning

    def test_detach(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)
        feed.attach()
        feed.detach()

        dev._unsub_fn.assert_called_once()

    def test_detach_without_attach(self):
        reg = DeviceRegistry()
        pv = _make_pv_service()
        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="d1"), pv)
        feed.detach()  # should not raise


class TestDeviceDataFeedOnReadComplete:
    @pytest.mark.asyncio
    async def test_numeric_value_appended(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)

        payload = ReadCompletePayload(device_id="meter1", values={"pv_power": 1500.5}, duration_ms=10.0)
        await feed._on_read_complete(payload)

        pv.append.assert_called_once_with(1500.5)

    @pytest.mark.asyncio
    async def test_int_value_converted_to_float(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)

        payload = ReadCompletePayload(device_id="meter1", values={"pv_power": 1500}, duration_ms=10.0)
        await feed._on_read_complete(payload)

        pv.append.assert_called_once_with(1500.0)

    @pytest.mark.asyncio
    async def test_non_numeric_value_appends_none(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)

        payload = ReadCompletePayload(device_id="meter1", values={"pv_power": "bad"}, duration_ms=10.0)
        await feed._on_read_complete(payload)

        pv.append.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_missing_point_appends_none(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)

        payload = ReadCompletePayload(device_id="meter1", values={}, duration_ms=10.0)
        await feed._on_read_complete(payload)

        pv.append.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_trait_resolves_first_responsive(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=False)
        d2 = _make_device("d2", responsive=True)
        reg.register(d1, traits=["meter"])
        reg.register(d2, traits=["meter"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="meter"), pv)
        feed.attach()

        # Should have subscribed to d2 (first responsive)
        d2.on.assert_called_once_with(EVENT_READ_COMPLETE, feed._on_read_complete)
        d1.on.assert_not_called()
