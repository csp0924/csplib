# =============== SystemControllerConfigBuilder.from_manifest Tests ===============
#
# 驗證 classmethod 入口：
#   - from_manifest(dict) → builder + manifest_* properties 正確
#   - from_manifest(SiteManifest instance) 直接 bind，跳過 load_manifest
#   - from_manifest + chain fluent method → build() 成功、回傳 frozen config
#   - manifest_* properties 是 tuple（不可變）
#   - from_manifest(不合法 manifest) → ConfigurationError 正常傳遞
#   - CommandRefresh reconciler kind → build() 後 command_refresh 已設定

from __future__ import annotations

from pathlib import Path

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.integration.manifest import (
    DeviceSpec,
    ManifestMetadata,
    SiteManifest,
    SiteSpec,
)
from csp_lib.integration.manifest_binder import (
    BoundDeviceSpec,
    BoundReconcilerSpec,
    BoundStrategySpec,
)
from csp_lib.integration.system_controller import (
    SystemControllerConfig,
    SystemControllerConfigBuilder,
)
from csp_lib.integration.type_registry import TypeRegistry


class _DummyDevice:
    """測試用 device class。"""


class _DummyStrategy:
    """測試用 strategy class。"""


def _mk_registries() -> tuple[TypeRegistry, TypeRegistry]:
    return TypeRegistry("d"), TypeRegistry("s")


def _valid_manifest_dict() -> dict:
    return {
        "apiVersion": "csp_lib/v1",
        "kind": "Site",
        "metadata": {"name": "test-site"},
        "spec": {
            "devices": [{"kind": "MyDev", "name": "dev1"}],
            "strategies": [{"kind": "MyStrat", "name": "strat1"}],
            "reconcilers": [
                {"kind": "CommandRefresh", "name": "cr", "config": {"interval_seconds": 2.0}},
            ],
        },
    }


# ─────────────── from_manifest(dict) ───────────────


