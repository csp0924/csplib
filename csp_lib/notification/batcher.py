# =============== Notification - Batcher ===============
#
# 批次通知管理器
#
# 收集通知並以防抖方式批次發送：
#   - NotificationBatcher: 批次通知管理器（AsyncLifecycleMixin）

from __future__ import annotations

import asyncio
from collections import deque
from typing import Callable, Sequence

from csp_lib.core import AsyncLifecycleMixin, get_logger

from .base import Notification, NotificationChannel
from .batch_config import BatchNotificationConfig
from .event import EventNotification, NotificationItem

logger = get_logger(__name__)


def _default_group_key(item: NotificationItem) -> str:
    """預設分組鍵：依等級/事件類型或事件分類分組"""
    if isinstance(item, Notification):
        return f"alarm:{item.level.value}:{item.event.value}"
    return f"event:{item.category.value}"


def _dedup_key(item: NotificationItem) -> str | None:
    """取得去重鍵：Notification 使用 (alarm_key, event)，EventNotification 不去重

    Note:
        必須包含 event，否則同 alarm_key 的 TRIGGERED 與 RESOLVED 在同一 flush
        window 內會互蓋，operator 會錯過告警觸發事件。
    """
    if isinstance(item, Notification):
        return f"{item.alarm_key}:{item.event.value}"
    return None


