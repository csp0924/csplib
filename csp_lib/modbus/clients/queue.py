# =============== Modbus Request Queue ===============
#
# 請求佇列 + 背景 Worker 模式
#
# 取代 asyncio.Lock，提供：
#   - 優先權排程 (寫入優先於讀取)
#   - 公平的 round-robin 跨 unit_id 排程
#   - 每個請求的逾時控制
#   - 每個 unit_id 的斷路器 (circuit breaker)

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from heapq import heappop, heappush
from typing import Any, Callable, Coroutine

from csp_lib.core.resilience import CircuitBreaker, CircuitState

from ..exceptions import ModbusCircuitBreakerError, ModbusError, ModbusQueueFullError


@dataclass(frozen=True)
class RequestQueueConfig:
    """
    請求佇列設定

    Args:
        default_timeout: 每個請求的預設逾時 (秒)
        circuit_breaker_threshold: 連續失敗次數達到此值後觸發斷路器
        circuit_breaker_cooldown: 斷路器開啟後的冷卻時間 (秒)
        max_queue_size: 佇列最大容量 (0 = 無限制)
        drain_timeout: 關閉時等待佇列排空的逾時 (秒)
    """

    default_timeout: float = 5.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown: float = 30.0
    max_queue_size: int = 1000
    drain_timeout: float = 10.0


class RequestPriority(IntEnum):
    """請求優先權 (數值越小優先權越高)"""

    WRITE = 0
    READ = 1


@dataclass
class ModbusRequest:
    """
    佇列中的 Modbus 請求

    Args:
        priority: 請求優先權
        unit_id: 設備位址
        coroutine_factory: 產生新 coroutine 的工廠函式
        future: 用於回傳結果的 Future
        timeout: 此請求的逾時 (秒)，None 使用預設值
        enqueue_time: 加入佇列的時間戳
        sequence: 全域序號，用於同優先權時的 FIFO 排序
    """

    priority: RequestPriority
    unit_id: int
    coroutine_factory: Callable[[], Coroutine[Any, Any, Any]]
    future: asyncio.Future[Any]
    timeout: float | None
    enqueue_time: float
    sequence: int

    def __lt__(self, other: ModbusRequest) -> bool:
        """用於 heapq 比較：先比優先權，再比序號"""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.sequence < other.sequence


# 向後相容別名：CircuitBreakerState → CircuitState
CircuitBreakerState = CircuitState


class UnitCircuitBreaker(CircuitBreaker):
    """
    每個 unit_id 的斷路器

    薄包裝 Core 層的 CircuitBreaker，保留向後相容 API。
    """

    pass


