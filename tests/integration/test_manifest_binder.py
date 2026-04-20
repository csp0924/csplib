# =============== Manifest Binder Tests ===============
#
# 驗證 apply_manifest_to_builder：
#   - devices / strategies kind 解析到 class（BoundDeviceSpec / BoundStrategySpec）
#   - 未知 device / strategy kind → ConfigurationError（訊息含 device/strategy name）
#   - CommandRefresh reconciler spec → 直接呼叫 builder.command_refresh(**config)
#   - 未知 reconciler kind → 保留在 unbound_reconcilers
#   - reconciler config 不合法 kwargs → ConfigurationError
#   - ManifestBindResult 是 frozen

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.integration.manifest import (
    DeviceSpec,
    ManifestMetadata,
    ReconcilerSpec,
    SiteManifest,
    SiteSpec,
    StrategySpec,
)
from csp_lib.integration.manifest_binder import (
    BoundDeviceSpec,
    BoundReconcilerSpec,
    BoundStrategySpec,
    ManifestBindResult,
    apply_manifest_to_builder,
)
from csp_lib.integration.type_registry import TypeRegistry

# ─────────────── Helpers ───────────────


class _DummyDevice:
    """測試用 device class placeholder。"""


class _DummyStrategy:
    """測試用 strategy class placeholder。"""


class _FakeBuilder:
    """模擬 SystemControllerConfigBuilder 的最小介面：只需要
    command_refresh 這個 fluent method。
    """

    def __init__(self) -> None:
        self.command_refresh_calls: list[dict] = []

    def command_refresh(
        self,
        *,
        interval_seconds: float = 1.0,
        enabled: bool = True,
        devices: list[str] | None = None,
    ) -> "_FakeBuilder":
        self.command_refresh_calls.append(
            {"interval_seconds": interval_seconds, "enabled": enabled, "devices": devices}
        )
        return self


def _mk_manifest(
    *,
    devices: tuple[DeviceSpec, ...] = (),
    strategies: tuple[StrategySpec, ...] = (),
    reconcilers: tuple[ReconcilerSpec, ...] = (),
) -> SiteManifest:
    return SiteManifest(
        apiVersion="csp_lib/v1",
        kind="Site",
        metadata=ManifestMetadata(name="test-site"),
        spec=SiteSpec(devices=devices, strategies=strategies, reconcilers=reconcilers),
    )


def _mk_registries() -> tuple[TypeRegistry, TypeRegistry]:
    """每次建立獨立 registry 避免 singleton 汙染。"""
    dev_reg: TypeRegistry = TypeRegistry("device-test")
    strat_reg: TypeRegistry = TypeRegistry("strategy-test")
    return dev_reg, strat_reg


# ─────────────── devices / strategies resolve ───────────────


