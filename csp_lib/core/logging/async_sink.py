# =============== Core - Logging - Async Sink ===============
#
# 非同步 Sink 轉接器
#
# 將 async handler 包裝為同步 write 介面，供 loguru 使用：
#   - AsyncSinkAdapter: 透過 queue + event loop 橋接

from __future__ import annotations

import asyncio
import queue
import threading
from typing import Awaitable, Callable


class AsyncSinkAdapter:
    """非同步 Sink 轉接器。

    將 async handler 包裝為 loguru 可用的同步 ``write`` 方法。
    內部使用 thread-safe queue 緩衝訊息，並在指定 event loop 上排程執行。

    Attributes:
        _async_handler: 使用者提供的 async handler。
        _loop: 目標 event loop。
        _queue: 訊息佇列。
        _max_queue_size: 佇列上限。
        _flush_timeout: close 時等待清空的超時秒數。
        _closed: 是否已關閉。

    Example:
        ```python
        async def send_to_remote(msg: str) -> None:
            await http_client.post("/logs", data=msg)

        adapter = AsyncSinkAdapter(send_to_remote, max_queue_size=5000)
        logger.add(adapter.write, format="{message}")
        ```
    """

    def __init__(
        self,
        async_handler: Callable[[str], Awaitable[None]],
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        max_queue_size: int = 10000,
        flush_timeout: float = 5.0,
    ) -> None:
        self._async_handler = async_handler
        self._loop = loop
        self._max_queue_size = max_queue_size
        self._flush_timeout = flush_timeout
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=max_queue_size)
        self._closed = False
        self._drain_task: asyncio.Task[None] | None = None
        self._lock = threading.Lock()

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """取得目標 event loop。

        Returns:
            asyncio event loop 實例。

        Raises:
            RuntimeError: 找不到 running loop。
        """
        if self._loop is not None:
            return self._loop
        return asyncio.get_event_loop()

    def write(self, message: str) -> None:
        """同步寫入介面，將訊息放入佇列。

        當佇列滿時，靜默丟棄訊息以避免阻塞 logger。

        Args:
            message: 格式化後的 log 訊息。
        """
        if self._closed:
            return
        try:
            self._queue.put_nowait(message)
        except queue.Full:
            pass  # 佇列滿時靜默丟棄，避免阻塞

        # 確保 drain task 在運行
        self._ensure_drain_running()

    def _ensure_drain_running(self) -> None:
        """確保 drain task 正在執行。"""
        with self._lock:
            if self._drain_task is not None and not self._drain_task.done():
                return
            try:
                loop = self._get_loop()
                if loop.is_running():
                    self._drain_task = loop.create_task(self._drain())
            except RuntimeError:
                pass  # 沒有 running loop，等下次 write 再試

    async def _drain(self) -> None:
        """從佇列取出訊息並交給 async handler 處理。"""
        while not self._closed or not self._queue.empty():
            try:
                message = self._queue.get_nowait()
            except queue.Empty:
                if self._closed:
                    break
                await asyncio.sleep(0.01)
                continue

            if message is None:
                break

            try:
                await self._async_handler(message)
            except Exception:  # noqa: BLE001
                pass  # handler 錯誤不應影響日誌系統

    async def close(self) -> None:
        """關閉轉接器，等待佇列清空。

        等待不超過 ``flush_timeout`` 秒。超時後強制關閉。
        """
        self._closed = True
        # 放入 sentinel 值通知 drain 結束
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        if self._drain_task is not None and not self._drain_task.done():
            try:
                await asyncio.wait_for(self._drain_task, timeout=self._flush_timeout)
            except (TimeoutError, asyncio.CancelledError):
                self._drain_task.cancel()


__all__: list[str] = [
    "AsyncSinkAdapter",
]
