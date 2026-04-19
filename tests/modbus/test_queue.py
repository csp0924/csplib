# =============== Modbus Tests - Request Queue ===============
#
# 請求佇列單元測試

from __future__ import annotations

import asyncio
import time
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from csp_lib.modbus.clients.queue import (
    CircuitBreakerState,
    ModbusRequestQueue,
    RequestPriority,
    RequestQueueConfig,
    UnitCircuitBreaker,
)
from csp_lib.modbus.exceptions import (
    ModbusCircuitBreakerError,
    ModbusError,
    ModbusQueueFullError,
)
from tests.helpers import wait_for_condition


class TestRequestQueueConfig:
    """RequestQueueConfig 測試"""

    def test_default_values(self):
        config = RequestQueueConfig()
        assert config.default_timeout == 5.0
        assert config.circuit_breaker_threshold == 5
        assert config.circuit_breaker_cooldown == 30.0
        assert config.max_queue_size == 1000
        assert config.drain_timeout == 10.0

    def test_custom_values(self):
        config = RequestQueueConfig(
            default_timeout=3.0,
            circuit_breaker_threshold=3,
            circuit_breaker_cooldown=15.0,
            max_queue_size=500,
            drain_timeout=5.0,
        )
        assert config.default_timeout == 3.0
        assert config.circuit_breaker_threshold == 3
        assert config.circuit_breaker_cooldown == 15.0
        assert config.max_queue_size == 500
        assert config.drain_timeout == 5.0

    def test_config_is_frozen(self):
        config = RequestQueueConfig()
        with pytest.raises(FrozenInstanceError):
            config.default_timeout = 10.0


class TestRequestPriority:
    """RequestPriority 測試"""

    def test_write_higher_than_read(self):
        assert RequestPriority.WRITE < RequestPriority.READ

    def test_values(self):
        assert RequestPriority.WRITE == 0
        assert RequestPriority.READ == 1