class TestResolveDevices:
    def test_resolves_device_kind_to_class(self):
        dev_reg, strat_reg = _mk_registries()
        dev_reg.register("MyDev", _DummyDevice)
        builder = _FakeBuilder()

        manifest = _mk_manifest(devices=(DeviceSpec(kind="MyDev", name="dev1", config={"host": "1.2.3.4"}),))
        result = apply_manifest_to_builder(
            builder,
            manifest,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )

        assert len(result.devices) == 1
        bound = result.devices[0]
        assert isinstance(bound, BoundDeviceSpec)
        assert bound.name == "dev1"
        assert bound.cls is _DummyDevice
        assert bound.config["host"] == "1.2.3.4"
        assert bound.source.kind == "MyDev"

    def test_unknown_device_kind_raises_with_device_name(self):
        dev_reg, strat_reg = _mk_registries()
        # 不註冊 UnknownKind
        builder = _FakeBuilder()
        manifest = _mk_manifest(devices=(DeviceSpec(kind="UnknownKind", name="dev-missing"),))
        with pytest.raises(ConfigurationError) as exc_info:
            apply_manifest_to_builder(
                builder,
                manifest,
                device_registry=dev_reg,
                strategy_registry=strat_reg,
            )
        msg = str(exc_info.value)
        assert "dev-missing" in msg
        assert "UnknownKind" in msg

    def test_multiple_devices_resolved_in_order(self):
        dev_reg, strat_reg = _mk_registries()
        dev_reg.register("A", _DummyDevice)
        dev_reg.register("B", _DummyStrategy)  # 隨意複用測試 class
        builder = _FakeBuilder()
        manifest = _mk_manifest(
            devices=(
                DeviceSpec(kind="A", name="a1"),
                DeviceSpec(kind="B", name="b1"),
                DeviceSpec(kind="A", name="a2"),
            )
        )
        result = apply_manifest_to_builder(
            builder,
            manifest,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        assert [d.name for d in result.devices] == ["a1", "b1", "a2"]
        assert result.devices[0].cls is _DummyDevice
        assert result.devices[1].cls is _DummyStrategy
        assert result.devices[2].cls is _DummyDevice


class TestResolveStrategies:
    def test_resolves_strategy_kind_to_class(self):
        dev_reg, strat_reg = _mk_registries()
        strat_reg.register("MyStrat", _DummyStrategy)
        builder = _FakeBuilder()

        manifest = _mk_manifest(strategies=(StrategySpec(kind="MyStrat", name="strat1", config={"p": 100}),))
        result = apply_manifest_to_builder(
            builder,
            manifest,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )

        assert len(result.strategies) == 1
        bound = result.strategies[0]
        assert isinstance(bound, BoundStrategySpec)
        assert bound.name == "strat1"
        assert bound.cls is _DummyStrategy
        assert bound.config["p"] == 100

    def test_unknown_strategy_kind_raises_with_strategy_name(self):
        dev_reg, strat_reg = _mk_registries()
        builder = _FakeBuilder()
        manifest = _mk_manifest(strategies=(StrategySpec(kind="Nope", name="strat-missing"),))
        with pytest.raises(ConfigurationError) as exc_info:
            apply_manifest_to_builder(
                builder,
                manifest,
                device_registry=dev_reg,
                strategy_registry=strat_reg,
            )
        msg = str(exc_info.value)
        assert "strat-missing" in msg
        assert "Nope" in msg


# ─────────────── Builtin reconciler dispatch (CommandRefresh) ───────────────


class TestCommandRefreshReconciler:
    def test_command_refresh_spec_calls_builder_method(self):
        """kind='CommandRefresh' 的 reconciler 應呼叫 builder.command_refresh(**config)。"""
        dev_reg, strat_reg = _mk_registries()
        builder = _FakeBuilder()
        manifest = _mk_manifest(
            reconcilers=(
                ReconcilerSpec(
                    kind="CommandRefresh",
                    name="cr",
                    config={"interval_seconds": 2.5, "enabled": True},
                ),
            )
        )
        result = apply_manifest_to_builder(
            builder,
            manifest,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        # CommandRefresh 已被 builder 消化，不在 unbound
        assert result.reconcilers == ()
        # builder.command_refresh(...) 被呼叫，參數正確
        assert len(builder.command_refresh_calls) == 1
        call = builder.command_refresh_calls[0]
        assert call["interval_seconds"] == 2.5
        assert call["enabled"] is True

    def test_command_refresh_invalid_kwargs_raises(self):
        """config 含 builder.command_refresh 不接受的 kwargs → ConfigurationError。"""
        dev_reg, strat_reg = _mk_registries()
        builder = _FakeBuilder()
        manifest = _mk_manifest(
            reconcilers=(
                ReconcilerSpec(
                    kind="CommandRefresh",
                    name="bad-cr",
                    config={"nonexistent_kwarg": 123},
                ),
            )
        )
        with pytest.raises(ConfigurationError) as exc_info:
            apply_manifest_to_builder(
                builder,
                manifest,
                device_registry=dev_reg,
                strategy_registry=strat_reg,
            )
        msg = str(exc_info.value)
        assert "bad-cr" in msg
        assert "CommandRefresh" in msg
        assert "command_refresh" in msg

    def test_command_refresh_empty_config_ok(self):
        """空 config 等同使用 builder method 預設值。"""
        dev_reg, strat_reg = _mk_registries()
        builder = _FakeBuilder()
        manifest = _mk_manifest(reconcilers=(ReconcilerSpec(kind="CommandRefresh", name="cr"),))
        result = apply_manifest_to_builder(
            builder,
            manifest,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        assert result.reconcilers == ()
        assert builder.command_refresh_calls == [{"interval_seconds": 1.0, "enabled": True, "devices": None}]


# ─────────────── 未知 reconciler kind 保留 ───────────────


class TestUnknownReconcilerKind:
    def test_unknown_kind_preserved_in_unbound(self):
        dev_reg, strat_reg = _mk_registries()
        builder = _FakeBuilder()
        manifest = _mk_manifest(
            reconcilers=(
                ReconcilerSpec(kind="Heartbeat", name="hb1", config={"interval": 2}),
                ReconcilerSpec(kind="SetpointDrift", name="sd1"),
            )
        )
        result = apply_manifest_to_builder(
            builder,
            manifest,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        assert len(result.reconcilers) == 2
        kinds = [r.kind for r in result.reconcilers]
        assert "Heartbeat" in kinds
        assert "SetpointDrift" in kinds
        # 未知 kind 不會呼叫 builder.command_refresh
        assert builder.command_refresh_calls == []

    def test_unknown_preserves_config(self):
        dev_reg, strat_reg = _mk_registries()
        builder = _FakeBuilder()
        cfg = {"k": "v", "n": 42}
        manifest = _mk_manifest(reconcilers=(ReconcilerSpec(kind="Custom", name="c1", config=cfg),))
        result = apply_manifest_to_builder(
            builder,
            manifest,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        assert len(result.reconcilers) == 1
        bound = result.reconcilers[0]
        assert isinstance(bound, BoundReconcilerSpec)
        assert bound.kind == "Custom"
        assert bound.name == "c1"
        assert dict(bound.config) == cfg

    def test_mix_builtin_and_unknown(self):
        """builtin 呼 builder method；unknown 保留於 unbound。"""
        dev_reg, strat_reg = _mk_registries()
        builder = _FakeBuilder()
        manifest = _mk_manifest(
            reconcilers=(
                ReconcilerSpec(kind="CommandRefresh", name="cr", config={}),
                ReconcilerSpec(kind="MysteryRec", name="mr"),
            )
        )
        result = apply_manifest_to_builder(
            builder,
            manifest,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        assert len(builder.command_refresh_calls) == 1
        assert [r.kind for r in result.reconcilers] == ["MysteryRec"]


# ─────────────── Default registry fallback ───────────────


class TestDefaultRegistryFallback:
    """未傳 device_registry / strategy_registry 時使用 module-level singleton。"""

    def test_uses_default_singletons(self):
        from csp_lib.integration.type_registry import device_type_registry, strategy_type_registry

        dev_kind = "__BinderDefaultTestDev__"
        strat_kind = "__BinderDefaultTestStrat__"

        device_type_registry.register(dev_kind, _DummyDevice)
        strategy_type_registry.register(strat_kind, _DummyStrategy)
        try:
            builder = _FakeBuilder()
            manifest = _mk_manifest(
                devices=(DeviceSpec(kind=dev_kind, name="d"),),
                strategies=(StrategySpec(kind=strat_kind, name="s"),),
            )
            # 不指定 registry → 應走 singleton
            result = apply_manifest_to_builder(builder, manifest)
            assert result.devices[0].cls is _DummyDevice
            assert result.strategies[0].cls is _DummyStrategy
        finally:
            device_type_registry._table.pop(dev_kind, None)
            strategy_type_registry._table.pop(strat_kind, None)


# ─────────────── ManifestBindResult frozen ───────────────


class TestBindResultFrozen:
    def test_manifest_bind_result_frozen(self):
        result = ManifestBindResult(devices=(), strategies=(), reconcilers=())
        with pytest.raises(FrozenInstanceError):
            result.devices = ()  # type: ignore[misc]

    def test_bound_device_spec_frozen(self):
        spec = DeviceSpec(kind="A", name="a")
        bound = BoundDeviceSpec(name="a", cls=_DummyDevice, config={}, source=spec)
        with pytest.raises(FrozenInstanceError):
            bound.name = "b"  # type: ignore[misc]

    def test_bound_strategy_spec_frozen(self):
        spec = StrategySpec(kind="A", name="a")
        bound = BoundStrategySpec(name="a", cls=_DummyStrategy, config={}, source=spec)
        with pytest.raises(FrozenInstanceError):
            bound.cls = _DummyDevice  # type: ignore[misc]

    def test_bound_reconciler_spec_frozen(self):
        spec = ReconcilerSpec(kind="K", name="n")
        bound = BoundReconcilerSpec(kind="K", name="n", config={}, source=spec)
        with pytest.raises(FrozenInstanceError):
            bound.kind = "other"  # type: ignore[misc]


# ─────────────── 空 manifest ───────────────


class TestEmptyManifest:
    def test_empty_sections_produce_empty_tuples(self):
        """devices/strategies/reconcilers 皆空 → 結果也是空 tuple，不 raise。"""
        dev_reg, strat_reg = _mk_registries()
        builder = _FakeBuilder()
        manifest = _mk_manifest()
        result = apply_manifest_to_builder(
            builder,
            manifest,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        assert result.devices == ()
        assert result.strategies == ()
        assert result.reconcilers == ()
        assert builder.command_refresh_calls == []
