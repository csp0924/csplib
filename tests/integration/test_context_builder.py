"""Tests for ContextBuilder."""

from unittest.mock import MagicMock, PropertyMock

from csp_lib.controller.core import SystemBase
from csp_lib.integration.context_builder import ContextBuilder, _apply_builtin_aggregate
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import AggregateFunc, ContextMapping


def _make_device(device_id: str, values: dict | None = None, responsive: bool = True) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).latest_values = PropertyMock(return_value=values or {})
    return dev


class TestApplyBuiltinAggregate:
    def test_average(self):
        assert _apply_builtin_aggregate(AggregateFunc.AVERAGE, [10, 20, 30]) == 20.0

    def test_sum(self):
        assert _apply_builtin_aggregate(AggregateFunc.SUM, [10, 20, 30]) == 60

    def test_min(self):
        assert _apply_builtin_aggregate(AggregateFunc.MIN, [10, 5, 30]) == 5

    def test_max(self):
        assert _apply_builtin_aggregate(AggregateFunc.MAX, [10, 5, 30]) == 30

    def test_first(self):
        assert _apply_builtin_aggregate(AggregateFunc.FIRST, [10, 20]) == 10

    def test_empty_returns_none(self):
        assert _apply_builtin_aggregate(AggregateFunc.AVERAGE, []) is None


