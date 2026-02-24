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

        with patch("csp_lib.modbus.clients.queue.time") as mock_time:
            # Simulate cooldown elapsed
            mock_time.monotonic.return_value = time.monotonic() + 1.0
            assert cb.state == CircuitBreakerState.HALF_OPEN
            assert cb.allows_request() is True

    def test_half_open_success_closes(self):
        cb = UnitCircuitBreaker(threshold=1, cooldown=100.0)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        with patch("csp_lib.modbus.clients.queue.time") as mock_time:
            # Simulate cooldown elapsed → HALF_OPEN
            mock_time.monotonic.return_value = time.monotonic() + 200.0
            assert cb.state == CircuitBreakerState.HALF_OPEN

            cb.record_success()
            assert cb.state == CircuitBreakerState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = UnitCircuitBreaker(threshold=1, cooldown=100.0)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        with patch("csp_lib.modbus.clients.queue.time") as mock_time:
            # Simulate cooldown elapsed → HALF_OPEN
            mock_time.monotonic.return_value = time.monotonic() + 200.0
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

            # Give worker time to start processing the blocking op
            await asyncio.sleep(0.05)

            # Submit READ then WRITE while worker is busy
            read_future = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=read_op)
            )
            write_future = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.WRITE, coroutine_factory=write_op)
            )

            # Wait for queued items to be enqueued
            await asyncio.sleep(0.05)

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
            await asyncio.sleep(0.05)

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

            await asyncio.sleep(0.05)
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
            await asyncio.sleep(0.05)

            # Fill queue
            f2 = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            f3 = asyncio.ensure_future(
                queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
            )
            await asyncio.sleep(0.05)

            # Third queued item should fail
            with pytest.raises(ModbusQueueFullError):
                await queue.submit(
                    unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op
                )

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

            # Wait for cooldown
            await asyncio.sleep(0.2)

            # Should work now (HALF_OPEN → CLOSED)
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
        f1 = asyncio.ensure_future(
            queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
        )
        await asyncio.sleep(0.05)

        f2 = asyncio.ensure_future(
            queue.submit(unit_id=1, priority=RequestPriority.READ, coroutine_factory=blocking_op)
        )
        await asyncio.sleep(0.05)

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


# ========== Helper coroutines ==========


async def _async_value(value: object) -> object:
    return value


async def _async_raise(exc: Exception) -> object:
    raise exc
