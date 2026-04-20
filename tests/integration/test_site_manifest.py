# =============== SiteManifest Tests ===============
#
# 驗證 load_manifest 與 SiteManifest 的 schema validation：
#   - 合法 manifest（dict）parse 成功
#   - apiVersion / kind / metadata.name 必填驗證
#   - devices / strategies / reconcilers 的 kind / name 必填驗證
#   - labels / config 可省略，labels int 值會被 str 化
#   - 安全性：yaml.safe_load（禁用 yaml.load）→ !!python/object 類不被解析
#   - 傳 dict 不需要 pyyaml（monkeypatch import 驗證）
#   - pyyaml 缺失 + path 來源 → ImportError 含 csp_lib[manifest]
#   - SiteManifest / DeviceSpec frozen check

from __future__ import annotations

import builtins
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.integration.manifest import (
    SUPPORTED_API_VERSION,
    SUPPORTED_KIND,
    DeviceSpec,
    ManifestMetadata,
    ReconcilerSpec,
    SiteManifest,
    SiteSpec,
    StrategySpec,
    load_manifest,
)

# ─────────────── Helpers ───────────────


def _valid_manifest_dict() -> dict:
    """最小合法 manifest dict。"""
    return {
        "apiVersion": SUPPORTED_API_VERSION,
        "kind": SUPPORTED_KIND,
        "metadata": {"name": "site-a"},
        "spec": {
            "devices": [
                {"kind": "ExamplePCS", "name": "PCS1", "config": {"host": "1.2.3.4"}},
            ],
            "strategies": [
                {"kind": "PQStrategy", "name": "default", "config": {"p_target": 1000}},
            ],
            "reconcilers": [
                {"kind": "CommandRefresh", "name": "cmd-refresh", "config": {}},
            ],
        },
    }


# ─────────────── 合法 manifest parse ───────────────


class TestValidManifestParse:
    def test_parse_complete_manifest(self):
        manifest = load_manifest(_valid_manifest_dict())
        assert isinstance(manifest, SiteManifest)
        assert manifest.apiVersion == SUPPORTED_API_VERSION
        assert manifest.kind == SUPPORTED_KIND
        assert manifest.metadata.name == "site-a"
        assert len(manifest.spec.devices) == 1
        assert len(manifest.spec.strategies) == 1
        assert len(manifest.spec.reconcilers) == 1

    def test_device_spec_fields(self):
        manifest = load_manifest(_valid_manifest_dict())
        dev = manifest.spec.devices[0]
        assert isinstance(dev, DeviceSpec)
        assert dev.kind == "ExamplePCS"
        assert dev.name == "PCS1"
        assert dev.config["host"] == "1.2.3.4"

    def test_strategy_spec_fields(self):
        manifest = load_manifest(_valid_manifest_dict())
        strat = manifest.spec.strategies[0]
        assert isinstance(strat, StrategySpec)
        assert strat.kind == "PQStrategy"
        assert strat.name == "default"
        assert strat.config["p_target"] == 1000

    def test_reconciler_spec_fields(self):
        manifest = load_manifest(_valid_manifest_dict())
        rec = manifest.spec.reconcilers[0]
        assert isinstance(rec, ReconcilerSpec)
        assert rec.kind == "CommandRefresh"
        assert rec.name == "cmd-refresh"


# ─────────────── apiVersion / kind / metadata validation ───────────────


class TestApiVersionValidation:
    def test_missing_api_version_raises(self):
        data = _valid_manifest_dict()
        del data["apiVersion"]
        with pytest.raises(ConfigurationError, match="apiVersion"):
            load_manifest(data)

    def test_wrong_api_version_raises(self):
        data = _valid_manifest_dict()
        data["apiVersion"] = "csp_lib/v2"
        with pytest.raises(ConfigurationError, match="Unsupported apiVersion"):
            load_manifest(data)


class TestKindValidation:
    def test_missing_kind_raises(self):
        data = _valid_manifest_dict()
        del data["kind"]
        with pytest.raises(ConfigurationError, match="Unsupported kind"):
            load_manifest(data)

    def test_wrong_kind_raises(self):
        data = _valid_manifest_dict()
        data["kind"] = "NotSite"
        with pytest.raises(ConfigurationError, match="Unsupported kind"):
            load_manifest(data)


class TestMetadataValidation:
    def test_missing_metadata_name_raises(self):
        data = _valid_manifest_dict()
        data["metadata"] = {}
        with pytest.raises(ConfigurationError, match="metadata.name"):
            load_manifest(data)

    def test_empty_metadata_name_raises(self):
        data = _valid_manifest_dict()
        data["metadata"] = {"name": ""}
        with pytest.raises(ConfigurationError, match="metadata.name"):
            load_manifest(data)

    def test_none_metadata_name_raises(self):
        data = _valid_manifest_dict()
        data["metadata"] = {"name": None}
        with pytest.raises(ConfigurationError, match="metadata.name"):
            load_manifest(data)

    def test_non_str_metadata_name_raises(self):
        data = _valid_manifest_dict()
        data["metadata"] = {"name": 123}
        with pytest.raises(ConfigurationError, match="metadata.name"):
            load_manifest(data)

    def test_metadata_not_mapping_raises(self):
        data = _valid_manifest_dict()
        data["metadata"] = "not-a-mapping"
        with pytest.raises(ConfigurationError, match="metadata must be a mapping"):
            load_manifest(data)

    def test_labels_not_mapping_raises(self):
        data = _valid_manifest_dict()
        data["metadata"] = {"name": "ok", "labels": ["not", "a", "mapping"]}
        with pytest.raises(ConfigurationError, match="metadata.labels"):
            load_manifest(data)


