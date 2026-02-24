from unittest.mock import MagicMock

from csp_lib.integration.context_builder import ContextBuilder
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import ContextMapping


def _make_device(device_id, values=None, responsive=True):
    d = MagicMock()
    d.device_id = device_id
    d.is_responsive = responsive
    d.latest_values = values or {}
    return d


class TestContextBuilderEdgeCases:
    def test_empty_registry_produces_defaults(self):
        registry = DeviceRegistry()
        mapping = ContextMapping(
            point_name="voltage",
            context_field="extra.voltage",
            device_id="dev1",
            default=380.0,
        )
        builder = ContextBuilder(registry, [mapping])
        ctx = builder.build()
        assert ctx.extra["voltage"] == 380.0

    def test_transform_failure_uses_default(self):
        registry = DeviceRegistry()
        device = _make_device("dev1", values={"voltage": 400})
        registry.register(device)
        mapping = ContextMapping(
            point_name="voltage",
            context_field="extra.voltage",
            device_id="dev1",
            default=380.0,
            transform=lambda x: 1 / 0,  # raises ZeroDivisionError
        )
        builder = ContextBuilder(registry, [mapping])
        ctx = builder.build()
        assert ctx.extra["voltage"] == 380.0

    def test_custom_aggregate_failure_returns_default(self):
        registry = DeviceRegistry()
        device = _make_device("dev1", values={"power": 100})
        registry.register(device, traits=["pcs"])
        mapping = ContextMapping(
            point_name="power",
            context_field="extra.power",
            trait="pcs",
            default=0.0,
            custom_aggregate=lambda vals: 1 / 0,  # raises ZeroDivisionError
        )
        builder = ContextBuilder(registry, [mapping])
        ctx = builder.build()
        assert ctx.extra["power"] == 0.0

    def test_all_values_none_returns_default(self):
        registry = DeviceRegistry()
        device = _make_device("dev1", values={"voltage": None})
        registry.register(device, traits=["meter"])
        mapping = ContextMapping(
            point_name="voltage",
            context_field="extra.voltage",
            trait="meter",
            default=380.0,
        )
        builder = ContextBuilder(registry, [mapping])
        ctx = builder.build()
        assert ctx.extra["voltage"] == 380.0

    def test_no_responsive_devices_returns_default(self):
        registry = DeviceRegistry()
        device = _make_device("dev1", values={"v": 100}, responsive=False)
        registry.register(device)
        mapping = ContextMapping(
            point_name="v",
            context_field="extra.v",
            device_id="dev1",
            default=0.0,
        )
        builder = ContextBuilder(registry, [mapping])
        ctx = builder.build()
        assert ctx.extra["v"] == 0.0
