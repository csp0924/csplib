# =============== Equipment Device - Events ===============
#
# 事件發射器
#
# 提供 Push 模式的事件通知

from __future__ import annotations

import asyncio
import inspect
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from csp_lib.core import get_logger

if TYPE_CHECKING:
    from csp_lib.equipment.alarm import AlarmEvent

logger = get_logger(__name__)

AsyncHandler = Callable[[Any], Awaitable[None]]


class _WeakHandler:
    """WeakRef wrapper for event handlers.

    Holds a weak reference to the handler and checks liveness before invocation.
    Uses ``weakref.WeakMethod`` for bound methods and ``weakref.ref`` for plain
    functions/static methods.

    Limitations:
        Lambdas and closures are technically weak-referenceable, but they
        typically have no persistent referent outside of the calling scope.
        If the caller does not keep a strong reference, the weak reference
        dies immediately after creation and the handler is never invoked.
    """

    __slots__ = ("_ref",)

    def __init__(self, handler: AsyncHandler) -> None:
        if inspect.ismethod(handler):
            self._ref: weakref.ref[Any] = weakref.WeakMethod(handler)
        else:
            self._ref = weakref.ref(handler)

    @property
    def alive(self) -> bool:
        """Return ``True`` if the referent is still alive."""
        return self._ref() is not None

    async def __call__(self, payload: Any) -> None:
        fn = self._ref()
        if fn is not None:
            await fn(payload)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _WeakHandler):
            return self._ref == other._ref
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._ref)


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
EVENT_RECONFIGURED = "reconfigured"
EVENT_RESTARTED = "restarted"
EVENT_POINT_TOGGLED = "point_toggled"


