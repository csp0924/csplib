"""DeviceDataFeed 測試。

v0.9.x 起 DeviceDataFeed 移除 private ``_on_read_complete``，改以 per-(key, mapping)
closure handler 訂閱設備事件。測試改為：
- 透過 ``dev.on`` 的 mock call_args 取回實際註冊的 handler
- 呼叫該 handler 驗證對應 buffer 被正確 append
- 同時驗證新舊建構 API 的相容性
"""

from unittest.mock import MagicMock, PropertyMock

import pytest

from csp_lib.controller.services import HistoryBuffer
from csp_lib.equipment.device.events import EVENT_READ_COMPLETE, ReadCompletePayload
from csp_lib.integration.data_feed import DeviceDataFeed
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import AggregateFunc, DataFeedMapping


def _make_device(device_id: str, responsive: bool = True, latest_values: dict | None = None) -> MagicMock:
    """建立 device mock，dev.on 回傳可驗證的 unsub callable"""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).latest_values = PropertyMock(return_value=latest_values or {})
    unsub_fn = MagicMock()
    dev.on = MagicMock(return_value=unsub_fn)
    dev._unsub_fn = unsub_fn
    return dev


def _make_pv_service() -> MagicMock:
    """legacy-style PVDataService / HistoryBuffer mock"""
    svc = MagicMock()
    svc.append = MagicMock()
    return svc


def _registered_handlers(dev: MagicMock) -> list:
    """從 dev.on 的 call_args_list 取出所有被註冊的 handler"""
    return [call.args[1] for call in dev.on.call_args_list if call.args[0] == EVENT_READ_COMPLETE]


class TestDeviceDataFeedAttachDetach:
    def test_attach_device_id_mode(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)
        feed.attach()

        # 應註冊了一個 read_complete handler；handler 為 per-(key, mapping) closure
        assert dev.on.call_count == 1
        event_name, handler = dev.on.call_args.args
        assert event_name == EVENT_READ_COMPLETE
        assert callable(handler)

    def test_attach_trait_mode(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev, traits=["meter"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="meter"), pv)
        feed.attach()

        assert dev.on.call_count == 1
        event_name, handler = dev.on.call_args.args
        assert event_name == EVENT_READ_COMPLETE
        assert callable(handler)

    def test_attach_trait_subscribes_all_devices(self):
        """trait 模式應訂閱所有匹配設備（含非 responsive）且共用同一 handler closure"""
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

        # 三台設備各被呼叫一次 dev.on，event 必為 EVENT_READ_COMPLETE
        for dev in (d1, d2, d3):
            assert dev.on.call_count == 1
            assert dev.on.call_args.args[0] == EVENT_READ_COMPLETE
            assert callable(dev.on.call_args.args[1])

        # 同一 trait mapping 內所有設備共用同一個 handler closure
        handlers = {id(_registered_handlers(d)[0]) for d in (d1, d2, d3)}
        assert len(handlers) == 1

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


class TestDeviceDataFeedDeviceIdHandler:
    """透過 attach() 取得實際註冊的 handler，呼叫驗證行為（取代舊 _on_read_complete）"""

    async def test_numeric_value_appended(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)
        feed.attach()
        handler = _registered_handlers(dev)[0]

        payload = ReadCompletePayload(device_id="meter1", values={"pv_power": 1500.5}, duration_ms=10.0)
        await handler(payload)

        pv.append.assert_called_once_with(1500.5)

    async def test_int_value_converted_to_float(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)
        feed.attach()
        handler = _registered_handlers(dev)[0]

        payload = ReadCompletePayload(device_id="meter1", values={"pv_power": 1500}, duration_ms=10.0)
        await handler(payload)

        pv.append.assert_called_once_with(1500.0)

    async def test_non_numeric_value_appends_none(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)
        feed.attach()
        handler = _registered_handlers(dev)[0]

        payload = ReadCompletePayload(device_id="meter1", values={"pv_power": "bad"}, duration_ms=10.0)
        await handler(payload)

        pv.append.assert_called_once_with(None)

    async def test_missing_point_appends_none(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)
        feed.attach()
        handler = _registered_handlers(dev)[0]

        payload = ReadCompletePayload(device_id="meter1", values={}, duration_ms=10.0)
        await handler(payload)

        pv.append.assert_called_once_with(None)