# ─────────────── devices / strategies / reconcilers 的 kind / name ───────────────


@pytest.mark.parametrize("section", ["devices", "strategies", "reconcilers"])
class TestSpecSectionKindNameValidation:
    def test_missing_kind_raises(self, section):
        data = _valid_manifest_dict()
        data["spec"][section] = [{"name": "x"}]
        with pytest.raises(ConfigurationError, match="kind"):
            load_manifest(data)

    def test_missing_name_raises(self, section):
        data = _valid_manifest_dict()
        data["spec"][section] = [{"kind": "SomeKind"}]
        with pytest.raises(ConfigurationError, match="name"):
            load_manifest(data)

    def test_empty_kind_raises(self, section):
        data = _valid_manifest_dict()
        data["spec"][section] = [{"kind": "", "name": "x"}]
        with pytest.raises(ConfigurationError, match="kind"):
            load_manifest(data)

    def test_empty_name_raises(self, section):
        data = _valid_manifest_dict()
        data["spec"][section] = [{"kind": "K", "name": ""}]
        with pytest.raises(ConfigurationError, match="name"):
            load_manifest(data)

    def test_entry_not_mapping_raises(self, section):
        data = _valid_manifest_dict()
        data["spec"][section] = ["not-a-mapping"]
        with pytest.raises(ConfigurationError, match="must be a mapping"):
            load_manifest(data)

    def test_config_not_mapping_raises(self, section):
        data = _valid_manifest_dict()
        data["spec"][section] = [{"kind": "K", "name": "n", "config": "not-mapping"}]
        with pytest.raises(ConfigurationError, match="config"):
            load_manifest(data)


# ─────────────── Default / optional fields ───────────────


class TestOptionalFields:
    def test_labels_omitted_uses_default_empty(self):
        """metadata.labels 可省略，預設為空 Mapping。"""
        data = _valid_manifest_dict()
        data["metadata"] = {"name": "site-a"}  # no labels
        manifest = load_manifest(data)
        assert dict(manifest.metadata.labels) == {}

    def test_config_omitted_uses_default_empty(self):
        """DeviceSpec / StrategySpec / ReconcilerSpec 的 config 可省略。"""
        data = _valid_manifest_dict()
        data["spec"] = {
            "devices": [{"kind": "X", "name": "x"}],
            "strategies": [{"kind": "Y", "name": "y"}],
            "reconcilers": [{"kind": "Z", "name": "z"}],
        }
        manifest = load_manifest(data)
        assert dict(manifest.spec.devices[0].config) == {}
        assert dict(manifest.spec.strategies[0].config) == {}
        assert dict(manifest.spec.reconcilers[0].config) == {}

    def test_spec_entire_section_omitted(self):
        """spec.devices / strategies / reconcilers 整段可省略。"""
        data = _valid_manifest_dict()
        data["spec"] = {}
        manifest = load_manifest(data)
        assert manifest.spec.devices == ()
        assert manifest.spec.strategies == ()
        assert manifest.spec.reconcilers == ()

    def test_labels_int_value_coerced_to_str(self):
        """labels 的 value 為 int（YAML 會載出 int）應被強制轉 str。"""
        data = _valid_manifest_dict()
        data["metadata"] = {
            "name": "site-a",
            "labels": {"region": "prod", "priority": 42, "enabled": True},
        }
        manifest = load_manifest(data)
        assert manifest.metadata.labels["region"] == "prod"
        assert manifest.metadata.labels["priority"] == "42"
        assert manifest.metadata.labels["enabled"] == "True"


# ─────────────── Frozen check ───────────────


class TestFrozenness:
    """SiteManifest / DeviceSpec / StrategySpec / ReconcilerSpec / ManifestMetadata
    都應為 frozen dataclass，不允許 mutate。
    """

    def test_site_manifest_frozen(self):
        manifest = load_manifest(_valid_manifest_dict())
        with pytest.raises(FrozenInstanceError):
            manifest.apiVersion = "other"  # type: ignore[misc]

    def test_device_spec_frozen(self):
        dev = DeviceSpec(kind="A", name="a")
        with pytest.raises(FrozenInstanceError):
            dev.kind = "B"  # type: ignore[misc]

    def test_strategy_spec_frozen(self):
        strat = StrategySpec(kind="A", name="a")
        with pytest.raises(FrozenInstanceError):
            strat.name = "b"  # type: ignore[misc]

    def test_reconciler_spec_frozen(self):
        rec = ReconcilerSpec(kind="A", name="a")
        with pytest.raises(FrozenInstanceError):
            rec.name = "b"  # type: ignore[misc]

    def test_metadata_frozen(self):
        meta = ManifestMetadata(name="s")
        with pytest.raises(FrozenInstanceError):
            meta.name = "t"  # type: ignore[misc]

    def test_site_spec_frozen(self):
        spec = SiteSpec()
        with pytest.raises(FrozenInstanceError):
            spec.devices = ()  # type: ignore[misc]