class TestUnitCircuitBreaker:
    """UnitCircuitBreaker 測試"""

    def test_initial_state_is_closed(self):
        cb = UnitCircuitBreaker(threshold=3, cooldown=10.0)
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.allows_request() is True

    def test_stays_closed_below_threshold(self):
        cb = UnitCircuitBreaker(threshold=3, cooldown=10.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.allows_request() is True

    def test_opens_at_threshold(self):
        cb = UnitCircuitBreaker(threshold=3, cooldown=10.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.allows_request() is False

    def test_success_resets_failure_count(self):
        cb = UnitCircuitBreaker(threshold=3, cooldown=10.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        # 2 failures after reset, still below threshold
        assert cb.state == CircuitBreakerState.CLOSED

    def test_open_to_half_open_after_cooldown(self):
        cb = UnitCircuitBreaker(threshold=1, cooldown=0.5)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        with patch("csp_lib.core.resilience.time") as mock_time:
            # Simulate cooldown elapsed (must exceed max backoff with jitter)
            mock_time.monotonic.return_value = time.monotonic() + 5.0
            assert cb.state == CircuitBreakerState.HALF_OPEN
            assert cb.allows_request() is True

    def test_half_open_success_closes(self):
        cb = UnitCircuitBreaker(threshold=1, cooldown=100.0)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        with patch("csp_lib.core.resilience.time") as mock_time:
            # Simulate cooldown elapsed → HALF_OPEN (must exceed max backoff with jitter)
            mock_time.monotonic.return_value = time.monotonic() + 500.0
            assert cb.state == CircuitBreakerState.HALF_OPEN

            cb.record_success()
            assert cb.state == CircuitBreakerState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = UnitCircuitBreaker(threshold=1, cooldown=100.0)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        with patch("csp_lib.core.resilience.time") as mock_time:
            # Simulate cooldown elapsed → HALF_OPEN (must exceed max backoff with jitter)
            mock_time.monotonic.return_value = time.monotonic() + 500.0
            assert cb.state == CircuitBreakerState.HALF_OPEN

            # Failure in HALF_OPEN → back to OPEN
            cb.record_failure()
            # _last_failure_time is now set to mocked value (very far in future)
            # so cooldown hasn't elapsed relative to that new time
            mock_time.monotonic.return_value = time.monotonic() + 200.0
            assert cb.state == CircuitBreakerState.OPEN

    def test_manual_reset(self):
        cb = UnitCircuitBreaker(threshold=1, cooldown=100.0)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.allows_request() is True


class TestModbusRequestQueue:
    """ModbusRequestQueue 測試"""

    @pytest.mark.asyncio
    async def test_basic_submit_and_result(self):
        """基本提交和結果流程"""
        queue = ModbusRequestQueue(RequestQueueConfig(default_timeout=2.0))
        await queue.start()
        try:
            result = await queue.submit(
                unit_id=1,
                priority=RequestPriority.READ,
                coroutine_factory=lambda: _async_value([100, 200]),
            )
            assert result == [100, 200]
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_write_priority_over_read(self):
        """WRITE 優先於 READ"""
        execution_order: list[str] = []
        gate = asyncio.Event()

        async def blocking_op():
            await gate.wait()
            return "first"

        async def read_op():
            execution_order.append("read")
            return "read"

        async def write_op():
            execution_order.append("write")
            return "write"

        queue = ModbusRequestQueue(RequestQueueConfig(default_timeout=5.0))
        await queue.start()
        try:
            # Submit a blocking operation first to hold up the worker
            blocking_future = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )

            # 等待 blocking op 入隊後被 worker 取出開始處理
            # worker 取出後 total_size 回到 0，但 future 尚未完成（blocked on gate）
            # 先等入隊完成（total_size > 0），再等 worker 取出（total_size == 0）
            await wait_for_condition(lambda: queue._sequence >= 1, message="request should be enqueued")
            await wait_for_condition(
                lambda: queue.total_size == 0 and not blocking_future.done(),
                message="worker should be processing blocking op",
            )

            # Submit READ then WRITE while worker is busy
            read_future = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=read_op)
            )
            write_future = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.WRITE, coroutine_factory=write_op)
            )

            # 等待兩個請求都進入佇列
            await wait_for_condition(lambda: queue.total_size >= 2)

            # Release the gate - worker will process WRITE before READ
            gate.set()

            await blocking_future
            await write_future
            await read_future

            assert execution_order == ["write", "read"]
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_fair_round_robin(self):
        """公平的 round-robin 跨 unit_id"""
        execution_order: list[int] = []
        gate = asyncio.Event()

        async def blocking_op():
            await gate.wait()
            return "block"

        async def tracked_op(uid: int):
            execution_order.append(uid)
            return uid

        queue = ModbusRequestQueue(RequestQueueConfig(default_timeout=5.0))
        await queue.start()
        try:
            # Block the worker first
            blocking_future = asyncio.ensure_future(
                queue.submit(unit_id=99, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            await wait_for_condition(lambda: queue._sequence >= 1, message="blocking request enqueued")
            await wait_for_condition(
                lambda: queue.total_size == 0 and not blocking_future.done(),
                message="worker should pick up blocking op",
            )

            # Submit requests for unit 1, 2, 3 (all same priority)
            futures = []
            for uid in [1, 2, 3]:
                for _ in range(2):
                    f = asyncio.ensure_future(
                        queue.submit(
                            unit_id=uid,
                            priority=RequestPriority.READ,
                            coroutine_factory=lambda u=uid: tracked_op(u),
                        )
                    )
                    futures.append(f)

            await wait_for_condition(lambda: queue.total_size >= 6)
            gate.set()

            await blocking_future
            await asyncio.gather(*futures)

            # Each unit should appear before any unit repeats (round-robin)
            # First 3 should be {1, 2, 3} in some order
            assert set(execution_order[:3]) == {1, 2, 3}
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_per_request_timeout(self):
        """每個請求的逾時控制"""
        queue = ModbusRequestQueue(RequestQueueConfig(default_timeout=5.0))
        await queue.start()
        try:
            with pytest.raises(asyncio.TimeoutError):
                await queue.submit(
                    unit_id=1,
                    priority=RequestPriority.READ,
                    coroutine_factory=lambda: asyncio.sleep(10),
                    timeout=0.1,
                )
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_queue_full_raises(self):
        """佇列已滿時拋出 ModbusQueueFullError"""
        gate = asyncio.Event()

        async def blocking_op():
            await gate.wait()
            return True

        config = RequestQueueConfig(max_queue_size=2, default_timeout=5.0)
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            # Block the worker
            f1 = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            await wait_for_condition(lambda: queue._sequence >= 1, message="first request enqueued")
            await wait_for_condition(
                lambda: queue.total_size == 0 and not f1.done(),
                message="worker should pick up blocking op",
            )

            # Fill queue
            f2 = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            f3 = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            await wait_for_condition(lambda: queue.total_size >= 2, message="queue should have 2 items")

            # Third queued item should fail
            with pytest.raises(ModbusQueueFullError):
                await queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)

            gate.set()
            await f1
            await f2
            await f3
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_circuit_breaker_rejection(self):
        """斷路器開啟時拒絕請求"""
        config = RequestQueueConfig(circuit_breaker_threshold=2, default_timeout=2.0)
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            # Submit failing requests to trigger circuit breaker
            for _ in range(2):
                with pytest.raises(ModbusError, match="fail"):
                    await queue.submit(
                        unit_id=1,
                        priority=RequestPriority.READ,
                        coroutine_factory=lambda: _async_raise(ModbusError("fail")),
                    )

            # Circuit breaker should now be open
            with pytest.raises(ModbusCircuitBreakerError) as exc_info:
                await queue.submit(
                    unit_id=1,
                    priority=RequestPriority.READ,
                    coroutine_factory=lambda: _async_value("ok"),
                )
            assert exc_info.value.unit_id == 1
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self):
        """斷路器冷卻後恢復"""
        config = RequestQueueConfig(
            circuit_breaker_threshold=1,
            circuit_breaker_cooldown=0.1,
            default_timeout=2.0,
        )
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            # Trigger circuit breaker
            with pytest.raises(ModbusError, match="fail"):
                await queue.submit(
                    unit_id=1,
                    priority=RequestPriority.READ,
                    coroutine_factory=lambda: _async_raise(ModbusError("fail")),
                )

            # 用 mock clock 跳過 cooldown，不依賴真實等待
            with patch("csp_lib.core.resilience.time") as mock_time:
                mock_time.monotonic.return_value = time.monotonic() + 5.0

                # Should work now (HALF_OPEN -> CLOSED)
                result = await queue.submit(
                    unit_id=1,
                    priority=RequestPriority.READ,
                    coroutine_factory=lambda: _async_value("recovered"),
                )
                assert result == "recovered"
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self):
        """正常關閉時取消剩餘請求"""
        gate = asyncio.Event()

        async def blocking_op():
            await gate.wait()
            return True

        queue = ModbusRequestQueue(RequestQueueConfig(default_timeout=5.0, drain_timeout=0.5))
        await queue.start()

        # Block the worker and queue more requests
        _f1 = asyncio.ensure_future(
            queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
        )
        await wait_for_condition(lambda: queue._sequence >= 1, message="first request enqueued")
        await wait_for_condition(
            lambda: queue.total_size == 0 and not _f1.done(),
            message="worker should pick up blocking op",
        )

        _f2 = asyncio.ensure_future(
            queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
        )
        await wait_for_condition(lambda: queue.total_size >= 1)

        # Stop the queue
        gate.set()
        await queue.stop()

        assert queue.total_size == 0

    @pytest.mark.asyncio
    async def test_submit_after_stop_raises(self):
        """停止後提交請求應拋出錯誤"""
        queue = ModbusRequestQueue()
        await queue.start()
        await queue.stop()

        with pytest.raises(ModbusError, match="not running"):
            await queue.submit(
                unit_id=1,
                priority=RequestPriority.READ,
                coroutine_factory=lambda: _async_value("late"),
            )

    @pytest.mark.asyncio
    async def test_submit_before_start_raises(self):
        """啟動前提交請求應拋出錯誤"""
        queue = ModbusRequestQueue()

        with pytest.raises(ModbusError, match="not running"):
            await queue.submit(
                unit_id=1,
                priority=RequestPriority.READ,
                coroutine_factory=lambda: _async_value("early"),
            )

    @pytest.mark.asyncio
    async def test_exception_propagation(self):
        """操作異常應正確傳播"""
        queue = ModbusRequestQueue(RequestQueueConfig(default_timeout=2.0))
        await queue.start()
        try:
            with pytest.raises(ValueError, match="bad value"):
                await queue.submit(
                    unit_id=1,
                    priority=RequestPriority.WRITE,
                    coroutine_factory=lambda: _async_raise(ValueError("bad value")),
                )
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_multiple_units_independent(self):
        """不同 unit_id 的斷路器互相獨立"""
        config = RequestQueueConfig(circuit_breaker_threshold=1, default_timeout=2.0)
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            # Trip circuit breaker for unit 1
            with pytest.raises(ModbusError):
                await queue.submit(
                    unit_id=1,
                    priority=RequestPriority.READ,
                    coroutine_factory=lambda: _async_raise(ModbusError("fail")),
                )

            # Unit 2 should still work
            result = await queue.submit(
                unit_id=2,
                priority=RequestPriority.READ,
                coroutine_factory=lambda: _async_value("unit2_ok"),
            )
            assert result == "unit2_ok"

            # Unit 1 should be rejected
            with pytest.raises(ModbusCircuitBreakerError):
                await queue.submit(
                    unit_id=1,
                    priority=RequestPriority.READ,
                    coroutine_factory=lambda: _async_value("unit1_retry"),
                )
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_unlimited_queue_size(self):
        """max_queue_size=0 表示無限制"""
        config = RequestQueueConfig(max_queue_size=0, default_timeout=2.0)
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            result = await queue.submit(
                unit_id=1,
                priority=RequestPriority.READ,
                coroutine_factory=lambda: _async_value("ok"),
            )
            assert result == "ok"
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_worker_timeout_prevents_blocking(self):
        """永不回傳的 coroutine 被 worker timeout 終止，回傳 TimeoutError"""

        async def never_return():
            await asyncio.sleep(3600)
            return "never"

        config = RequestQueueConfig(default_timeout=0.5)
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            with pytest.raises(asyncio.TimeoutError):
                await queue.submit(
                    unit_id=1,
                    priority=RequestPriority.READ,
                    coroutine_factory=never_return,
                    timeout=0.5,
                )
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_stale_requests_skipped(self):
        """在 queue 中過期的 request 不被執行"""
        executed = False
        gate = asyncio.Event()

        async def blocking_op():
            await gate.wait()
            return "block"

        async def tracked_op():
            nonlocal executed
            executed = True
            return "tracked"

        config = RequestQueueConfig(default_timeout=5.0)
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            # Block worker with a long op
            f_block = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            await wait_for_condition(lambda: queue._sequence >= 1, message="blocking request enqueued")
            await wait_for_condition(
                lambda: queue.total_size == 0 and not f_block.done(),
                message="worker should pick up blocking op",
            )

            # Submit a request with very short timeout
            f_stale = asyncio.ensure_future(
                queue.submit(
                    unit_id=1,
                    priority=RequestPriority.READ,
                    coroutine_factory=tracked_op,
                    timeout=0.1,
                )
            )

            # Wait for the caller-side timeout to expire
            with pytest.raises(asyncio.TimeoutError):
                await f_stale

            # Release the blocking op so worker proceeds to the stale request
            gate.set()
            await f_block

            # 等待 worker 處理完畢（佇列清空）
            await wait_for_condition(lambda: queue.total_size == 0)

            # The stale request's coroutine should NOT have been executed
            assert executed is False
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_cancelled_requests_freed_from_queue(self):
        """已取消的 request 被 dequeue 清理，不佔 total_size"""
        gate = asyncio.Event()

        async def blocking_op():
            await gate.wait()
            return "block"

        config = RequestQueueConfig(max_queue_size=5, default_timeout=5.0)
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            # Block worker
            f_block = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            await wait_for_condition(lambda: queue._sequence >= 1, message="blocking request enqueued")
            await wait_for_condition(
                lambda: queue.total_size == 0 and not f_block.done(),
                message="worker should pick up blocking op",
            )

            # Submit requests with short timeout so they'll be cancelled by caller
            stale_futures = []
            for _ in range(3):
                f = asyncio.ensure_future(
                    queue.submit(
                        unit_id=1,
                        priority=RequestPriority.READ,
                        coroutine_factory=lambda: _async_value("stale"),
                        timeout=0.1,
                    )
                )
                stale_futures.append(f)

            # Wait for caller-side timeouts
            for f in stale_futures:
                with pytest.raises(asyncio.TimeoutError):
                    await f

            # Release worker so dequeue runs and cleans cancelled requests
            gate.set()
            await f_block

            # 等待 worker 清理完畢
            await wait_for_condition(lambda: queue.total_size == 0)

            # Cancelled requests should have been freed
            assert queue.total_size == 0
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_worker_timeout_triggers_circuit_breaker(self):
        """worker timeout 正確遞增 CB failure counter，達 threshold 後 OPEN"""

        async def never_return():
            await asyncio.sleep(3600)
            return "never"

        config = RequestQueueConfig(
            default_timeout=0.6,
            circuit_breaker_threshold=2,
            circuit_breaker_cooldown=60.0,
        )
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            # Two timeouts should trip the circuit breaker
            for _ in range(2):
                with pytest.raises(asyncio.TimeoutError):
                    await queue.submit(
                        unit_id=1,
                        priority=RequestPriority.READ,
                        coroutine_factory=never_return,
                        timeout=0.6,
                    )

            # CB should become OPEN once worker finishes recording failures.
            # Caller timeout 與 worker timeout 幾乎同時 fire；caller 先 raise 時
            # worker 尚未執行 record_failure()，因此不可直接 assert，需等 CB 狀態轉換。
            cb = queue._get_circuit_breaker(1)
            await wait_for_condition(
                lambda: cb.state == CircuitBreakerState.OPEN,
                timeout=2.0,
                message="circuit breaker should OPEN after 2 worker timeouts",
            )

            with pytest.raises(ModbusCircuitBreakerError):
                await queue.submit(
                    unit_id=1,
                    priority=RequestPriority.READ,
                    coroutine_factory=lambda: _async_value("should_fail"),
                )
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_event_recheck_after_clear(self):
        """Worker clear 後若 total_size > 0，應立即回去 dequeue 而非阻塞在 wait"""
        config = RequestQueueConfig(default_timeout=2.0)
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            # 連續兩個 submit，第二個應在 worker 處理完第一個後被迅速處理
            r1 = await queue.submit(
                unit_id=1,
                priority=RequestPriority.READ,
                coroutine_factory=lambda: _async_value("first"),
            )
            assert r1 == "first"

            r2 = await queue.submit(
                unit_id=1,
                priority=RequestPriority.READ,
                coroutine_factory=lambda: _async_value("second"),
                timeout=1.0,
            )
            assert r2 == "second"
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_queue_full_exact_limit(self):
        """並行 submit 不應超過 max_queue_size (TOCTOU 防護)"""
        gate = asyncio.Event()

        async def blocking_op():
            await gate.wait()
            return True

        config = RequestQueueConfig(max_queue_size=2, default_timeout=5.0)
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            # Block worker with one request
            f_block = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            await wait_for_condition(lambda: queue._sequence >= 1, message="blocking request enqueued")
            await wait_for_condition(
                lambda: queue.total_size == 0 and not f_block.done(),
                message="worker should pick up blocking op",
            )

            # Enqueue 1 more -> total_size == 1, max == 2, 1 slot left
            f_fill = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            await wait_for_condition(lambda: queue.total_size >= 1)

            # Hold the lock so both new submits pass size check then block on lock acquire
            await queue._lock.acquire()

            # Launch 2 concurrent submits -- both see total_size=1 < max=2, pass check
            f_a = asyncio.ensure_future(
                queue.submit(unit_id=2, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            f_b = asyncio.ensure_future(
                queue.submit(unit_id=3, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            # yield control 讓兩個 submit 都開始等待 lock
            await asyncio.sleep(0)

            # Release lock -- they'll acquire sequentially and enqueue
            queue._lock.release()
            # 等待兩個 submit 都嘗試完成（其中一個可能因 QueueFull 而結束）
            await asyncio.sleep(0)

            # Bug: total_size == 3 > max == 2 (both passed stale size check)
            # Fix: second submit sees total_size == 2 >= max inside lock → QueueFullError
            assert queue.total_size <= config.max_queue_size, (
                f"total_size={queue.total_size} exceeded max={config.max_queue_size}"
            )

            # Cleanup
            gate.set()
            for f in [f_block, f_fill, f_a, f_b]:
                try:
                    await asyncio.wait_for(f, timeout=2.0)
                except (asyncio.TimeoutError, ModbusQueueFullError, asyncio.CancelledError):
                    pass
        finally:
            if queue._lock.locked():
                queue._lock.release()
            await queue.stop()

    @pytest.mark.asyncio
    async def test_stale_request_no_cb_event(self):
        """過期跳過的 request 不影響 CB failure_count"""
        gate = asyncio.Event()

        async def blocking_op():
            await gate.wait()
            return "block"

        config = RequestQueueConfig(
            default_timeout=5.0,
            circuit_breaker_threshold=2,
            circuit_breaker_cooldown=60.0,
        )
        queue = ModbusRequestQueue(config)
        await queue.start()
        try:
            # Block worker
            f_block = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            await wait_for_condition(lambda: queue._sequence >= 1, message="blocking request enqueued")
            await wait_for_condition(
                lambda: queue.total_size == 0 and not f_block.done(),
                message="worker should pick up blocking op",
            )

            # Submit requests with very short timeout (will become stale)
            stale_futures = []
            for _ in range(3):
                f = asyncio.ensure_future(
                    queue.submit(
                        unit_id=1,
                        priority=RequestPriority.READ,
                        coroutine_factory=lambda: _async_value("stale"),
                        timeout=0.1,
                    )
                )
                stale_futures.append(f)

            # Wait for caller-side timeouts
            for f in stale_futures:
                with pytest.raises(asyncio.TimeoutError):
                    await f

            # Release worker
            gate.set()
            await f_block
            # 等待 worker 清理完畢
            await wait_for_condition(lambda: queue.total_size == 0)

            # CB should still be CLOSED — stale skips don't count as failures
            cb = queue._get_circuit_breaker(1)
            assert cb.state == CircuitBreakerState.CLOSED
            assert cb.failure_count == 0
        finally:
            await queue.stop()


# ========== Helper coroutines ==========


async def _async_value(value: object) -> object:
    return value


async def _async_raise(exc: Exception) -> object:
    raise exc
