# =============== Integration - SiteManifest ===============
#
# K8s 風宣告式 Site 配置。
#
# YAML schema（apiVersion: csp_lib/v1）::
#
#   apiVersion: csp_lib/v1
#   kind: Site
#   metadata:
#     name: my-site
#     labels: {env: production}
#   spec:
#     devices:
#       - kind: ExamplePCS
#         name: PCS1
#         config: {host: 192.168.1.10, unit_id: 1}
#     strategies:
#       - kind: PQStrategy
#         name: default-pq
#         config: {p_target: 1000}
#     reconcilers:
#       - kind: CommandRefresh
#         name: cmd-refresh
#         config: {interval_seconds: 1.0}
#
# 安全：
#   - 一律使用 yaml.safe_load（禁用 yaml.load）
#   - pyyaml 走 lazy import（optional extra：csp0924_lib[manifest]）

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from csp_lib.core import get_logger
from csp_lib.core.errors import ConfigurationError

logger = get_logger(__name__)

SUPPORTED_API_VERSION = "csp_lib/v1"
SUPPORTED_KIND = "Site"


def _empty_mapping() -> Mapping[str, Any]:
    # MappingProxyType 本身就是 frozen 唯讀視圖；泛型在 runtime 被 erase，
    # 單一 factory 可同時服務 str→str 與 str→Any 的 default。
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class ManifestMetadata:
    """Manifest metadata section。

    Attributes:
        name:   Site 名稱（必填）
        labels: 任意 label 字典（唯讀）
    """

    name: str
    labels: Mapping[str, str] = field(default_factory=_empty_mapping)


@dataclass(frozen=True, slots=True)
class DeviceSpec:
    """單一設備宣告。

    Attributes:
        kind:   對應 device_type_registry 的 key（例：``"ExamplePCS"``）
        name:   實例 id（即 device_id）
        config: 建構參數 dict（會傳給 device class 的 ``__init__``）
    """

    kind: str
    name: str
    config: Mapping[str, Any] = field(default_factory=_empty_mapping)


@dataclass(frozen=True, slots=True)
class StrategySpec:
    """單一策略宣告。

    Attributes:
        kind:   對應 strategy_type_registry 的 key（例：``"PQStrategy"``）
        name:   實例 logical name
        config: 建構參數 dict
    """

    kind: str
    name: str
    config: Mapping[str, Any] = field(default_factory=_empty_mapping)


@dataclass(frozen=True, slots=True)
class ReconcilerSpec:
    """單一 reconciler 宣告。

    Attributes:
        kind:   reconciler 類型識別（例：``"CommandRefresh"``、``"Heartbeat"``、
                ``"SetpointDrift"``）
        name:   實例 logical name
        config: 建構參數 dict
    """

    kind: str
    name: str
    config: Mapping[str, Any] = field(default_factory=_empty_mapping)


@dataclass(frozen=True, slots=True)
class SiteSpec:
    """Site spec section。"""

    devices: tuple[DeviceSpec, ...] = ()
    strategies: tuple[StrategySpec, ...] = ()
    reconcilers: tuple[ReconcilerSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class SiteManifest:
    """完整 Site manifest 宣告式配置。

    Attributes:
        apiVersion: 必為 ``"csp_lib/v1"``
        kind:       必為 ``"Site"``
        metadata:   Site metadata
        spec:       Site spec（devices / strategies / reconcilers）
    """

    apiVersion: str
    kind: str
    metadata: ManifestMetadata
    spec: SiteSpec


# ─────────── Loader ───────────


def load_manifest(source: str | Path | Mapping[str, Any]) -> SiteManifest:
    """從 YAML 檔案、Path、或 dict 載入 SiteManifest。

    Args:
        source:
          - ``str`` / ``Path``: 視為檔案路徑，讀取並 ``yaml.safe_load``
          - ``Mapping``: 已 parse 的 dict（測試用或 Python 直建）

    Returns:
        SiteManifest frozen dataclass

    Raises:
        ImportError:        pyyaml 未安裝（提示 ``csp0924_lib[manifest]``）
        ConfigurationError: apiVersion/kind 不合法、必要欄位缺失
        FileNotFoundError:  source 是 path 但檔案不存在
    """
    if isinstance(source, Mapping):
        data: Mapping[str, Any] = source
    else:
        # Path / str 路徑：lazy import pyyaml
        try:
            import yaml  # type: ignore[import-untyped]  # noqa: PLC0415 - optional dep, lazy import on demand
        except ImportError as e:
            raise ImportError("load_manifest requires pyyaml; install with: pip install 'csp0924_lib[manifest]'") from e
        path = Path(source)
        with path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)  # SECURITY: 絕不可改成 yaml.load
        if not isinstance(loaded, Mapping):
            raise ConfigurationError(f"Manifest root must be a mapping, got {type(loaded).__name__}")
        data = loaded

    return _parse_manifest(data)


