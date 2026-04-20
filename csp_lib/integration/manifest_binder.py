# =============== Integration - Manifest Binder ===============
#
# 把 SiteManifest 的宣告式配置 bind 到 SystemControllerConfigBuilder 的
# 內部狀態。
#
# 處理內容：
#   - spec.devices     → resolve kind 到 device class，回傳 BoundDeviceSpec
#   - spec.strategies  → resolve kind 到 strategy class，回傳 BoundStrategySpec
#   - spec.reconcilers → 對已知 kind (CommandRefresh) 直接呼叫 builder fluent
#                        method；未知 kind 留作 BoundReconcilerSpec 傳回供
#                        SystemController 啟動流程實例化
#
# 此檔不依賴 system_controller.py 的 class（透過 Protocol-like duck-typing
# 呼叫 builder.command_refresh(...) 等方法），避免循環 import。

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from csp_lib.core import get_logger
from csp_lib.core.errors import ConfigurationError

from .manifest import DeviceSpec, ReconcilerSpec, SiteManifest, StrategySpec
from .type_registry import TypeRegistry, device_type_registry, strategy_type_registry

if TYPE_CHECKING:
    from csp_lib.controller.core import Strategy
    from csp_lib.equipment.device import AsyncModbusDevice

logger = get_logger(__name__)


# Bound*Spec 只保留「解析後才出現」的資訊（cls）與原始 spec（source），
# 避免把 source.name / source.config 再複製一份造成雙來源真相。
# 呼叫端如需 name / config 請透過 bound.source.name / bound.source.config 取用。


@dataclass(frozen=True, slots=True)
class BoundDeviceSpec:
    """解析後的 device spec：kind 已對映到 class，但尚未 instantiate。"""

    cls: type["AsyncModbusDevice"]
    source: DeviceSpec


@dataclass(frozen=True, slots=True)
class BoundStrategySpec:
    """解析後的 strategy spec：kind 已對映到 class，但尚未 instantiate。"""

    cls: type["Strategy"]
    source: StrategySpec


@dataclass(frozen=True, slots=True)
class BoundReconcilerSpec:
    """未被 builder fluent method 消化的 reconciler spec。

    SystemController 啟動流程可依 ``source.kind`` 自行實例化（例如 Heartbeat、
    SetpointDrift 等進階 reconciler）。
    """

    source: ReconcilerSpec


@dataclass(frozen=True, slots=True)
class ManifestBindResult:
    """apply_manifest_to_builder 的結構化回傳。"""

    devices: tuple[BoundDeviceSpec, ...]
    strategies: tuple[BoundStrategySpec, ...]
    reconcilers: tuple[BoundReconcilerSpec, ...]


# kind 字串 → builder method name 對應表
# builder.command_refresh(**config) 吃 interval_seconds / enabled / devices 等 kwargs
_BUILTIN_RECONCILER_DISPATCH: dict[str, str] = {
    "CommandRefresh": "command_refresh",
}


def apply_manifest_to_builder(
    builder: Any,
    manifest: SiteManifest,
    *,
    device_registry: TypeRegistry["AsyncModbusDevice"] | None = None,
    strategy_registry: TypeRegistry["Strategy"] | None = None,
) -> ManifestBindResult:
    """把 SiteManifest 內容 bind 到 SystemControllerConfigBuilder。

    Args:
        builder:           SystemControllerConfigBuilder 實例（duck-typed）
        manifest:          已 parse 的 SiteManifest
        device_registry:   預設用 module-level singleton
        strategy_registry: 同上

    Returns:
        ManifestBindResult（devices / strategies / 未處理的 reconcilers）

    Raises:
        ConfigurationError: kind 未註冊、或 builtin reconciler 的 config
                            kwargs 不被 builder method 接受
    """
    dev_reg = device_registry or device_type_registry
    strat_reg = strategy_registry or strategy_type_registry

    devices = tuple(_resolve_device(d, dev_reg) for d in manifest.spec.devices)
    strategies = tuple(_resolve_strategy(s, strat_reg) for s in manifest.spec.strategies)

    unbound_reconcilers: list[BoundReconcilerSpec] = []
    for rec in manifest.spec.reconcilers:
        builder_method_name = _BUILTIN_RECONCILER_DISPATCH.get(rec.kind)
        if builder_method_name is None:
            unbound_reconcilers.append(BoundReconcilerSpec(source=rec))
            continue
        method = getattr(builder, builder_method_name, None)
        if method is None:
            raise ConfigurationError(
                f"Manifest reconciler kind={rec.kind!r} maps to builder "
                f"method {builder_method_name!r} but builder lacks it"
            )
        try:
            method(**dict(rec.config))
        except TypeError as e:
            raise ConfigurationError(
                f"Manifest reconciler[{rec.name!r}] kind={rec.kind!r} config "
                f"rejected by builder.{builder_method_name}: {e}"
            ) from e

    return ManifestBindResult(
        devices=devices,
        strategies=strategies,
        reconcilers=tuple(unbound_reconcilers),
    )


def _resolve_device(spec: DeviceSpec, registry: TypeRegistry["AsyncModbusDevice"]) -> BoundDeviceSpec:
    try:
        cls = registry.get(spec.kind)
    except ConfigurationError as e:
        raise ConfigurationError(f"Manifest device[{spec.name!r}]: {e}") from e
    return BoundDeviceSpec(cls=cls, source=spec)


def _resolve_strategy(spec: StrategySpec, registry: TypeRegistry["Strategy"]) -> BoundStrategySpec:
    try:
        cls = registry.get(spec.kind)
    except ConfigurationError as e:
        raise ConfigurationError(f"Manifest strategy[{spec.name!r}]: {e}") from e
    return BoundStrategySpec(cls=cls, source=spec)


__all__ = [
    "BoundDeviceSpec",
    "BoundStrategySpec",
    "BoundReconcilerSpec",
    "ManifestBindResult",
    "apply_manifest_to_builder",
]