class ModbusRequestQueue:
    """
    Modbus 請求佇列

    使用背景 worker 逐一處理請求，提供：
    - 優先權排程 (WRITE > READ)
    - 公平的 round-robin 跨 unit_id
    - 每個請求逾時
    - 每個 unit_id 斷路器
    """

    def __init__(self, config: RequestQueueConfig | None = None) -> None:
        self._config = config or RequestQueueConfig()
        self._unit_queues: dict[int, list[ModbusRequest]] = {}
        self._round_robin: deque[int] = deque()
        self._circuit_breakers: dict[int, UnitCircuitBreaker] = {}
        self._sequence = 0
        self._total_size = 0
        self._event = asyncio.Event()
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False
        self._lock = asyncio.Lock()

    @property
    def total_size(self) -> int:
        """佇列中的總請求數"""
        return self._total_size

    def _get_circuit_breaker(self, unit_id: int) -> UnitCircuitBreaker:
        """取得或建立指定 unit_id 的斷路器"""
        if unit_id not in self._circuit_breakers:
            self._circuit_breakers[unit_id] = UnitCircuitBreaker(
                threshold=self._config.circuit_breaker_threshold,
                cooldown=self._config.circuit_breaker_cooldown,
            )
        return self._circuit_breakers[unit_id]

    async def submit(
        self,
        unit_id: int,
        priority: RequestPriority,
        coroutine_factory: Callable[[], Coroutine[Any, Any, Any]],
        timeout: float | None = None,
    ) -> Any:
        """
        提交請求到佇列

        Args:
            unit_id: 設備位址
            priority: 請求優先權
            coroutine_factory: 產生 coroutine 的工廠函式
            timeout: 此請求的逾時 (秒)，None 使用預設值

        Returns:
            Modbus 操作的結果

        Raises:
            ModbusQueueFullError: 佇列已滿
            ModbusCircuitBreakerError: 斷路器開啟
            ModbusError: 佇列未啟動
            asyncio.TimeoutError: 請求逾時
        """
        if not self._running:
            raise ModbusError("Request queue is not running")

        cb = self._get_circuit_breaker(unit_id)
        if not cb.allows_request():
            raise ModbusCircuitBreakerError(unit_id)

        if self._config.max_queue_size > 0 and self._total_size >= self._config.max_queue_size:
            raise ModbusQueueFullError(f"Request queue is full (max_size={self._config.max_queue_size})")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()

        async with self._lock:
            self._sequence += 1
            request = ModbusRequest(
                priority=priority,
                unit_id=unit_id,
                coroutine_factory=coroutine_factory,
                future=future,
                timeout=timeout,
                enqueue_time=time.monotonic(),
                sequence=self._sequence,
            )

            if unit_id not in self._unit_queues:
                self._unit_queues[unit_id] = []
                self._round_robin.append(unit_id)

            heappush(self._unit_queues[unit_id], request)
            self._total_size += 1

        self._event.set()

        effective_timeout = timeout if timeout is not None else self._config.default_timeout
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=effective_timeout)
        except asyncio.TimeoutError:
            future.cancel()
            raise

    async def start(self) -> None:
        """啟動背景 worker"""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """停止背景 worker 並排空佇列"""
        if not self._running:
            return
        self._running = False
        self._event.set()

        if self._worker_task is not None:
            try:
                await asyncio.wait_for(self._worker_task, timeout=self._config.drain_timeout)
            except asyncio.TimeoutError:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
            self._worker_task = None

        # 取消所有剩餘的請求
        async with self._lock:
            for unit_id in list(self._unit_queues.keys()):
                for request in self._unit_queues[unit_id]:
                    if not request.future.done():
                        request.future.cancel()
                self._unit_queues[unit_id].clear()
            self._unit_queues.clear()
            self._round_robin.clear()
            self._total_size = 0

    async def _worker(self) -> None:
        """背景 worker：逐一處理佇列中的請求"""
        while self._running or self._total_size > 0:
            request = await self._dequeue()
            if request is None:
                if not self._running:
                    break
                self._event.clear()
                await self._event.wait()
                continue

            if request.future.cancelled() or request.future.done():
                continue

            effective_timeout = request.timeout if request.timeout is not None else self._config.default_timeout

            # 跳過在 queue 中已過期的請求
            elapsed = time.monotonic() - request.enqueue_time
            if elapsed >= effective_timeout:
                if not request.future.done():
                    request.future.cancel()
                continue

            cb = self._get_circuit_breaker(request.unit_id)

            # 再次檢查斷路器 (可能在排隊期間變為 OPEN)
            if not cb.allows_request():
                if not request.future.done():
                    request.future.set_exception(ModbusCircuitBreakerError(request.unit_id))
                continue

            try:
                coro = request.coroutine_factory()
                remaining = effective_timeout - elapsed
                worker_timeout = max(remaining, 0.5)  # 最低 0.5s，對齊 pymodbus wire timeout
                result = await asyncio.wait_for(coro, timeout=worker_timeout)
                cb.record_success()
                if not request.future.done():
                    request.future.set_result(result)
            except Exception as exc:
                cb.record_failure()
                if not request.future.done():
                    request.future.set_exception(exc)

    async def _dequeue(self) -> ModbusRequest | None:
        """
        公平排程：round-robin + 優先權選擇

        1. 掃描所有 unit_id (round-robin 順序)
        2. 跳過斷路器 OPEN 的 unit
        3. 選擇最高優先權的請求；同優先權時以 round-robin 位置決勝
        4. 彈出請求，將已服務的 unit 移到 deque 尾端
        """
        async with self._lock:
            if not self._round_robin:
                return None

            best_request: ModbusRequest | None = None
            best_unit_id: int | None = None
            best_index: int | None = None
            stale_units: list[int] = []

            for i, unit_id in enumerate(self._round_robin):
                queue = self._unit_queues.get(unit_id)
                if not queue:
                    stale_units.append(unit_id)
                    continue

                # 清理 heap 頂部已取消或已完成的 request
                while queue and (queue[0].future.cancelled() or queue[0].future.done()):
                    heappop(queue)
                    self._total_size -= 1

                if not queue:
                    stale_units.append(unit_id)
                    continue

                cb = self._get_circuit_breaker(unit_id)
                if not cb.allows_request():
                    continue

                # Peek 最高優先權項目
                candidate = queue[0]
                # 跨 unit 只比較優先權，同優先權以 round-robin 位置決勝
                if best_request is None or candidate.priority < best_request.priority:
                    best_request = candidate
                    best_unit_id = unit_id
                    best_index = i

            # 清理空的 unit 佇列
            for uid in stale_units:
                if uid in self._unit_queues:
                    del self._unit_queues[uid]
                if uid in self._round_robin:
                    self._round_robin.remove(uid)

            if best_request is None or best_unit_id is None or best_index is None:
                return None

            # 彈出選中的請求
            heappop(self._unit_queues[best_unit_id])
            self._total_size -= 1

            # 清理空佇列
            if not self._unit_queues[best_unit_id]:
                del self._unit_queues[best_unit_id]
                self._round_robin.remove(best_unit_id)
            else:
                # 已服務的 unit 移到尾端
                self._round_robin.remove(best_unit_id)
                self._round_robin.append(best_unit_id)

            return best_request


__all__ = [
    "RequestQueueConfig",
    "RequestPriority",
    "ModbusRequest",
    "CircuitBreakerState",
    "UnitCircuitBreaker",
    "ModbusRequestQueue",
]
