# =============== Integration - Command Refresh Service ===============
#
# 命令刷新（Reconciler）服務
#
# CommandRefreshService 以固定週期把 ``CommandRouter`` 追蹤的「desired
# state」（最近一次成功寫入的命令值）重新寫回設備，達成 Kubernetes 風格
# 的 reconciler 模型：
#
#   desired state  =  CommandRouter._last_written
#   actual state   =  設備端目前實際狀態（可能被斷線 / 重啟 / 外部干預改動）
#   reconcile      =  週期把 desired state 重寫回 actual state
#
# 典型使用場景：
#   - 設備短暫斷線後重連，上一輪 Command 可能已被設備端 reset；
#     reconciler 在下一個 tick 把最新的 desired state 重新下推。
#   - Shared Modbus 連線被外部工具寫入後，控制器可藉此把自己的意向重新
#     復位。
#
# 設計重點：
#   - 絕對時間錨定 (next_tick_delay)：避免 phase drift，嚴重落後自動重錨。
#   - Fire-and-forget：呼叫 ``router.try_write_single``，不關心回傳；寫入
#     失敗的 log 由 CommandRouter 自行處理。
#   - NO_CHANGE 不入 desired state：CommandRouter 的 NO_CHANGE 軸跳過寫入，
#     不會污染 ``_last_written``；因此 reconciler 永遠用的是業務值。
#   - device_filter：可限定只 reconcile 特定設備（例如 gateway-facing PCS）。

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from csp_lib.core import AsyncLifecycleMixin, get_logger
from csp_lib.core._time_anchor import next_tick_delay

from .reconciler import ReconcilerMixin

if TYPE_CHECKING:
    from .command_router import CommandRouter

logger = get_logger(__name__)


class CommandRefreshService(ReconcilerMixin, AsyncLifecycleMixin):
    """命令刷新（reconciler）服務

    每 ``interval`` 秒從 ``CommandRouter`` 讀取 desired state，並對每個
    ``(device_id, point_name, value)`` 呼叫 ``router.try_write_single``
    把 desired state 重新推到設備（actual state）。

    Args:
        router: 目標 ``CommandRouter`` 實例；需已啟用 desired-state 追蹤。
        interval: reconcile 週期（秒），必須 > 0。
        device_filter: 若提供，只 reconcile 此集合中的 device_id；``None``
            代表 reconcile 所有被 router 追蹤的設備。

    Raises:
        ValueError: ``interval <= 0``。
    """

    def __init__(
        self,
        router: CommandRouter,
        *,
        interval: float = 1.0,
        device_filter: frozenset[str] | None = None,
        name: str = "command_refresh",
    ) -> None:
        if interval <= 0:
            raise ValueError(f"CommandRefreshService: interval must be > 0, got {interval}")
        self._router = router
        self._interval = interval
        self._device_filter = device_filter

        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

        self._init_reconciler(name)

    # ---- Lifecycle ----

    async def _on_start(self) -> None:
        """啟動 reconcile 迴圈"""
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())
        logger.info(f"CommandRefreshService started (interval={self._interval}s).")

    async def _on_stop(self) -> None:
        """停止 reconcile 迴圈並等待 task 結束"""
        self._stop_event.set()
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("CommandRefreshService stopped.")

    @property
    def is_running(self) -> bool:
        """reconcile task 是否正在執行"""
        return self._task is not None and not self._task.done()

    # ---- Reconciler Protocol ----
    #
    # name / status / reconcile_once 由 ReconcilerMixin 提供；本類只覆寫 work。

    async def _reconcile_work(self, detail: dict[str, Any]) -> None:
        """執行一次 desired → actual 收斂；本類無額外 diagnostic detail。"""
        await self._refresh_once()

    # ---- 內部實作 ----

    async def _run(self) -> None:
        """主迴圈：work-first + 絕對時間錨定

        每個 tick 先執行 ``reconcile_once``（work + 更新 status），再用
        ``next_tick_delay`` 計算到下個 tick 的 sleep 量。遇到 stop_event
        立即中斷。
        """
        anchor = time.monotonic()
        completed = 0

        while not self._stop_event.is_set():
            # reconcile_once 契約：不得對外拋例外
            await self.reconcile_once()

            delay, anchor, completed = next_tick_delay(anchor, completed, self._interval)
            if delay <= 0:
                # 讓出 event loop；同時檢查 stop_event
                await asyncio.sleep(0)
                if self._stop_event.is_set():
                    break
                continue

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                break  # stop_event 被設定 → 離開
            except asyncio.TimeoutError:
                pass  # 正常 tick 時間到

    async def _refresh_once(self) -> None:
        """執行一次 reconcile：把 desired state 重寫回設備"""
        tracked = self._router.get_tracked_device_ids()
        if self._device_filter is not None:
            tracked = tracked & self._device_filter

        for device_id in tracked:
            snapshot = self._router.get_last_written(device_id)
            if not snapshot:
                continue
            for point_name, value in snapshot.items():
                # Fire-and-forget：try_write_single 內部已 log 失敗
                await self._router.try_write_single(device_id, point_name, value)


__all__ = [
    "CommandRefreshService",
]
