# =============== Equipment Transport - Periodic Sender ===============
#
# 定期發送排程器
#
# 為每個 CAN ID 建立獨立的 asyncio.Task，按週期發送 buffer 最新內容。

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

from csp_lib.core import get_logger
from csp_lib.core._time_anchor import next_tick_delay

if TYPE_CHECKING:
    from csp_lib.equipment.processing.can_encoder import CANFrameBuffer

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PeriodicFrameConfig:
    """
    定期發送配置

    Attributes:
        can_id: CAN 訊框 ID
        interval: 發送間隔（秒）
        enabled: 是否啟用
    """

    can_id: int
    interval: float = 0.1
    enabled: bool = True


class PeriodicSendScheduler:
    """
    定期發送排程器

    為每個 CAN ID 建立獨立的 asyncio.Task，按週期從 frame_buffer 取得最新內容並發送。
    支持暫停/恢復/立即發送。

    使用範例::

        scheduler = PeriodicSendScheduler(
            frame_buffer=buffer,
            send_callback=client.send,
            configs=[PeriodicFrameConfig(can_id=0x200, interval=0.1)],
        )
        await scheduler.start()
        # ... 使用中 ...
        await scheduler.stop()
    """

    def __init__(
        self,
        frame_buffer: CANFrameBuffer,
        send_callback: Callable[[int, bytes], Awaitable[None]],
        configs: list[PeriodicFrameConfig],
    ) -> None:
        self._frame_buffer = frame_buffer
        self._send_callback = send_callback
        self._configs = {cfg.can_id: cfg for cfg in configs}
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._paused: set[int] = set()
        self._running = False

    async def start(self) -> None:
        """啟動所有定期發送任務"""
        if self._running:
            return
        self._running = True
        for can_id, cfg in self._configs.items():
            if cfg.enabled:
                self._tasks[can_id] = asyncio.create_task(
                    self._send_loop(can_id, cfg.interval),
                    name=f"periodic_sender_0x{can_id:03X}",
                )

    async def stop(self) -> None:
        """停止所有定期發送任務"""
        if not self._running:
            return
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    def pause(self, can_id: int) -> None:
        """暫停指定 CAN ID 的定期發送"""
        self._paused.add(can_id)

    def resume(self, can_id: int) -> None:
        """恢復指定 CAN ID 的定期發送"""
        self._paused.discard(can_id)

    async def send_now(self, can_id: int) -> None:
        """立即發送指定 CAN ID 的訊框"""
        data = self._frame_buffer.get_frame(can_id)
        await self._send_callback(can_id, data)

    async def _send_loop(self, can_id: int, interval: float) -> None:
        """單一 CAN ID 的發送循環。

        採用絕對時間錨定（absolute time anchoring）避免時序漂移：
        以 ``next_tick_delay`` helper 統一計算 sleep delay，補償 send_callback 耗時；
        exception 路徑保持固定 interval 避免緊迴圈並重新錨定。
        """
        anchor = time.monotonic()
        n = 0
        while self._running:
            try:
                if can_id not in self._paused:
                    data = self._frame_buffer.get_frame(can_id)
                    await self._send_callback(can_id, data)
                delay, anchor, n = next_tick_delay(anchor, n, interval)
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.opt(exception=True).warning("定期發送失敗: can_id=0x{:03X}", can_id)
                # 錯誤後保持 fixed interval 避免緊迴圈，並重新錨定
                await asyncio.sleep(interval)
                anchor = time.monotonic()
                n = 0


__all__ = [
    "PeriodicFrameConfig",
    "PeriodicSendScheduler",
]