# ─────────────── YAML 安全性 ───────────────


class TestYamlSecurity:
    """驗證 load_manifest 走 yaml.safe_load（非 yaml.load），
    !!python/object 類不可執行的 YAML tag 應被拒絕。
    """

    def test_unsafe_yaml_tag_rejected(self, tmp_path: Path):
        """含 !!python/object/apply:os.system 的 YAML 用 safe_load 載入會 raise
        yaml.constructor.ConstructorError（非 ConfigurationError），
        驗證實作未走 yaml.load。"""
        pytest.importorskip("yaml")
        import yaml

        yaml_path = tmp_path / "unsafe.yaml"
        yaml_path.write_text(
            """
apiVersion: csp_lib/v1
kind: Site
metadata:
  name: evil
  pwn: !!python/object/apply:os.system ['echo pwned']
spec: {}
""",
            encoding="utf-8",
        )
        # safe_load 應該拒絕 !!python/object tag
        with pytest.raises(yaml.YAMLError):
            load_manifest(yaml_path)

    def test_yaml_file_loads_successfully(self, tmp_path: Path):
        """正常 YAML 檔案能被 load_manifest 讀取。"""
        pytest.importorskip("yaml")
        yaml_path = tmp_path / "site.yaml"
        yaml_path.write_text(
            """
apiVersion: csp_lib/v1
kind: Site
metadata:
  name: real-site
  labels:
    region: prod
spec:
  devices:
    - kind: ExamplePCS
      name: PCS1
""",
            encoding="utf-8",
        )
        manifest = load_manifest(yaml_path)
        assert manifest.metadata.name == "real-site"
        assert manifest.metadata.labels["region"] == "prod"
        assert len(manifest.spec.devices) == 1

    def test_yaml_file_str_path_also_works(self, tmp_path: Path):
        """傳 str 路徑（非 Path）也應能讀取。"""
        pytest.importorskip("yaml")
        yaml_path = tmp_path / "site.yaml"
        yaml_path.write_text(
            """
apiVersion: csp_lib/v1
kind: Site
metadata:
  name: str-path-site
spec: {}
""",
            encoding="utf-8",
        )
        manifest = load_manifest(str(yaml_path))
        assert manifest.metadata.name == "str-path-site"

    def test_yaml_file_non_mapping_root_raises(self, tmp_path: Path):
        """YAML 檔案 root 不是 mapping（如 list） → ConfigurationError。"""
        pytest.importorskip("yaml")
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text(
            """
- not
- a
- mapping
""",
            encoding="utf-8",
        )
        with pytest.raises(ConfigurationError, match="must be a mapping"):
            load_manifest(yaml_path)


# ─────────────── pyyaml 缺失 ───────────────


class TestPyyamlOptionalDependency:
    """傳 dict 不需要 pyyaml；傳 path 無 pyyaml → ImportError 含
    ``csp_lib[manifest]`` 字樣。"""

    def test_dict_source_does_not_require_yaml(self, monkeypatch):
        """把 yaml import 弄失敗，驗證 dict 路徑仍能成功 parse。"""
        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "yaml":
                raise ImportError("simulated: yaml not installed")
            return real_import(name, globals, locals, fromlist, level)

        # 清除已 cache 的 yaml module，強制重新 import
        monkeypatch.delitem(sys.modules, "yaml", raising=False)
        monkeypatch.setattr(builtins, "__import__", fake_import)

        # dict 路徑不經 lazy import yaml
        manifest = load_manifest(_valid_manifest_dict())
        assert manifest.metadata.name == "site-a"

    def test_path_source_without_yaml_raises_importerror(self, monkeypatch, tmp_path: Path):
        """傳 path 且 yaml import 失敗 → ImportError 內容提示 csp_lib[manifest]。"""
        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "yaml":
                raise ImportError("simulated: yaml not installed")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.delitem(sys.modules, "yaml", raising=False)
        monkeypatch.setattr(builtins, "__import__", fake_import)

        yaml_path = tmp_path / "site.yaml"
        yaml_path.write_text("{}", encoding="utf-8")

        with pytest.raises(ImportError, match="csp0924_lib\\[manifest\\]|csp_lib\\[manifest\\]"):
            load_manifest(yaml_path)


# ─────────────── 其他邊界 ───────────────


class TestMiscEdgeCases:
    def test_nonexistent_file_raises_file_not_found(self, tmp_path: Path):
        """不存在的 path → FileNotFoundError。"""
        pytest.importorskip("yaml")
        missing = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError):
            load_manifest(missing)