@dataclass(frozen=True)
class ValueChangePayload:
    """值變化事件資料"""

    device_id: str
    point_name: str
    old_value: Any
    new_value: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ConnectedPayload:
    """連線成功事件資料"""

    device_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ReadErrorPayload:
    """讀取錯誤事件資料"""

    device_id: str
    error: str
    consecutive_failures: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class WriteCompletePayload:
    """寫入完成事件資料"""

    device_id: str
    point_name: str
    value: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class WriteErrorPayload:
    """寫入錯誤事件資料"""

    device_id: str
    point_name: str
    value: Any
    error: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class DisconnectPayload:
    """斷線事件資料"""

    device_id: str
    reason: str
    consecutive_failures: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class DeviceAlarmPayload:
    """設備告警事件資料"""

    device_id: str
    alarm_event: AlarmEvent
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ReadCompletePayload:
    """讀取完成事件資料"""

    device_id: str
    values: dict[str, Any]
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ReconfiguredPayload:
    """重新配置事件資料"""

    device_id: str
    changed_sections: tuple[str, ...]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class RestartedPayload:
    """重啟事件資料"""

    device_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class PointToggledPayload:
    """點位開關事件資料"""

    device_id: str
    point_name: str
    enabled: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DeviceEventEmitter:
    """
    設備事件發射器

    使用 asyncio.Queue 進行非阻塞事件處理，避免大量事件阻塞讀取循環。

    支援的事件：
        - connected: 連線成功 (ConnectedPayload)
        - disconnected: 斷線 (DisconnectPayload)
        - read_complete: 讀取完成 (ReadCompletePayload)
        - read_error: 讀取錯誤 (ReadErrorPayload)
        - value_change: 值變化 (ValueChangePayload)
        - alarm_triggered: 告警觸發 (DeviceAlarmPayload)
        - alarm_cleared: 告警解除 (DeviceAlarmPayload)
        - write_complete: 寫入完成 (WriteCompletePayload)
        - write_error: 寫入錯誤 (WriteErrorPayload)

    使用範例：
        emitter = DeviceEventEmitter()
        await emitter.start()  # 啟動 worker

        # 註冊處理器
        async def on_change(payload: ValueChangePayload):
            print(f"{payload.point_name}: {payload.old_value} -> {payload.new_value}")

        cancel = emitter.on("value_change", on_change)

        # 發射事件（非阻塞）
        emitter.emit("value_change", ValueChangePayload(...))

        # 停止
        await emitter.stop()
    """

    _SENTINEL: tuple[str, Any] = ("__stop__", None)
    _DRAIN_TIMEOUT: float = 5.0

    def __init__(self, max_queue_size: int = 10000) -> None:
        """
        初始化事件發射器

        Args:
            max_queue_size: 最大佇列大小，超過時丟棄事件
        """
        self._handlers: dict[str, list[AsyncHandler | _WeakHandler]] = {}
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """啟動事件處理 worker"""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker(), name="event_emitter_worker")

    async def stop(self) -> None:
        """停止 worker，處理剩餘事件後關閉"""
        if not self._running:
            return
        self._running = False

        if self._worker_task:
            # 送 sentinel 通知 worker 排空後結束
            try:
                self._queue.put_nowait(self._SENTINEL)
            except asyncio.QueueFull:
                pass

            # 等待 worker 自行排空（有逾時保護）
            try:
                await asyncio.wait_for(self._worker_task, timeout=self._DRAIN_TIMEOUT)
            except asyncio.TimeoutError:
                remaining = self._queue.qsize()
                if remaining:
                    logger.warning("事件排空逾時，丟棄 {} 筆未處理事件", remaining)
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass

            self._worker_task = None

    def on(self, event: str, handler: AsyncHandler, *, weak: bool = False) -> Callable[[], None]:
        """
        註冊事件處理器

        Args:
            event: 事件名稱
            handler: 非同步處理函數
            weak: 若為 ``True``，以 weak reference 儲存 handler。
                  當 handler 的 referent 被 GC 回收後，自動從處理器列表移除。
                  使用 ``weakref.WeakMethod`` 處理 bound method，
                  ``weakref.ref`` 處理一般函式。
                  **注意**：lambda 和 closure 雖可弱引用，但若呼叫端未保留
                  強引用，弱引用會立即失效，handler 永遠不會被呼叫。

        Returns:
            取消訂閱的函數
        """
        if event not in self._handlers:
            self._handlers[event] = []

        if weak:
            entry: AsyncHandler | _WeakHandler = _WeakHandler(handler)
        else:
            entry = handler

        self._handlers[event].append(entry)

        def cancel() -> None:
            if event in self._handlers and entry in self._handlers[event]:
                self._handlers[event].remove(entry)

        return cancel

    def emit(self, event: str, payload: Any = None) -> None:
        """
        發射事件（非阻塞）

        事件會被放入佇列，由 worker 處理。
        若無監聽器則直接跳過，避免無謂的入隊操作。

        Args:
            event: 事件名稱
            payload: 事件資料
        """
        # 未啟動或沒有監聽器就不入隊
        if not self._running or not self._handlers.get(event):
            return

        try:
            self._queue.put_nowait((event, payload))
        except asyncio.QueueFull:
            logger.warning("事件佇列已滿，丟棄事件: event=%s", event)

    async def emit_await(self, event: str, payload: Any = None) -> None:
        """
        發射事件並等待處理完成（阻塞）

        用於需要確保處理完成的重要事件（如告警、連線狀態）。

        Args:
            event: 事件名稱
            payload: 事件資料
        """
        await self._process_event(event, payload)

    def has_listeners(self, event: str) -> bool:
        """檢查是否有（存活的）事件監聽器"""
        handlers = self._handlers.get(event)
        if not handlers:
            return False
        return any(not isinstance(h, _WeakHandler) or h.alive for h in handlers)

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

    @property
    def queue_size(self) -> int:
        """目前佇列中的事件數量"""
        return self._queue.qsize()

    async def _worker(self) -> None:
        """事件處理 worker"""
        while self._running:
            try:
                event, payload = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                if (event, payload) == self._SENTINEL:
                    self._queue.task_done()
                    break
                await self._process_event(event, payload)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

        # 排空佇列中的剩餘事件
        while not self._queue.empty():
            try:
                event, payload = self._queue.get_nowait()
                if (event, payload) == self._SENTINEL:
                    self._queue.task_done()
                    continue
                await self._process_event(event, payload)
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def _process_event(self, event: str, payload: Any) -> None:
        """
        處理單一事件

        Note: 順序執行 handlers，避免並行造成資源競爭。
        複製 handler list 以防迭代中被修改。
        Dead weak-ref handlers 在此懶清除。
        """
        handlers = list(self._handlers.get(event, []))
        if not handlers:
            return

        # Lazily purge dead weak handlers before iteration
        alive_handlers = [h for h in handlers if not (isinstance(h, _WeakHandler) and not h.alive)]
        if len(alive_handlers) != len(handlers):
            self._handlers[event] = alive_handlers

        for handler in alive_handlers:
            try:
                await handler(payload)
            except Exception:
                logger.opt(exception=True).warning("事件處理失敗: event={}, payload={}", event, repr(payload))


__all__ = [
    "AsyncHandler",
    "ValueChangePayload",
    "ReadCompletePayload",
    "DeviceEventEmitter",
    "ConnectedPayload",
    "DisconnectPayload",
    "ReadErrorPayload",
    "WriteCompletePayload",
    "WriteErrorPayload",
    "DeviceAlarmPayload",
    "ReconfiguredPayload",
    "RestartedPayload",
    "PointToggledPayload",
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
    "EVENT_RECONFIGURED",
    "EVENT_RESTARTED",
    "EVENT_POINT_TOGGLED",
]