class TestFromManifestDict:
    def test_returns_builder_instance(self):
        dev_reg, strat_reg = _mk_registries()
        dev_reg.register("MyDev", _DummyDevice)
        strat_reg.register("MyStrat", _DummyStrategy)

        builder = SystemControllerConfigBuilder.from_manifest(
            _valid_manifest_dict(),
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        assert isinstance(builder, SystemControllerConfigBuilder)

    def test_manifest_properties_populated(self):
        dev_reg, strat_reg = _mk_registries()
        dev_reg.register("MyDev", _DummyDevice)
        strat_reg.register("MyStrat", _DummyStrategy)

        builder = SystemControllerConfigBuilder.from_manifest(
            _valid_manifest_dict(),
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )

        assert len(builder.manifest_devices) == 1
        bound_dev = builder.manifest_devices[0]
        assert isinstance(bound_dev, BoundDeviceSpec)
        assert bound_dev.source.name == "dev1"
        assert bound_dev.cls is _DummyDevice

        assert len(builder.manifest_strategies) == 1
        bound_strat = builder.manifest_strategies[0]
        assert isinstance(bound_strat, BoundStrategySpec)
        assert bound_strat.cls is _DummyStrategy

        # CommandRefresh 已被 builder 消化 → manifest_reconcilers 為空
        assert builder.manifest_reconcilers == ()

    def test_manifest_source_preserved(self):
        dev_reg, strat_reg = _mk_registries()
        dev_reg.register("MyDev", _DummyDevice)
        strat_reg.register("MyStrat", _DummyStrategy)

        builder = SystemControllerConfigBuilder.from_manifest(
            _valid_manifest_dict(),
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        assert builder.manifest_source is not None
        assert isinstance(builder.manifest_source, SiteManifest)
        assert builder.manifest_source.metadata.name == "test-site"


# ─────────────── from_manifest(SiteManifest instance) ───────────────


class TestFromManifestInstance:
    def test_accepts_site_manifest_instance_directly(self):
        """傳 SiteManifest 實例應直接 bind，不經 load_manifest。"""
        dev_reg, strat_reg = _mk_registries()
        dev_reg.register("D", _DummyDevice)

        manifest = SiteManifest(
            apiVersion="csp_lib/v1",
            kind="Site",
            metadata=ManifestMetadata(name="direct"),
            spec=SiteSpec(devices=(DeviceSpec(kind="D", name="d1"),)),
        )
        builder = SystemControllerConfigBuilder.from_manifest(
            manifest,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        # manifest_source 直接引用同一個實例
        assert builder.manifest_source is manifest
        assert len(builder.manifest_devices) == 1


# ─────────────── chain fluent + build() ───────────────


class TestChainFluentMethods:
    def test_can_chain_fluent_methods_after_from_manifest(self):
        """from_manifest 後可繼續 chain，最後 build() 仍成功。"""
        dev_reg, strat_reg = _mk_registries()
        dev_reg.register("MyDev", _DummyDevice)
        strat_reg.register("MyStrat", _DummyStrategy)

        builder = SystemControllerConfigBuilder.from_manifest(
            _valid_manifest_dict(),
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        # 再 chain 額外設定
        config = builder.system_base(p_base=500.0, q_base=100.0).auto_stop(enabled=False).build()

        assert isinstance(config, SystemControllerConfig)
        assert config.system_base is not None
        assert config.system_base.p_base == 500.0
        assert config.system_base.q_base == 100.0
        assert config.auto_stop_on_alarm is False

    def test_command_refresh_from_manifest_propagates_to_config(self):
        """manifest 中的 CommandRefresh reconciler → build() 後 config.command_refresh 有值。"""
        dev_reg, strat_reg = _mk_registries()
        dev_reg.register("MyDev", _DummyDevice)
        strat_reg.register("MyStrat", _DummyStrategy)

        builder = SystemControllerConfigBuilder.from_manifest(
            _valid_manifest_dict(),
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        config = builder.build()
        assert config.command_refresh is not None
        assert config.command_refresh.refresh_interval == 2.0
        assert config.command_refresh.enabled is True


# ─────────────── manifest_* properties 不可變 ───────────────


class TestPropertiesAreTuples:
    def test_manifest_devices_is_tuple(self):
        dev_reg, strat_reg = _mk_registries()
        dev_reg.register("MyDev", _DummyDevice)
        strat_reg.register("MyStrat", _DummyStrategy)

        builder = SystemControllerConfigBuilder.from_manifest(
            _valid_manifest_dict(),
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        assert isinstance(builder.manifest_devices, tuple)
        assert isinstance(builder.manifest_strategies, tuple)
        assert isinstance(builder.manifest_reconcilers, tuple)

    def test_empty_builder_returns_empty_tuples(self):
        """未走 from_manifest 的空 builder → manifest_* 皆空 tuple（不是 None）。"""
        builder = SystemControllerConfigBuilder()
        assert builder.manifest_devices == ()
        assert builder.manifest_strategies == ()
        assert builder.manifest_reconcilers == ()
        assert builder.manifest_source is None

    def test_unknown_reconciler_kind_kept_as_bound_spec(self):
        """未知 reconciler kind 應保留於 manifest_reconcilers 供後續處理。"""
        dev_reg, strat_reg = _mk_registries()
        data = _valid_manifest_dict()
        data["spec"]["reconcilers"] = [
            {"kind": "Heartbeat", "name": "hb"},  # 不是 builtin 消化的 CommandRefresh
        ]
        data["spec"]["devices"] = []
        data["spec"]["strategies"] = []
        builder = SystemControllerConfigBuilder.from_manifest(
            data,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        assert len(builder.manifest_reconcilers) == 1
        bound = builder.manifest_reconcilers[0]
        assert isinstance(bound, BoundReconcilerSpec)
        assert bound.source.kind == "Heartbeat"


# ─────────────── 不合法 manifest propagation ───────────────


class TestInvalidManifestPropagation:
    def test_missing_api_version_raises_configuration_error(self):
        data = _valid_manifest_dict()
        del data["apiVersion"]
        with pytest.raises(ConfigurationError, match="apiVersion"):
            SystemControllerConfigBuilder.from_manifest(data)

    def test_unknown_device_kind_raises_configuration_error(self):
        """manifest device kind 查無 → ConfigurationError（含裝置 name）。"""
        dev_reg, strat_reg = _mk_registries()
        # 沒註冊 MyDev
        data = _valid_manifest_dict()
        data["spec"]["strategies"] = []  # 簡化
        data["spec"]["reconcilers"] = []
        with pytest.raises(ConfigurationError) as exc_info:
            SystemControllerConfigBuilder.from_manifest(
                data,
                device_registry=dev_reg,
                strategy_registry=strat_reg,
            )
        assert "dev1" in str(exc_info.value)

    def test_unknown_strategy_kind_raises_configuration_error(self):
        dev_reg, strat_reg = _mk_registries()
        dev_reg.register("MyDev", _DummyDevice)
        # 沒註冊 MyStrat
        data = _valid_manifest_dict()
        data["spec"]["reconcilers"] = []
        with pytest.raises(ConfigurationError) as exc_info:
            SystemControllerConfigBuilder.from_manifest(
                data,
                device_registry=dev_reg,
                strategy_registry=strat_reg,
            )
        assert "strat1" in str(exc_info.value)


# ─────────────── YAML 檔案路徑 ───────────────


class TestFromYamlPath:
    def test_from_yaml_file(self, tmp_path: Path):
        """from_manifest 接受 YAML 檔案路徑（透過 load_manifest）。"""
        pytest.importorskip("yaml")

        dev_reg, strat_reg = _mk_registries()
        dev_reg.register("D", _DummyDevice)

        yaml_path = tmp_path / "site.yaml"
        yaml_path.write_text(
            """
apiVersion: csp_lib/v1
kind: Site
metadata:
  name: yaml-site
spec:
  devices:
    - kind: D
      name: d-from-yaml
""",
            encoding="utf-8",
        )
        builder = SystemControllerConfigBuilder.from_manifest(
            yaml_path,
            device_registry=dev_reg,
            strategy_registry=strat_reg,
        )
        assert builder.manifest_source is not None
        assert builder.manifest_source.metadata.name == "yaml-site"
        assert builder.manifest_devices[0].source.name == "d-from-yaml"


# ─────────────── ReconcilerSpec 不合法 kwargs ───────────────


class TestReconcilerConfigErrorPropagation:
    def test_command_refresh_invalid_config_raises(self):
        """manifest 中 CommandRefresh 的 config 帶不合法 kwargs → ConfigurationError。"""
        dev_reg, strat_reg = _mk_registries()
        data = _valid_manifest_dict()
        data["spec"]["devices"] = []
        data["spec"]["strategies"] = []
        data["spec"]["reconcilers"] = [
            {
                "kind": "CommandRefresh",
                "name": "cr",
                "config": {"unknown_kwarg": 42},
            }
        ]
        with pytest.raises(ConfigurationError):
            SystemControllerConfigBuilder.from_manifest(
                data,
                device_registry=dev_reg,
                strategy_registry=strat_reg,
            )
