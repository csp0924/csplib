"""Tests for DeviceDataFeed."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from csp_lib.equipment.device.events import EVENT_READ_COMPLETE, ReadCompletePayload
from csp_lib.integration.data_feed import DeviceDataFeed
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import AggregateFunc, DataFeedMapping


def _make_device(device_id: str, responsive: bool = True, latest_values: dict | None = None) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).latest_values = PropertyMock(return_value=latest_values or {})
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

    def test_attach_trait_subscribes_all_devices(self):
        """trait 模式應訂閱所有匹配設備（含非 responsive）"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=False)
        d2 = _make_device("d2", responsive=True)
        d3 = _make_device("d3", responsive=True)
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        reg.register(d3, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv", aggregate=AggregateFunc.SUM), pv)
        feed.attach()

        d1.on.assert_called_once_with(EVENT_READ_COMPLETE, feed._on_read_complete)
        d2.on.assert_called_once_with(EVENT_READ_COMPLETE, feed._on_read_complete)
        d3.on.assert_called_once_with(EVENT_READ_COMPLETE, feed._on_read_complete)

    def test_attach_no_device_found(self):
        reg = DeviceRegistry()
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="missing"), pv)
        feed.attach()  # should not raise, just log warning

    def test_attach_trait_no_devices(self):
        reg = DeviceRegistry()
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="missing"), pv)
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

    def test_detach_trait_unsubscribes_all(self):
        """detach 應取消所有設備的訂閱"""
        reg = DeviceRegistry()
        d1 = _make_device("d1")
        d2 = _make_device("d2")
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv"), pv)
        feed.attach()
        feed.detach()

        d1._unsub_fn.assert_called_once()
        d2._unsub_fn.assert_called_once()

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


class TestDeviceDataFeedTraitAggregate:
    @pytest.mark.asyncio
    async def test_sum_aggregate(self):
        """SUM 聚合：加總所有 responsive 設備的值"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True, latest_values={"pv_power": 500.0})
        d2 = _make_device("d2", responsive=True, latest_values={"pv_power": 300.0})
        d3 = _make_device("d3", responsive=True, latest_values={"pv_power": 200.0})
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        reg.register(d3, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv", aggregate=AggregateFunc.SUM), pv)

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 500.0}, duration_ms=10.0)
        await feed._on_read_complete(payload)

        pv.append.assert_called_once_with(1000.0)

    @pytest.mark.asyncio
    async def test_sum_excludes_unresponsive(self):
        """SUM 聚合：排除 unresponsive 設備"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True, latest_values={"pv_power": 500.0})
        d2 = _make_device("d2", responsive=False, latest_values={"pv_power": 300.0})
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv", aggregate=AggregateFunc.SUM), pv)

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 500.0}, duration_ms=10.0)
        await feed._on_read_complete(payload)

        pv.append.assert_called_once_with(500.0)

    @pytest.mark.asyncio
    async def test_sum_all_unresponsive_appends_none(self):
        """所有設備皆 unresponsive 時 append None"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=False, latest_values={"pv_power": 500.0})
        reg.register(d1, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv", aggregate=AggregateFunc.SUM), pv)

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 500.0}, duration_ms=10.0)
        await feed._on_read_complete(payload)

        pv.append.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_first_aggregate_default(self):
        """預設 FIRST 聚合：取排序後第一台 responsive 設備的值"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True, latest_values={"pv_power": 500.0})
        d2 = _make_device("d2", responsive=True, latest_values={"pv_power": 300.0})
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv"), pv)

        payload = ReadCompletePayload(device_id="d2", values={"pv_power": 300.0}, duration_ms=10.0)
        await feed._on_read_complete(payload)

        pv.append.assert_called_once_with(500.0)  # d1 is first sorted by device_id

    @pytest.mark.asyncio
    async def test_average_aggregate(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True, latest_values={"pv_power": 400.0})
        d2 = _make_device("d2", responsive=True, latest_values={"pv_power": 600.0})
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(
            reg, DataFeedMapping(point_name="pv_power", trait="pv", aggregate=AggregateFunc.AVERAGE), pv
        )

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 400.0}, duration_ms=10.0)
        await feed._on_read_complete(payload)

        pv.append.assert_called_once_with(500.0)

    @pytest.mark.asyncio
    async def test_sum_skips_none_values(self):
        """設備 responsive 但點位值為 None 時跳過"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True, latest_values={"pv_power": 500.0})
        d2 = _make_device("d2", responsive=True, latest_values={})  # point missing
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv", aggregate=AggregateFunc.SUM), pv)

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 500.0}, duration_ms=10.0)
        await feed._on_read_complete(payload)

        pv.append.assert_called_once_with(500.0)

    @pytest.mark.asyncio
    async def test_sum_int_values_converted_to_float(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True, latest_values={"pv_power": 500})
        d2 = _make_device("d2", responsive=True, latest_values={"pv_power": 300})
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv", aggregate=AggregateFunc.SUM), pv)

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 500}, duration_ms=10.0)
        await feed._on_read_complete(payload)

        pv.append.assert_called_once_with(800.0)