class TestDeviceDataFeedTraitAggregate:
    """trait 模式聚合：取 attach 後註冊的 handler 呼叫驗證"""

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
        feed.attach()
        handler = _registered_handlers(d1)[0]

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 500.0}, duration_ms=10.0)
        await handler(payload)

        pv.append.assert_called_once_with(1000.0)

    async def test_sum_excludes_unresponsive(self):
        """SUM 聚合：排除 unresponsive 設備"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True, latest_values={"pv_power": 500.0})
        d2 = _make_device("d2", responsive=False, latest_values={"pv_power": 300.0})
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv", aggregate=AggregateFunc.SUM), pv)
        feed.attach()
        handler = _registered_handlers(d1)[0]

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 500.0}, duration_ms=10.0)
        await handler(payload)

        pv.append.assert_called_once_with(500.0)

    async def test_sum_all_unresponsive_appends_none(self):
        """所有設備皆 unresponsive 時 append None"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=False, latest_values={"pv_power": 500.0})
        reg.register(d1, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv", aggregate=AggregateFunc.SUM), pv)
        feed.attach()
        handler = _registered_handlers(d1)[0]

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 500.0}, duration_ms=10.0)
        await handler(payload)

        pv.append.assert_called_once_with(None)

    async def test_first_aggregate_default(self):
        """預設 FIRST 聚合：取排序後第一台 responsive 設備的值"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True, latest_values={"pv_power": 500.0})
        d2 = _make_device("d2", responsive=True, latest_values={"pv_power": 300.0})
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv"), pv)
        feed.attach()
        # d1 / d2 共用同一 closure handler，取任一即可
        handler = _registered_handlers(d2)[0]

        payload = ReadCompletePayload(device_id="d2", values={"pv_power": 300.0}, duration_ms=10.0)
        await handler(payload)

        pv.append.assert_called_once_with(500.0)  # d1 is first sorted by device_id

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
        feed.attach()
        handler = _registered_handlers(d1)[0]

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 400.0}, duration_ms=10.0)
        await handler(payload)

        pv.append.assert_called_once_with(500.0)

    async def test_sum_skips_none_values(self):
        """設備 responsive 但點位值缺失時跳過"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True, latest_values={"pv_power": 500.0})
        d2 = _make_device("d2", responsive=True, latest_values={})  # point missing
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv", aggregate=AggregateFunc.SUM), pv)
        feed.attach()
        handler = _registered_handlers(d1)[0]

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 500.0}, duration_ms=10.0)
        await handler(payload)

        pv.append.assert_called_once_with(500.0)

    async def test_sum_int_values_converted_to_float(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True, latest_values={"pv_power": 500})
        d2 = _make_device("d2", responsive=True, latest_values={"pv_power": 300})
        reg.register(d1, traits=["pv"])
        reg.register(d2, traits=["pv"])
        pv = _make_pv_service()

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", trait="pv", aggregate=AggregateFunc.SUM), pv)
        feed.attach()
        handler = _registered_handlers(d1)[0]

        payload = ReadCompletePayload(device_id="d1", values={"pv_power": 500}, duration_ms=10.0)
        await handler(payload)

        pv.append.assert_called_once_with(800.0)


class TestDeviceDataFeedLegacyNormalization:
    """驗證 legacy 建構 API 被正規化到 dict-based 內部表達 + accessor 相容性"""

    def test_legacy_ctor_normalized_to_pv_power_key(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv_buf = HistoryBuffer(max_history=10)

        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv_buf)

        # get_buffer("pv_power") 應回傳同一物件
        assert feed.get_buffer("pv_power") is pv_buf
        # buffers property 含 "pv_power" key
        assert "pv_power" in feed.buffers
        assert feed.buffers["pv_power"] is pv_buf
        # pv_service property（legacy）也能取到同 buffer
        assert feed.pv_service is pv_buf

    def test_get_buffer_missing_key_returns_none(self):
        reg = DeviceRegistry()
        pv = _make_pv_service()
        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv)

        assert feed.get_buffer("grid_power") is None

    def test_buffers_property_is_readonly_view(self):
        """buffers property 回傳 MappingProxyType 唯讀視圖，caller 無法修改。"""
        reg = DeviceRegistry()
        pv_buf = HistoryBuffer(max_history=10)
        feed = DeviceDataFeed(reg, DataFeedMapping(point_name="pv_power", device_id="meter1"), pv_buf)

        snapshot = feed.buffers
        with pytest.raises(TypeError):
            snapshot["foo"] = HistoryBuffer()  # type: ignore[index]
        assert "foo" not in feed.buffers
        assert feed.get_buffer("foo") is None


