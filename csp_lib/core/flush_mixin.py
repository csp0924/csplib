"""背景定期 flush 迴圈的共用 Mixin（internal，不匯出到 public API）"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class BackgroundFlushMixin:
    """
    背景定期 flush 迴圈的共用 Mixin。

    提供 start/stop flush loop 的骨架，子類別覆寫：
    - _flush_once(): 單次 flush 邏輯
    - _on_flush_error(exc): flush 失敗處理（預設 log warning）
    - _flush_interval: flush 間隔（秒）

    搭配 AsyncLifecycleMixin 使用：在 _on_start/_on_stop 中
    呼叫 _start_flush_loop() / _stop_flush_loop()。
    """

    _flush_interval: float
    _flush_task: asyncio.Task[None] | None
    _flush_stop_event: asyncio.Event

    def _start_flush_loop(self) -> None:
        """啟動 flush 背景任務"""
        self._flush_stop_event = asyncio.Event()
        self._flush_task = asyncio.create_task(self._run_flush_loop())

    async def _stop_flush_loop(self) -> None:
        """停止 flush 並執行最終 flush"""
        self._flush_stop_event.set()
        if self._flush_task is not None:
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        await self._final_flush()

    async def _run_flush_loop(self) -> None:
        """flush 迴圈主體"""
        while not self._flush_stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._flush_stop_event.wait(),
                    timeout=self._flush_interval,
                )
                break  # stop event set
            except TimeoutError:
                pass
            try:
                await self._flush_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._on_flush_error(exc)

    async def _flush_once(self) -> None:
        """單次 flush 邏輯（子類別必須覆寫）"""
        raise NotImplementedError

    async def _on_flush_error(self, exc: Exception) -> None:
        """flush 失敗處理（子類別可覆寫）"""
        logger.warning("Flush error: %s", exc)

    async def _final_flush(self) -> None:
        """停止時的最終 flush（預設呼叫一次 _flush_once，子類別可覆寫加重試等）"""
        try:
            await self._flush_once()
        except Exception as exc:
            logger.warning("Final flush error: %s", exc)
