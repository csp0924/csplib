"""Tests for VirtualContextBuilder."""

from unittest.mock import MagicMock

from csp_lib.cluster.context import VirtualContextBuilder
from csp_lib.cluster.sync import ClusterStateSubscriber
from csp_lib.controller.core import SystemBase
from csp_lib.integration.schema import AggregateFunc, ContextMapping


def _make_subscriber(device_states: dict) -> MagicMock:
    """建立 mock subscriber"""
    sub = MagicMock(spec=ClusterStateSubscriber)
    sub.device_states = device_states
    return sub


class TestVirtualContextBuilderDeviceMode:
    def test_single_device_mapping(self):
        """device_id 模式：從快取讀取設備值"""
        sub = _make_subscriber({
            "meter-1": {"active_power": 100.0, "voltage": 220.0},
        })
        mappings = [
            ContextMapping(point_name="active_power", context_field="extra.meter_power", device_id="meter-1"),
        ]
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings)
        ctx = builder.build()
        assert ctx.extra["meter_power"] == 100.0

    def test_device_not_in_cache_uses_default(self):
        """設備不在快取中應使用預設值"""
        sub = _make_subscriber({})
        mappings = [
            ContextMapping(
                point_name="active_power",
                context_field="extra.meter_power",
                device_id="meter-1",
                default=-1.0,
            ),
        ]
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings)
        ctx = builder.build()
        assert ctx.extra["meter_power"] == -1.0

    def test_point_not_in_device_state_uses_default(self):
        """點位不在設備狀態中應使用預設值"""
        sub = _make_subscriber({
            "meter-1": {"voltage": 220.0},
        })
        mappings = [
            ContextMapping(
                point_name="active_power",
                context_field="extra.meter_power",
                device_id="meter-1",
                default=0.0,
            ),
        ]
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings)
        ctx = builder.build()
        assert ctx.extra["meter_power"] == 0.0

    def test_maps_to_context_field(self):
        """應正確設定 context 欄位"""
        sub = _make_subscriber({
            "pcs-1": {"soc": 75.0},
        })
        mappings = [
            ContextMapping(point_name="soc", context_field="soc", device_id="pcs-1"),
        ]
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings)
        ctx = builder.build()
        assert ctx.soc == 75.0

    def test_transform_applied(self):
        """應套用 transform 函式"""
        sub = _make_subscriber({
            "meter-1": {"active_power": 1000.0},
        })
        mappings = [
            ContextMapping(
                point_name="active_power",
                context_field="extra.meter_kw",
                device_id="meter-1",
                transform=lambda v: v / 1000.0,  # W to kW
            ),
        ]
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings)
        ctx = builder.build()
        assert ctx.extra["meter_kw"] == 1.0

    def test_transform_failure_uses_default(self):
        """Transform 失敗應使用預設值"""
        sub = _make_subscriber({
            "meter-1": {"active_power": "invalid"},
        })
        mappings = [
            ContextMapping(
                point_name="active_power",
                context_field="extra.meter_power",
                device_id="meter-1",
                transform=lambda v: v / 1000.0,
                default=-1.0,
            ),
        ]
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings)
        ctx = builder.build()
        assert ctx.extra["meter_power"] == -1.0


class TestVirtualContextBuilderTraitMode:
    def test_trait_aggregate_sum(self):
        """trait 模式：SUM 聚合"""
        sub = _make_subscriber({
            "pcs-1": {"p_target": 50.0},
            "pcs-2": {"p_target": 30.0},
        })
        mappings = [
            ContextMapping(
                point_name="p_target",
                context_field="extra.total_p",
                trait="pcs",
                aggregate=AggregateFunc.SUM,
            ),
        ]
        trait_map = {"pcs": ["pcs-1", "pcs-2"]}
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings, trait_device_map=trait_map)
        ctx = builder.build()
        assert ctx.extra["total_p"] == 80.0

    def test_trait_aggregate_average(self):
        """trait 模式：AVERAGE 聚合"""
        sub = _make_subscriber({
            "pcs-1": {"soc": 60.0},
            "pcs-2": {"soc": 80.0},
        })
        mappings = [
            ContextMapping(
                point_name="soc",
                context_field="soc",
                trait="pcs",
                aggregate=AggregateFunc.AVERAGE,
            ),
        ]
        trait_map = {"pcs": ["pcs-1", "pcs-2"]}
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings, trait_device_map=trait_map)
        ctx = builder.build()
        assert ctx.soc == 70.0

    def test_trait_no_devices_uses_default(self):
        """trait 無設備時使用預設值"""
        sub = _make_subscriber({})
        mappings = [
            ContextMapping(
                point_name="soc",
                context_field="soc",
                trait="pcs",
                default=50.0,
            ),
        ]
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings, trait_device_map={})
        ctx = builder.build()
        assert ctx.soc == 50.0

    def test_trait_partial_data(self):
        """部分設備有值時應聚合可用資料"""
        sub = _make_subscriber({
            "pcs-1": {"soc": 60.0},
            "pcs-2": {},  # soc not available
        })
        mappings = [
            ContextMapping(
                point_name="soc",
                context_field="soc",
                trait="pcs",
                aggregate=AggregateFunc.AVERAGE,
            ),
        ]
        trait_map = {"pcs": ["pcs-1", "pcs-2"]}
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings, trait_device_map=trait_map)
        ctx = builder.build()
        assert ctx.soc == 60.0

    def test_custom_aggregate(self):
        """應支援自訂聚合函式"""
        sub = _make_subscriber({
            "pcs-1": {"soc": 60.0},
            "pcs-2": {"soc": 80.0},
        })
        mappings = [
            ContextMapping(
                point_name="soc",
                context_field="soc",
                trait="pcs",
                custom_aggregate=lambda values: min(values),
            ),
        ]
        trait_map = {"pcs": ["pcs-1", "pcs-2"]}
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings, trait_device_map=trait_map)
        ctx = builder.build()
        assert ctx.soc == 60.0


class TestVirtualContextBuilderSystemBase:
    def test_system_base_set(self):
        """應設定 system_base"""
        sub = _make_subscriber({})
        base = SystemBase(p_base=500.0, q_base=200.0)
        builder = VirtualContextBuilder(subscriber=sub, mappings=[], system_base=base)
        ctx = builder.build()
        assert ctx.system_base is not None
        assert ctx.system_base.p_base == 500.0

    def test_system_base_none(self):
        """system_base 未設定時應為 None"""
        sub = _make_subscriber({})
        builder = VirtualContextBuilder(subscriber=sub, mappings=[])
        ctx = builder.build()
        assert ctx.system_base is None


class TestVirtualContextBuilderMultipleMappings:
    def test_multiple_mappings(self):
        """多個映射應同時生效"""
        sub = _make_subscriber({
            "meter-1": {"active_power": 100.0},
            "pcs-1": {"soc": 75.0},
        })
        mappings = [
            ContextMapping(point_name="active_power", context_field="extra.meter_power", device_id="meter-1"),
            ContextMapping(point_name="soc", context_field="soc", device_id="pcs-1"),
        ]
        builder = VirtualContextBuilder(subscriber=sub, mappings=mappings)
        ctx = builder.build()
        assert ctx.extra["meter_power"] == 100.0
        assert ctx.soc == 75.0
