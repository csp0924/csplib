# =============== Equipment Device - Events ===============
#
# 事件發射器
#
# 提供 Push 模式的事件通知

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

from csp_lib.core import get_logger

logger = get_logger(__name__)

AsyncHandler = Callable[[Any], Awaitable[None]]

# 事件名稱常數
EVENT_CONNECTED = "connected"
EVENT_DISCONNECTED = "disconnected"
EVENT_READ_COMPLETE = "read_complete"
EVENT_READ_ERROR = "read_error"
EVENT_VALUE_CHANGE = "value_change"
EVENT_ALARM_TRIGGERED = "alarm_triggered"
EVENT_ALARM_CLEARED = "alarm_cleared"
EVENT_WRITE_COMPLETE = "write_complete"
EVENT_WRITE_ERROR = "write_error"


@dataclass(frozen=True)
class ValueChangePayload:
    """值變化事件資料"""

    point_name: str
    old_value: Any
    new_value: Any
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class DisconnectPayload:
    """斷線事件資料"""

    reason: str
    consecutive_failures: int
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class ReadCompletePayload:
    """讀取完成事件資料"""

    values: dict[str, Any]
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)


class DeviceEventEmitter:
    """
    設備事件發射器

    提供非同步事件訂閱與發射功能。

    支援的事件：
        - connected: 連線成功
        - disconnected: 斷線 (DisconnectPayload)
        - read_complete: 讀取完成 (ReadCompletePayload)
        - read_error: 讀取錯誤 (Exception)
        - value_change: 值變化 (ValueChangePayload)
        - alarm_triggered: 告警觸發 (AlarmEvent)
        - alarm_cleared: 告警解除 (AlarmEvent)

    使用範例：
        emitter = DeviceEventEmitter()

        # 註冊處理器
        async def on_change(payload: ValueChangePayload):
            print(f"{payload.point_name}: {payload.old_value} -> {payload.new_value}")

        cancel = emitter.on("value_change", on_change)

        # 發射事件
        await emitter.emit("value_change", ValueChangePayload(...))

        # 取消訂閱
        cancel()
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[AsyncHandler]] = {}

    def on(self, event: str, handler: AsyncHandler) -> Callable[[], None]:
        """
        註冊事件處理器

        Args:
            event: 事件名稱
            handler: 非同步處理函數

        Returns:
            取消訂閱的函數
        """
        if event not in self._handlers:
            self._handlers[event] = []

        self._handlers[event].append(handler)

        def cancel() -> None:
            if event in self._handlers and handler in self._handlers[event]:
                self._handlers[event].remove(handler)

        return cancel

    async def emit(self, event: str, payload: Any = None) -> None:
        """
        發射事件

        Args:
            event: 事件名稱
            payload: 事件資料
        """
        handlers = self._handlers.get(event, [])
        if not handlers:
            return

        # 並行執行所有處理器
        results = await asyncio.gather(
            *(handler(payload) for handler in handlers),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.warning("事件處理失敗: event={}, payload={}", event, repr(payload), exc_info=result)

    def has_listeners(self, event: str) -> bool:
        """檢查是否有事件監聽器"""
        return bool(self._handlers.get(event))

    def clear(self, event: str | None = None) -> None:
        """
        清除事件處理器

        Args:
            event: 事件名稱，None 表示清除所有
        """
        if event is None:
            self._handlers.clear()
        elif event in self._handlers:
            del self._handlers[event]


__all__ = [
    "AsyncHandler",
    "ValueChangePayload",
    "DisconnectPayload",
    "ReadCompletePayload",
    "DeviceEventEmitter",
    # Event names
    "EVENT_CONNECTED",
    "EVENT_DISCONNECTED",
    "EVENT_READ_COMPLETE",
    "EVENT_READ_ERROR",
    "EVENT_VALUE_CHANGE",
    "EVENT_ALARM_TRIGGERED",
    "EVENT_ALARM_CLEARED",
    "EVENT_WRITE_COMPLETE",
    "EVENT_WRITE_ERROR",
]