class NotificationBatcher(AsyncLifecycleMixin):
    """
    批次通知管理器

    收集通知到內部佇列，以防抖時間窗（預設 5 秒）批次發送。
    遵循 MongoBatchUploader 的 flush loop 模式。

    Features:
        - 定期 flush（flush_interval）
        - 閾值 flush（batch_size_threshold）
        - 同一時間窗內相同 alarm_key 去重（保留最新）
        - 分組發送（依 level:event 或 category 分組）
        - 立即發送模式（dispatch_immediate / immediate event）

    Example:
        ```python
        batcher = NotificationBatcher(channels=[line_channel, email_channel])
        async with batcher:
            await batcher.dispatch(notification)  # 進入佇列
            await batcher.dispatch_immediate(urgent)  # 立即發送
        ```
    """

    def __init__(
        self,
        channels: Sequence[NotificationChannel],
        config: BatchNotificationConfig | None = None,
        group_key_fn: Callable[[NotificationItem], str] | None = None,
    ) -> None:
        """
        初始化批次通知管理器

        Args:
            channels: 通知通道列表
            config: 批次配置（可選，預設使用 BatchNotificationConfig()）
            group_key_fn: 自訂分組函式（可選，預設依 level:event / category 分組）
        """
        self._channels = list(channels)
        self._config = config or BatchNotificationConfig()
        self._group_key_fn = group_key_fn or _default_group_key
        self._queue: deque[NotificationItem] = deque(maxlen=self._config.max_queue_size)
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._flush_task: asyncio.Task[None] | None = None
        # H2 可觀測性：最近一次 flush 中失敗的 channel 清單（per-channel 去重後保留最後一筆錯誤）
        # count 由 property derive；attempts 另外記錄
        self._last_flush_failures: list[tuple[str, str]] = []
        # 最近一次 flush 中 channel send 失敗的 attempt 次數（同 channel 跨多個 group 會累加）
        self._last_flush_failure_attempts: int = 0

    # ================ Lifecycle ================

    async def _on_start(self) -> None:
        """啟動 flush 迴圈"""
        self._stop_event.clear()
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("NotificationBatcher: 已啟動")

    async def _on_stop(self) -> None:
        """停止 flush 迴圈，最終 flush 所有殘留通知"""
        self._stop_event.set()
        if self._flush_task:
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        # 對殘留通知做一次最終 flush；channel 失敗會走 aggregate ERROR log（不再 retry）
        await self._final_flush()
        logger.info("NotificationBatcher: 已停止")

    async def _final_flush(self) -> None:
        """停止時的最終 flush，並對 channel 失敗做 aggregate ERROR 通報

        Note:
            原本的 try/except + sleep + retry 結構在 _send_to_channels 改成
            collect-and-aggregate 之後其實永遠 unreachable（flush() 不會 raise），
            因此移除 dead code。改用「flush 後檢查失敗計數」走顯式的可觀測路徑。

            pending 計數在 _lock 內取，避免與 shutdown 期間殘留的 dispatch() race。
        """
        async with self._lock:
            pending = len(self._queue)
        if pending == 0:
            return
        await self.flush()
        if self._last_flush_failures:
            failure_summary = ", ".join(f"{name}: {err}" for name, err in self._last_flush_failures)
            logger.error(
                "NotificationBatcher: 停止時 flush 完成但 {failure_count} 個 channel 失敗，"
                "{pending} 則通知未送達到失敗 channel（failures={failure_summary}）",
                failure_count=len(self._last_flush_failures),
                pending=pending,
                failure_summary=failure_summary,
            )

    # ================ Public API ================

    async def dispatch(self, notification: Notification) -> None:
        """
        將通知加入批次佇列

        與 NotificationDispatcher.dispatch() 相同簽名，
        滿足 NotificationSender 協議。

        Args:
            notification: 通知資料
        """
        async with self._lock:
            self._queue.append(notification)

        if len(self._queue) >= self._config.batch_size_threshold:
            await self.flush()

    async def dispatch_event(self, event: EventNotification) -> None:
        """
        發送事件通知

        若 event.immediate 為 True，立即發送；否則加入佇列。

        Args:
            event: 事件通知
        """
        if event.immediate:
            await self._send_to_channels([event])
            return

        async with self._lock:
            self._queue.append(event)

        if len(self._queue) >= self._config.batch_size_threshold:
            await self.flush()

    async def dispatch_immediate(self, notification: Notification) -> None:
        """
        立即發送通知（繞過佇列）

        Args:
            notification: 通知資料
        """
        await self._send_to_channels([notification])

    async def flush(self) -> None:
        """強制 flush 佇列中所有通知

        Note:
            single flush 視為一次 batch operation：``last_flush_failures`` 反映本次 flush
            **獨特** 失敗 channel（per channel name 去重，保留最後一筆 error message）。
            ``last_flush_failure_attempts`` 則記錄 channel send attempt 失敗總次數
            （同一 channel 在多個 group 都失敗會累加），方便區分「N 個 channel 掛」與
            「1 個 channel 掛 N 次」。
            若有任一 channel 失敗，會 emit 一筆 aggregate WARNING，
            避免 caller 看不到「silent 模式下 channel 全掛」的情況。
        """
        async with self._lock:
            items = list(self._queue)
            self._queue.clear()

        # 以 channel name 為 key 去重，保留最後一筆 error message
        per_channel_failures: dict[str, str] = {}
        attempt_count = 0
        self._last_flush_failures = []
        self._last_flush_failure_attempts = 0

        if not items:
            return

        if self._config.deduplicate_by_key:
            items = self._deduplicate(items)

        groups = self._group(items)

        for group_items in groups.values():
            for channel_name, err in await self._send_to_channels(group_items):
                per_channel_failures[channel_name] = err
                attempt_count += 1

        self._last_flush_failures = list(per_channel_failures.items())
        self._last_flush_failure_attempts = attempt_count

        if per_channel_failures:
            failure_summary = ", ".join(f"{name}: {err}" for name, err in per_channel_failures.items())
            logger.warning(
                "NotificationBatcher: flush 期間 {failure_count} 個 channel 發送失敗 "
                "({attempts} 次 attempt) ({failure_summary})",
                failure_count=len(per_channel_failures),
                attempts=attempt_count,
                failure_summary=failure_summary,
            )

    # ================ Flush Loop ================

    async def _flush_loop(self) -> None:
        """定期 flush 迴圈（遵循 MongoBatchUploader 模式）"""
        while not self._stop_event.is_set():
            try:
                # 等待 flush_interval 或收到停止信號
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._config.flush_interval,
                    )
                    # stop_event 被設定，結束前 flush
                    await self.flush()
                    break
                except asyncio.TimeoutError:
                    await self.flush()

            except asyncio.CancelledError:
                await self.flush()
                break
            except Exception as e:
                logger.error(f"NotificationBatcher: flush loop 錯誤: {e}")
                await asyncio.sleep(1)

    # ================ Internal ================

    def _deduplicate(self, items: list[NotificationItem]) -> list[NotificationItem]:
        """
        去重：相同 alarm_key 僅保留最新一則

        EventNotification 不參與去重，全部保留。
        """
        seen: dict[str, int] = {}
        result: list[NotificationItem] = []

        for item in items:
            key = _dedup_key(item)
            if key is None:
                # EventNotification，不去重
                result.append(item)
            elif key in seen:
                # 替換為更新的
                result[seen[key]] = item
            else:
                seen[key] = len(result)
                result.append(item)

        return result

    def _group(self, items: list[NotificationItem]) -> dict[str, list[NotificationItem]]:
        """依 group_key_fn 分組"""
        groups: dict[str, list[NotificationItem]] = {}
        for item in items:
            key = self._group_key_fn(item)
            groups.setdefault(key, []).append(item)
        return groups

    async def _send_to_channels(self, items: list[NotificationItem]) -> list[tuple[str, str]]:
        """將通知列表發送到所有通道

        Per-channel exception 仍然被 swallow（保持 `dispatch()` happy-path 不 raise 的契約），
        但會將每筆失敗收集成 ``(channel_name, error_repr)`` 並 return 給呼叫方做 aggregate 處理。

        Returns:
            list of ``(channel_name, error_str)`` for channels that raised during this send.
        """
        failures: list[tuple[str, str]] = []
        for channel in self._channels:
            try:
                await channel.send_batch(items)
            except Exception as exc:
                logger.opt(exception=True).warning(f"NotificationBatcher: 通道 '{channel.name}' 批次發送失敗")
                failures.append((channel.name, repr(exc)))
        return failures

    # ================ Properties ================

    @property
    def pending_count(self) -> int:
        """佇列中待發送的通知數量"""
        return len(self._queue)

    @property
    def channels(self) -> list[NotificationChannel]:
        """已註冊的通知通道列表"""
        return list(self._channels)

    @property
    def last_flush_failure_count(self) -> int:
        """最近一次 flush() 失敗的 channel 計數

        Note:
            僅追蹤透過 ``flush()`` 走的批次發送；``dispatch_immediate`` 與
            ``dispatch_event(immediate=True)`` 等 bypass 路徑不會更新此值。
        """
        return len(self._last_flush_failures)

    @property
    def last_flush_failures(self) -> list[tuple[str, str]]:
        """最近一次 flush() 失敗清單：``[(channel_name, error_repr), ...]``

        Per channel name 去重，每個 channel 最多出現一次（保留最後一筆 error message）。
        """
        return list(self._last_flush_failures)

    @property
    def last_flush_failure_attempts(self) -> int:
        """最近一次 flush() 中 channel send 失敗的 attempt 總次數

        Note:
            同一個 channel 在多個 group 都失敗會累加。與 ``last_flush_failure_count``
            的差異：前者算「獨特失敗 channel」，此值算「失敗 attempt 次數」。
        """
        return self._last_flush_failure_attempts


__all__ = [
    "NotificationBatcher",
]
