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
    """取得去重鍵：Notification 使用 alarm_key，EventNotification 不去重"""
    if isinstance(item, Notification):
        return item.alarm_key
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
        # 確保所有殘留通知都已發送
        await self.flush()
        logger.info("NotificationBatcher: 已停止")

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
        """強制 flush 佇列中所有通知"""
        async with self._lock:
            items = list(self._queue)
            self._queue.clear()

        if not items:
            return

        # 去重
        if self._config.deduplicate_by_key:
            items = self._deduplicate(items)

        # 分組
        groups = self._group(items)

        # 逐組發送
        for group_items in groups.values():
            await self._send_to_channels(group_items)

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

    async def _send_to_channels(self, items: list[NotificationItem]) -> None:
        """將通知列表發送到所有通道"""
        for channel in self._channels:
            try:
                await channel.send_batch(items)
            except Exception:
                logger.warning(f"NotificationBatcher: 通道 '{channel.name}' 批次發送失敗", exc_info=True)

    # ================ Properties ================

    @property
    def pending_count(self) -> int:
        """佇列中待發送的通知數量"""
        return len(self._queue)

    @property
    def channels(self) -> list[NotificationChannel]:
        """已註冊的通知通道列表"""
        return list(self._channels)


__all__ = [
    "NotificationBatcher",
]
