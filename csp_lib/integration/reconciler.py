# =============== Integration - Reconciler Protocol ===============
#
# K8s 風 Operator Pattern 基礎 Protocol
#
# Reconciler 定義「把 desired state 往 actual state 收斂一次」的抽象介面。
# 生命週期（start/stop）不在 Protocol 之內，由 AsyncLifecycleMixin 提供。
#
# 命名說明：
#   「Operator Pattern」是設計概念名稱（K8s controller/operator），
#   Protocol 命名為 Reconciler 是因為 csp_lib.equipment.alarm.evaluator
#   已有 public class Operator(Enum) — 避免衝突。

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


def _empty_mapping() -> Mapping[str, Any]:
    # MappingProxyType 本身就是 frozen 的唯讀視圖；每個 default 都分配獨立 view。
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class ReconcilerStatus:
    """Reconciler 單次執行後或當下的觀測狀態。

    對應 K8s ``.status`` subresource：
      - ``name``:        識別用，通常等同 reconciler 實例的 logical name
      - ``last_run_at``: 最近一次 reconcile_once 完成的 monotonic timestamp（秒）
                         None 代表尚未執行過
      - ``last_error``:  最近一次失敗的錯誤摘要（str）；成功則 None
      - ``run_count``:   累積 reconcile_once 呼叫次數
      - ``healthy``:     主觀健康旗標（實作端定義判斷規則）
      - ``detail``:      reconciler-specific 唯讀 Mapping，例如
                         ``{"drift_count": 3, "devices_fixed": ["PCS1"]}``

    規則：
      - frozen + slots → 防突變、零 ``__dict__`` overhead
      - detail 預設為空 read-only Mapping，避免 caller mutate
      - 只存放 diagnostic scalars，不放大型物件（device ref、完整 command 等）
    """

    name: str
    last_run_at: float | None = None
    last_error: str | None = None
    run_count: int = 0
    healthy: bool = True
    detail: Mapping[str, Any] = field(default_factory=_empty_mapping)

    @classmethod
    def empty(cls, name: str) -> ReconcilerStatus:
        """建立尚未 reconcile 過的初始狀態。"""
        return cls(name=name)


@runtime_checkable
class Reconciler(Protocol):
    """K8s 風 Reconciler Protocol。

    契約：
      - ``name``：穩定的 logical identifier（用於 logging / metrics / status）
      - ``reconcile_once()``：執行一次 desired → actual 收斂，回傳 ReconcilerStatus
            * 不得 raise（例外一律 catch 並記錄於回傳的 ``last_error``）
            * idempotent：重複呼叫不應造成額外副作用
      - ``status``：最新狀態的唯讀視圖，不觸發 reconcile

    非契約：
      - 週期性執行由外層迴圈負責（AsyncLifecycleMixin / asyncio.Task）
      - pause/resume 是實作類選配能力，不在 Protocol 之內

    實作範例：CommandRefreshService, HeartbeatService, SetpointDriftReconciler。
    """

    @property
    def name(self) -> str:
        """Reconciler 的穩定識別名，用於 logging 與 status 聚合。"""
        ...

    @property
    def status(self) -> ReconcilerStatus:
        """最新狀態的唯讀視圖（不觸發 reconcile）。"""
        ...

    async def reconcile_once(self) -> ReconcilerStatus:
        """執行一次 desired → actual 收斂。

        Returns:
            本次執行結束的 ReconcilerStatus 快照。

        Contract:
            - 不得 raise（例外一律 catch 後記錄於回傳的 ``last_error``）
            - idempotent（重複呼叫等價於單次呼叫）
        """
        ...


__all__ = [
    "Reconciler",
    "ReconcilerStatus",
]
