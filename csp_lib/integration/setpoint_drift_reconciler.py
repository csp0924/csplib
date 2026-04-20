# =============== Integration - Setpoint Drift Reconciler ===============
#
# Operator Pattern 基礎 (K8s 風) — 偵測 Gateway / 外部工具覆蓋命令設定值
# 的 reconciler。
#
# 機制：
#   desired state = CommandRouter._last_written（上次業務寫入的值）
#   actual state  = device.latest_values[point_name]（設備端目前 cached 值）
#   drift         = |actual - desired| > tolerance
#   action        = router.try_write_single(...) 重寫；log 事件
#
# 與 CommandRefreshService 差異：
#   - CommandRefreshService: 無條件週期重寫（便宜、防護斷線重連覆蓋）
#   - SetpointDriftReconciler: 先讀 cache 後比對，只在偵測到漂移才重寫
#                              （有 audit trail 需求的場景）

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from csp_lib.core import get_logger
from csp_lib.core.errors import ConfigurationError

from .reconciler import ReconcilerMixin

if TYPE_CHECKING:
    from .command_router import CommandRouter
    from .registry import DeviceRegistry

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DriftTolerance:
    """Drift 容忍度配置。

    Attributes:
        absolute: 絕對容忍（``|actual - desired| <= absolute`` 視為未漂移）
        relative: 相對容忍（``|actual - desired| / |desired| <= relative`` 視為未漂移）
                  若兩者都設，取 OR（任一滿足即視為未漂移）
    """

    absolute: float = 0.0
    relative: float = 0.0


# Module-level singleton；frozen 本身就是 safe default（避開 ruff B008）。
_DEFAULT_TOLERANCE: DriftTolerance = DriftTolerance(absolute=0.0, relative=0.01)


class SetpointDriftReconciler(ReconcilerMixin):
    """偵測 command setpoint 被外部覆蓋並自動復原。

    實作 Reconciler Protocol（``name`` / ``status`` / ``reconcile_once``）。
    生命週期由外層 loop 管（不繼承 AsyncLifecycleMixin）。

    Args:
        router:    需已啟用 desired-state 追蹤的 CommandRouter
        registry:  DeviceRegistry（用於讀取 device.latest_values）
        tolerance: 預設容忍度；單一設備可由 per_device_tolerance override
        per_device_tolerance: ``{device_id: DriftTolerance}`` 映射
        name:      Reconciler name（預設 ``"setpoint_drift"``）

    Raises:
        ConfigurationError: tolerance 參數無效（absolute < 0 或 relative < 0）
    """

    def __init__(
        self,
        router: CommandRouter,
        registry: DeviceRegistry,
        *,
        tolerance: DriftTolerance = _DEFAULT_TOLERANCE,
        per_device_tolerance: Mapping[str, DriftTolerance] | None = None,
        name: str = "setpoint_drift",
    ) -> None:
        if tolerance.absolute < 0 or tolerance.relative < 0:
            raise ConfigurationError(f"DriftTolerance must be non-negative, got {tolerance!r}")
        if per_device_tolerance is not None:
            for dev_id, tol in per_device_tolerance.items():
                if tol.absolute < 0 or tol.relative < 0:
                    raise ConfigurationError(f"per_device_tolerance[{dev_id!r}] must be non-negative, got {tol!r}")

        self._router = router
        self._registry = registry
        self._tolerance = tolerance
        self._per_device: Mapping[str, DriftTolerance] = MappingProxyType(dict(per_device_tolerance or {}))
        self._init_reconciler(name)

    # ---- Reconciler Protocol ----
    #
    # name / status / reconcile_once 由 ReconcilerMixin 提供。

    async def _reconcile_work(self) -> Mapping[str, Any] | None:
        """掃描所有被追蹤 device，偵測 drift 並重寫。回傳 detail dict。"""
        drift_count = 0
        devices_fixed: list[str] = []

        for device_id in self._router.get_tracked_device_ids():
            snapshot = self._router.get_last_written(device_id)
            if not snapshot:
                continue
            device = self._registry.get_device(device_id)
            if device is None or not device.is_responsive:
                continue
            latest = device.latest_values
            tol = self._per_device.get(device_id, self._tolerance)
            for point_name, desired in snapshot.items():
                if point_name not in latest:
                    # 尚未讀到值，skip 本輪
                    continue
                actual = latest[point_name]
                if not self._is_drift(desired, actual, tol):
                    continue
                drift_count += 1
                ok = await self._router.try_write_single(device_id, point_name, desired)
                if ok:
                    devices_fixed.append(f"{device_id}.{point_name}")
                    logger.info(
                        f"Setpoint drift fixed: {device_id}.{point_name} actual={actual!r} -> desired={desired!r}"
                    )

        return {
            "drift_count": drift_count,
            "devices_fixed": tuple(devices_fixed),
        }

    @staticmethod
    def _is_drift(desired: Any, actual: Any, tol: DriftTolerance) -> bool:
        """僅對 numeric 型別做 drift 判斷；非 numeric 用 != 比較。"""
        if isinstance(desired, bool) or isinstance(actual, bool):
            # bool 是 int 的子類，要先擋掉避免誤判
            return desired != actual
        if not isinstance(desired, (int, float)) or not isinstance(actual, (int, float)):
            return desired != actual
        diff = abs(float(actual) - float(desired))
        if diff <= tol.absolute:
            return False
        if tol.relative > 0 and abs(float(desired)) > 0:
            if diff / abs(float(desired)) <= tol.relative:
                return False
        return True


__all__ = [
    "DriftTolerance",
    "SetpointDriftReconciler",
]
