# =============== Core - Reconciler Protocol ===============
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

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from loguru import logger as _root_logger

logger = _root_logger.bind(module=__name__)


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


class ReconcilerMixin:
    """共用 ``reconcile_once`` scaffold：

      - 遞增 ``_run_count``
      - 呼叫子類 ``_reconcile_work(detail)``；把 mutable dict 傳進去，
        子類邊做邊寫入（例如 drift_count / devices_fixed / paused）
      - 吞 Exception 並記錄於 ``last_error``；CancelledError 仍傳播
      - **detail 無論 work 成功或失敗都會快照**，子類在 raise 前寫入的
        部分進度不會被丟掉（支援偵錯與 partial failure 觀察）
      - 組裝 ``ReconcilerStatus`` 寫入 ``self._status``

    子類約定：
      - ``__init__`` 呼叫 ``self._init_reconciler(name)``
      - 實作 ``async def _reconcile_work(detail: dict[str, Any]) -> None``
        在 ``detail`` 內記錄本次 diagnostic metadata

    契約：``reconcile_once`` 不得 raise（CancelledError 除外）。
    """

    _name: str
    _run_count: int
    _status: ReconcilerStatus

    def _init_reconciler(self, name: str) -> None:
        self._name = name
        self._run_count = 0
        self._status = ReconcilerStatus.empty(name)

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> ReconcilerStatus:
        return self._status

    async def _reconcile_work(self, detail: dict[str, Any]) -> None:
        """子類必須覆寫；把 diagnostic metadata 寫入傳入的 detail dict。"""
        raise NotImplementedError

    async def reconcile_once(self) -> ReconcilerStatus:
        return await _run_reconcile_scaffold(self, self._reconcile_work)


async def _run_reconcile_scaffold(
    holder: ReconcilerMixin,
    work: Callable[[dict[str, Any]], Awaitable[None]],
) -> ReconcilerStatus:
    """ReconcilerMixin.reconcile_once 的純實作（獨立函式便於 unit test）。"""
    holder._run_count += 1
    last_error: str | None = None
    detail: dict[str, Any] = {}
    try:
        await work(detail)
    except asyncio.CancelledError:
        # 不更新 status（對齊原行為）；CancelledError 必須傳播
        raise
    except Exception as e:
        last_error = repr(e)
        # 動態綁定實際 holder 的 module 而非 core.reconciler，讓 module-based
        # log filter / set_level 可精準控制實作來源（如 manager.schedule.service）。
        _holder_logger = _root_logger.bind(module=type(holder).__module__, reconciler_module=__name__)
        _holder_logger.opt(exception=True).warning(f"{type(holder).__name__}.reconcile_once raised, captured in status")

    # 成功或 non-cancel 失敗都會到這；detail 是子類在 work 執行過程（含 raise 前）
    # 寫入的 diagnostic metadata，失敗時保留部分進度供偵錯
    holder._status = ReconcilerStatus(
        name=holder._name,
        last_run_at=time.monotonic(),
        last_error=last_error,
        run_count=holder._run_count,
        healthy=last_error is None,
        detail=MappingProxyType(dict(detail)),
    )
    return holder._status


__all__ = [
    "Reconciler",
    "ReconcilerMixin",
    "ReconcilerStatus",
]