class TestDeviceDataFeedMultiSource:
    """v0.9.x+ 新 API：多來源 mappings + history_buffers"""

    def test_multi_buffer_construction(self):
        reg = DeviceRegistry()
        pv_buf = HistoryBuffer(max_history=10)
        grid_buf = HistoryBuffer(max_history=20)

        feed = DeviceDataFeed(
            reg,
            mappings={
                "pv_power": DataFeedMapping(point_name="pv_power", device_id="meter1"),
                "grid_power": DataFeedMapping(point_name="grid_power", device_id="meter2"),
            },
            history_buffers={"pv_power": pv_buf, "grid_power": grid_buf},
        )

        assert feed.get_buffer("pv_power") is pv_buf
        assert feed.get_buffer("grid_power") is grid_buf
        assert set(feed.buffers.keys()) == {"pv_power", "grid_power"}

    async def test_multi_buffer_isolation(self):
        """一個設備的 read_complete 只更新其對應 key 的 buffer，不污染其他 key"""
        reg = DeviceRegistry()
        meter1 = _make_device("meter1")
        meter2 = _make_device("meter2")
        reg.register(meter1)
        reg.register(meter2)

        pv_buf = HistoryBuffer(max_history=10)
        grid_buf = HistoryBuffer(max_history=10)

        feed = DeviceDataFeed(
            reg,
            mappings={
                "pv_power": DataFeedMapping(point_name="pv_power", device_id="meter1"),
                "grid_power": DataFeedMapping(point_name="grid_power", device_id="meter2"),
            },
            history_buffers={"pv_power": pv_buf, "grid_power": grid_buf},
        )
        feed.attach()

        meter1_handler = _registered_handlers(meter1)[0]
        meter2_handler = _registered_handlers(meter2)[0]

        # meter1 的 read_complete 應只餵 pv_power buffer
        await meter1_handler(ReadCompletePayload(device_id="meter1", values={"pv_power": 500.0}, duration_ms=1.0))
        assert pv_buf.get_latest() == 500.0
        assert grid_buf.get_latest() is None

        # meter2 的 read_complete 應只餵 grid_power buffer
        await meter2_handler(ReadCompletePayload(device_id="meter2", values={"grid_power": 1200.0}, duration_ms=1.0))
        assert pv_buf.get_latest() == 500.0  # 不受影響
        assert grid_buf.get_latest() == 1200.0

    def test_mapping_without_buffer_is_skipped(self):
        """mapping 對應的 key 若沒配 buffer，attach 應 log warning 並跳過（不 raise）"""
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)
        pv_buf = HistoryBuffer()

        feed = DeviceDataFeed(
            reg,
            mappings={
                "pv_power": DataFeedMapping(point_name="pv_power", device_id="meter1"),
                "grid_power": DataFeedMapping(point_name="grid_power", device_id="meter1"),
            },
            history_buffers={"pv_power": pv_buf},
        )
        feed.attach()

        # grid_power 無對應 buffer，不應註冊 handler；只應有一次 pv_power 的訂閱
        assert dev.on.call_count == 1


class TestDeviceDataFeedConstructorConflicts:
    """新舊 API 混用必須 raise ValueError（bug-validation-fail-loud 原則）"""

    def test_mix_pv_service_and_history_buffers_raises(self):
        reg = DeviceRegistry()
        pv = _make_pv_service()
        with pytest.raises(ValueError, match="cannot mix"):
            DeviceDataFeed(
                reg,
                DataFeedMapping(point_name="pv_power", device_id="m1"),
                pv,
                history_buffers={"pv_power": HistoryBuffer()},
            )

    def test_mix_mapping_and_mappings_raises(self):
        reg = DeviceRegistry()
        with pytest.raises(ValueError, match="cannot mix"):
            DeviceDataFeed(
                reg,
                DataFeedMapping(point_name="pv_power", device_id="m1"),
                mappings={"pv_power": DataFeedMapping(point_name="pv_power", device_id="m1")},
            )

    def test_mix_mapping_and_history_buffers_raises(self):
        """只傳 legacy mapping + 新 history_buffers 也算混用"""
        reg = DeviceRegistry()
        with pytest.raises(ValueError, match="cannot mix"):
            DeviceDataFeed(
                reg,
                DataFeedMapping(point_name="pv_power", device_id="m1"),
                history_buffers={"pv_power": HistoryBuffer()},
            )

    def test_mix_pv_service_and_mappings_raises(self):
        """只傳 legacy pv_service + 新 mappings 也算混用"""
        reg = DeviceRegistry()
        pv = _make_pv_service()
        with pytest.raises(ValueError, match="cannot mix"):
            DeviceDataFeed(
                reg,
                None,
                pv,
                mappings={"pv_power": DataFeedMapping(point_name="pv_power", device_id="m1")},
            )
