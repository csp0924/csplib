# =============== Equipment Device - Event Bridge ===============
#
# 跨設備事件聚合器
#
# 提供低頻跨設備事件聚合（如「所有 PCS 都 connected」→ 觸發系統就緒事件），
# 不取代現有 per-device DeviceEventEmitter。

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Sequence

from csp_lib.core import get_logger

from .events import AsyncHandler

if TYPE_CHECKING:
    from .base import AsyncModbusDevice

logger = get_logger(__name__)


@dataclass(frozen=True)
class AggregateCondition:
    """聚合條件定義"""

    source_event: str  # 監聽的設備事件（如 EVENT_CONNECTED）
    target_event: str  # 聚合後發出的事件名稱
    predicate: Callable[[dict[str, Any]], bool]  # 判斷函式（收到 {device_id: payload} 後）
    debounce_seconds: float = 1.0  # 防抖動秒數


class EventBridge:
    """
    跨設備事件聚合器

    監聽多個設備的事件，當滿足聚合條件（predicate）時，
    發出聚合事件給已註冊的處理器。

    使用範例::

        bridge = EventBridge([
            AggregateCondition(
                source_event=EVENT_CONNECTED,
                target_event="system_ready",
                predicate=lambda payloads: len(payloads) >= 3,
                debounce_seconds=2.0,
            ),
        ])
        bridge.attach(devices)
        bridge.on("system_ready", my_handler)
    """

    def __init__(self, conditions: list[AggregateCondition]):
        self._conditions = conditions
        self._handlers: dict[str, list[AsyncHandler]] = {}
        self._subscriptions: list[Callable[[], None]] = []
        self._latest: dict[str, dict[str, Any]] = {}  # {source_event: {device_id: payload}}
        self._debounce_tasks: dict[str, asyncio.Task[None]] = {}
        self._last_result: dict[str, bool] = {}  # edge-detection：上次 predicate 結果

    def attach(self, devices: Sequence[AsyncModbusDevice]) -> None:
        """訂閱所有設備的事件"""
        for device in devices:
            for cond in self._conditions:
                cancel = device.on(cond.source_event, self._make_handler(cond, device.device_id))
                self._subscriptions.append(cancel)

    def detach(self) -> None:
        """取消所有訂閱並清理"""
        for cancel in self._subscriptions:
            cancel()
        self._subscriptions.clear()

        # 取消所有 debounce tasks
        for task in self._debounce_tasks.values():
            task.cancel()
        self._debounce_tasks.clear()
        self._latest.clear()
        self._last_result.clear()

    def on(self, event: str, handler: AsyncHandler) -> Callable[[], None]:
        """註冊聚合事件處理器"""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

        def cancel() -> None:
            if event in self._handlers and handler in self._handlers[event]:
                self._handlers[event].remove(handler)

        return cancel

    def _make_handler(self, cond: AggregateCondition, device_id: str) -> AsyncHandler:
        """建立帶 edge-detection + debounce 的 handler"""

        async def handler(payload: Any) -> None:
            self._latest.setdefault(cond.source_event, {})[device_id] = payload

            # 取消既有的 debounce task
            key = f"{cond.source_event}:{cond.target_event}"
            existing = self._debounce_tasks.get(key)
            if existing is not None and not existing.done():
                existing.cancel()

            # 建立新的 debounce task
            self._debounce_tasks[key] = asyncio.create_task(self._debounce_check(cond, key))

        return handler

    async def _debounce_check(self, cond: AggregateCondition, key: str) -> None:
        """debounce 結束後檢查 predicate"""
        try:
            await asyncio.sleep(cond.debounce_seconds)
        except asyncio.CancelledError:
            return

        payloads = self._latest.get(cond.source_event, {})
        current_result = cond.predicate(payloads)
        last_result = self._last_result.get(key, False)

        # Edge-detection：僅在狀態從 False → True 時觸發
        if current_result and not last_result:
            self._last_result[key] = True
            await self._emit(cond.target_event, payloads)
        elif not current_result and last_result:
            self._last_result[key] = False

    async def _emit(self, event: str, payload: Any) -> None:
        """發送聚合事件"""
        handlers = self._handlers.get(event, [])
        for handler in handlers:
            try:
                await handler(payload)
            except Exception:
                logger.opt(exception=True).warning("EventBridge handler failed: event={}", event)


__all__ = [
    "AggregateCondition",
    "EventBridge",
]