class TestContextBuilderDeviceIdMode:
    def test_single_device_read(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", {"soc": 85.0})
        reg.register(dev)

        builder = ContextBuilder(reg, [ContextMapping(point_name="soc", context_field="soc", device_id="d1")])
        ctx = builder.build()
        assert ctx.soc == 85.0

    def test_device_not_found_returns_default(self):
        reg = DeviceRegistry()
        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", device_id="missing", default=50.0)],
        )
        ctx = builder.build()
        assert ctx.soc == 50.0

    def test_device_not_responsive_returns_default(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", {"soc": 85.0}, responsive=False)
        reg.register(dev)

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", device_id="d1", default=0.0)],
        )
        ctx = builder.build()
        assert ctx.soc == 0.0

    def test_point_missing_returns_default(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", {})
        reg.register(dev)

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", device_id="d1", default=-1.0)],
        )
        ctx = builder.build()
        assert ctx.soc == -1.0

    def test_extra_field(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", {"grid_power": 1500.0})
        reg.register(dev)

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="grid_power", context_field="extra.grid_power", device_id="d1")],
        )
        ctx = builder.build()
        assert ctx.extra["grid_power"] == 1500.0

    def test_transform(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", {"soc": 0.85})
        reg.register(dev)

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", device_id="d1", transform=lambda v: v * 100)],
        )
        ctx = builder.build()
        assert ctx.soc == 85.0

    def test_transform_exception_returns_default(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", {"soc": "bad"})
        reg.register(dev)

        def bad_transform(v):
            raise ValueError("oops")

        builder = ContextBuilder(
            reg,
            [
                ContextMapping(
                    point_name="soc", context_field="soc", device_id="d1", transform=bad_transform, default=0.0
                )
            ],
        )
        ctx = builder.build()
        assert ctx.soc == 0.0


class TestContextBuilderTraitMode:
    def test_average_aggregate(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"soc": 80.0})
        d2 = _make_device("d2", {"soc": 90.0})
        reg.register(d1, traits=["bms"])
        reg.register(d2, traits=["bms"])

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", trait="bms", aggregate=AggregateFunc.AVERAGE)],
        )
        ctx = builder.build()
        assert ctx.soc == 85.0

    def test_sum_aggregate(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"power": 100.0})
        d2 = _make_device("d2", {"power": 200.0})
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        builder = ContextBuilder(
            reg,
            [
                ContextMapping(
                    point_name="power",
                    context_field="extra.total_power",
                    trait="pcs",
                    aggregate=AggregateFunc.SUM,
                )
            ],
        )
        ctx = builder.build()
        assert ctx.extra["total_power"] == 300.0

    def test_min_aggregate(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"cell_v": 3.2})
        d2 = _make_device("d2", {"cell_v": 3.1})
        reg.register(d1, traits=["bms"])
        reg.register(d2, traits=["bms"])

        builder = ContextBuilder(
            reg,
            [
                ContextMapping(
                    point_name="cell_v",
                    context_field="extra.min_cell_v",
                    trait="bms",
                    aggregate=AggregateFunc.MIN,
                )
            ],
        )
        ctx = builder.build()
        assert ctx.extra["min_cell_v"] == 3.1

    def test_max_aggregate(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"temp": 35.0})
        d2 = _make_device("d2", {"temp": 42.0})
        reg.register(d1, traits=["bms"])
        reg.register(d2, traits=["bms"])

        builder = ContextBuilder(
            reg,
            [
                ContextMapping(
                    point_name="temp", context_field="extra.max_temp", trait="bms", aggregate=AggregateFunc.MAX
                )
            ],
        )
        ctx = builder.build()
        assert ctx.extra["max_temp"] == 42.0

    def test_first_aggregate(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"status": 1})
        d2 = _make_device("d2", {"status": 2})
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        builder = ContextBuilder(
            reg,
            [
                ContextMapping(
                    point_name="status",
                    context_field="extra.status",
                    trait="pcs",
                    aggregate=AggregateFunc.FIRST,
                )
            ],
        )
        ctx = builder.build()
        assert ctx.extra["status"] == 1  # d1 is first (sorted by device_id)

    def test_custom_aggregate(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"soc": 80.0})
        d2 = _make_device("d2", {"soc": 90.0})
        reg.register(d1, traits=["bms"])
        reg.register(d2, traits=["bms"])

        custom_fn = lambda vs: max(vs) - min(vs)  # noqa: E731

        builder = ContextBuilder(
            reg,
            [
                ContextMapping(
                    point_name="soc",
                    context_field="extra.soc_range",
                    trait="bms",
                    custom_aggregate=custom_fn,
                )
            ],
        )
        ctx = builder.build()
        assert ctx.extra["soc_range"] == 10.0

    def test_custom_aggregate_exception_returns_default(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"soc": 80.0})
        reg.register(d1, traits=["bms"])

        def bad_agg(vs):
            raise RuntimeError("boom")

        builder = ContextBuilder(
            reg,
            [
                ContextMapping(
                    point_name="soc",
                    context_field="soc",
                    trait="bms",
                    custom_aggregate=bad_agg,
                    default=50.0,
                )
            ],
        )
        ctx = builder.build()
        assert ctx.soc == 50.0

    def test_no_responsive_devices_returns_default(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"soc": 80.0}, responsive=False)
        reg.register(d1, traits=["bms"])

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", trait="bms", default=0.0)],
        )
        ctx = builder.build()
        assert ctx.soc == 0.0

    def test_partial_none_values_filtered(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"soc": 80.0})
        d2 = _make_device("d2", {})  # point missing → None
        reg.register(d1, traits=["bms"])
        reg.register(d2, traits=["bms"])

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", trait="bms", aggregate=AggregateFunc.AVERAGE)],
        )
        ctx = builder.build()
        assert ctx.soc == 80.0  # only d1's value

    def test_all_none_returns_default(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", {})
        d2 = _make_device("d2", {})
        reg.register(d1, traits=["bms"])
        reg.register(d2, traits=["bms"])

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", trait="bms", default=-1.0)],
        )
        ctx = builder.build()
        assert ctx.soc == -1.0


class TestContextBuilderSystemBase:
    def test_system_base_set(self):
        reg = DeviceRegistry()
        sb = SystemBase(p_base=2000, q_base=1000)
        builder = ContextBuilder(reg, [], system_base=sb)
        ctx = builder.build()
        assert ctx.system_base is sb

    def test_system_base_none(self):
        reg = DeviceRegistry()
        builder = ContextBuilder(reg, [])
        ctx = builder.build()
        assert ctx.system_base is None