def _parse_manifest(data: Mapping[str, Any]) -> SiteManifest:
    """把 dict 解析為 frozen SiteManifest，做 schema validation。"""
    api_version = data.get("apiVersion")
    if api_version != SUPPORTED_API_VERSION:
        raise ConfigurationError(f"Unsupported apiVersion: {api_version!r}; supported: {SUPPORTED_API_VERSION!r}")

    kind = data.get("kind")
    if kind != SUPPORTED_KIND:
        raise ConfigurationError(f"Unsupported kind: {kind!r}; supported: {SUPPORTED_KIND!r}")

    metadata_raw = data.get("metadata") or {}
    if not isinstance(metadata_raw, Mapping):
        raise ConfigurationError("metadata must be a mapping")
    meta_name = metadata_raw.get("name")
    if not isinstance(meta_name, str) or not meta_name:
        raise ConfigurationError("metadata.name is required and must be a non-empty string")
    labels_raw = metadata_raw.get("labels") or {}
    if not isinstance(labels_raw, Mapping):
        raise ConfigurationError("metadata.labels must be a mapping")
    # 強制 str → str（YAML 可能載出 int value，明確 cast 避免型別混淆）
    metadata = ManifestMetadata(
        name=meta_name,
        labels=MappingProxyType({str(k): str(v) for k, v in labels_raw.items()}),
    )

    spec_raw = data.get("spec") or {}
    if not isinstance(spec_raw, Mapping):
        raise ConfigurationError("spec must be a mapping")

    devices = tuple(_parse_device_spec(d) for d in spec_raw.get("devices") or ())
    strategies = tuple(_parse_strategy_spec(s) for s in spec_raw.get("strategies") or ())
    reconcilers = tuple(_parse_reconciler_spec(r) for r in spec_raw.get("reconcilers") or ())

    return SiteManifest(
        apiVersion=api_version,
        kind=kind,
        metadata=metadata,
        spec=SiteSpec(devices=devices, strategies=strategies, reconcilers=reconcilers),
    )


def _require_kind_name(raw: Any, section: str) -> tuple[str, str, Mapping[str, Any]]:
    """共用 parser：取出 (kind, name, config)；缺欄位拋 ConfigurationError。"""
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"{section} entry must be a mapping, got {type(raw).__name__}")
    kind = raw.get("kind")
    name = raw.get("name")
    if not isinstance(kind, str) or not kind:
        raise ConfigurationError(f"{section}.kind is required and must be a non-empty string")
    if not isinstance(name, str) or not name:
        raise ConfigurationError(f"{section}.name is required and must be a non-empty string")
    config = raw.get("config") or {}
    if not isinstance(config, Mapping):
        raise ConfigurationError(f"{section}[{name}].config must be a mapping")
    return kind, name, MappingProxyType(dict(config))


def _parse_device_spec(raw: Any) -> DeviceSpec:
    kind, name, config = _require_kind_name(raw, "device")
    return DeviceSpec(kind=kind, name=name, config=config)


def _parse_strategy_spec(raw: Any) -> StrategySpec:
    kind, name, config = _require_kind_name(raw, "strategy")
    return StrategySpec(kind=kind, name=name, config=config)


def _parse_reconciler_spec(raw: Any) -> ReconcilerSpec:
    kind, name, config = _require_kind_name(raw, "reconciler")
    return ReconcilerSpec(kind=kind, name=name, config=config)


__all__ = [
    "SUPPORTED_API_VERSION",
    "SUPPORTED_KIND",
    "SiteManifest",
    "ManifestMetadata",
    "SiteSpec",
    "DeviceSpec",
    "StrategySpec",
    "ReconcilerSpec",
    "load_manifest",
]
