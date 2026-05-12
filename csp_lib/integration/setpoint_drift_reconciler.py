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

import math
import time
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
        min_rewrite_interval_seconds: per-(device, point) audit cooldown 視窗（秒）；
            > 0 時，對同 (device, point) 在前一次**成功寫入** N 秒內偵測到的 drift
            會被跳過（不重寫、不 log）。預設 ``0.0`` = 關閉 cooldown。
            production 建議設為 ReadScheduler 週期的 1.5-2 倍以避免 audit log spam：
            ReadScheduler 把新 actual 讀回前，同 drift 會被每個 reconcile cycle 重複偵測，
            破壞 reconciler 「偵測 + 記錄 drift event」的 audit-trail 設計意圖。
            **write 失敗不啟動 cooldown**（cooldown 是「成功記錄」的去抖，不是「最近嘗試」的去抖）
            → transient modbus error 不會卡死，下一 reconcile 立即 retry。
        name:      Reconciler name（預設 ``"setpoint_drift"``）

    Raises:
        ConfigurationError: tolerance 參數無效（absolute < 0 或 relative < 0），
            或 min_rewrite_interval_seconds < 0。
    """

    def __init__(
        self,
        router: CommandRouter,
        registry: DeviceRegistry,
        *,
        tolerance: DriftTolerance = _DEFAULT_TOLERANCE,
        per_device_tolerance: Mapping[str, DriftTolerance] | None = None,
        min_rewrite_interval_seconds: float = 0.0,
        name: str = "setpoint_drift",
    ) -> None:
        if tolerance.absolute < 0 or tolerance.relative < 0:
            raise ConfigurationError(f"DriftTolerance must be non-negative, got {tolerance!r}")
        if per_device_tolerance is not None:
            for dev_id, tol in per_device_tolerance.items():
                if tol.absolute < 0 or tol.relative < 0:
                    raise ConfigurationError(f"per_device_tolerance[{dev_id!r}] must be non-negative, got {tol!r}")
        if min_rewrite_interval_seconds < 0:
            raise ConfigurationError(f"min_rewrite_interval_seconds must be >= 0, got {min_rewrite_interval_seconds}")

        self._router = router
        self._registry = registry
        self._tolerance = tolerance
        self._per_device: Mapping[str, DriftTolerance] = MappingProxyType(dict(per_device_tolerance or {}))
        self._min_rewrite_interval = min_rewrite_interval_seconds
        # 每對 (device_id, point_name) 最近一次成功寫入的 monotonic timestamp。
        # Stable-topology 假設：caller 動態 untrack device 時，對應 entry 不會自動 evict；
        # production EMS 通常 boot 時 fix 設備集合，typical scale (~500 entry / ~40KB) 無虞。
        self._last_write_at: dict[tuple[str, str], float] = {}
        self._init_reconciler(name)

    # ---- Reconciler Protocol ----
    #
    # name / status / reconcile_once 由 ReconcilerMixin 提供。

    async def _reconcile_work(self, detail: dict[str, Any]) -> None:
        """掃描所有被追蹤 device，偵測 drift 並重寫；隨時更新 detail 以保留部分進度。"""
        drift_count = 0
        skipped_by_cooldown = 0
        devices_fixed: list[str] = []
        cooldown_enabled = self._min_rewrite_interval > 0
        now = time.monotonic()

        # 先寫初值，確保即使迴圈中途 raise 也能從 detail 看到 0/空
        detail["drift_count"] = 0
        detail["devices_fixed"] = ()
        if cooldown_enabled:
            detail["skipped_by_cooldown"] = 0

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

                # Invariant: write 失敗時 _last_write_at 不更新，下一 reconcile 仍允許 retry
                # （cooldown 是「成功 audit event」的去抖，不是「最近嘗試」的去抖）
                key = (device_id, point_name)
                if cooldown_enabled:
                    last_at = self._last_write_at.get(key, -math.inf)
                    if now - last_at < self._min_rewrite_interval:
                        skipped_by_cooldown += 1
                        detail["drift_count"] = drift_count
                        detail["skipped_by_cooldown"] = skipped_by_cooldown
                        continue

                ok = await self._router.try_write_single(device_id, point_name, desired)
                if ok:
                    if cooldown_enabled:
                        self._last_write_at[key] = now
                    devices_fixed.append(f"{device_id}.{point_name}")
                    logger.info(
                        f"Setpoint drift fixed: {device_id}.{point_name} actual={actual!r} -> desired={desired!r}"
                    )
                # 每次進度都更新 detail，讓 raise 前的部分結果仍能從 status 觀察到
                detail["drift_count"] = drift_count
                detail["devices_fixed"] = tuple(devices_fixed)

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
