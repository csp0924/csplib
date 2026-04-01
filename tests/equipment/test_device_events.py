# =============== Equipment Device Tests - Events ===============
#
# DeviceEventEmitter 事件發射器單元測試
#
# 測試覆蓋：
# - 事件註冊與發射
# - Queue-based 非阻塞發射
# - emit_await 同步發射
# - start/stop lifecycle
# - 錯誤處理
# - Payload dataclass

from __future__ import annotations

import asyncio
import gc
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.device.events import (
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    EVENT_VALUE_CHANGE,
    ConnectedPayload,
    DeviceEventEmitter,
    DisconnectPayload,
    ReadCompletePayload,
    ValueChangePayload,
    _WeakHandler,
)

# ======================== Payload Tests ========================


class TestValueChangePayload:
    """ValueChangePayload 測試"""

    def test_create_payload(self):
        """正確建立 payload"""
        payload = ValueChangePayload(
            device_id="device_001",
            point_name="power",
            old_value=100,
            new_value=200,
        )

        assert payload.device_id == "device_001"
        assert payload.point_name == "power"
        assert payload.old_value == 100
        assert payload.new_value == 200
        assert isinstance(payload.timestamp, datetime)

    def test_frozen_immutable(self):
        """frozen=True 應使物件不可變"""
        payload = ValueChangePayload(
            device_id="device_001",
            point_name="test",
            old_value=0,
            new_value=1,
        )

        with pytest.raises(AttributeError):
            payload.point_name = "changed"


class TestDisconnectPayload:
    """DisconnectPayload 測試"""

    def test_create_payload(self):
        """正確建立 payload"""
        payload = DisconnectPayload(
            device_id="device_001",
            reason="Connection timeout",
            consecutive_failures=5,
        )

        assert payload.device_id == "device_001"
        assert payload.reason == "Connection timeout"
        assert payload.consecutive_failures == 5
        assert isinstance(payload.timestamp, datetime)


class TestReadCompletePayload:
    """ReadCompletePayload 測試"""

    def test_create_payload(self):
        """正確建立 payload"""
        values = {"power": 100, "voltage": 220}
        payload = ReadCompletePayload(
            device_id="device_001",
            values=values,
            duration_ms=15.5,
        )

        assert payload.device_id == "device_001"
        assert payload.values == values
        assert payload.duration_ms == 15.5
        assert isinstance(payload.timestamp, datetime)


class TestConnectedPayload:
    """ConnectedPayload 測試"""

    def test_create_payload(self):
        """正確建立 payload"""
        payload = ConnectedPayload(device_id="device_001")

        assert payload.device_id == "device_001"
        assert isinstance(payload.timestamp, datetime)


# ======================== DeviceEventEmitter Lifecycle Tests ========================


class TestDeviceEventEmitterLifecycle:
    """DeviceEventEmitter 生命週期測試"""

    @pytest.mark.asyncio
    async def test_start_creates_worker(self):
        """start() 應建立 worker task"""
        emitter = DeviceEventEmitter()

        await emitter.start()
        try:
            assert emitter._running is True
            assert emitter._worker_task is not None
            assert not emitter._worker_task.done()
        finally:
            await emitter.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """重複 start() 應無效果"""
        emitter = DeviceEventEmitter()

        await emitter.start()
        task1 = emitter._worker_task

        await emitter.start()  # 第二次
        task2 = emitter._worker_task

        try:
            assert task1 is task2  # 應為同一個 task
        finally:
            await emitter.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_worker(self):
        """stop() 應取消 worker task"""
        emitter = DeviceEventEmitter()

        await emitter.start()
        await emitter.stop()

        assert emitter._running is False
        assert emitter._worker_task is None

    @pytest.mark.asyncio
    async def test_stop_processes_remaining_events(self):
        """stop() 應處理佇列中剩餘的事件"""
        emitter = DeviceEventEmitter()
        handler = AsyncMock()
        emitter.on(EVENT_CONNECTED, handler)

        await emitter.start()

        # 發射事件但不等待處理
        emitter.emit(EVENT_CONNECTED, {"test": 1})
        emitter.emit(EVENT_CONNECTED, {"test": 2})

        # 立即停止
        await emitter.stop()

        # 剩餘事件應已處理
        assert handler.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        """重複 stop() 應無錯誤"""
        emitter = DeviceEventEmitter()

        await emitter.start()
        await emitter.stop()
        await emitter.stop()  # 第二次不應報錯


# ======================== DeviceEventEmitter Event Tests ========================


class TestDeviceEventEmitterEmit:
    """DeviceEventEmitter emit 測試"""

    @pytest.mark.asyncio
    async def test_emit_skips_when_not_running(self):
        """emit() 未啟動時不入隊"""
        emitter = DeviceEventEmitter()
        emitter.on(EVENT_CONNECTED, AsyncMock())

        emitter.emit(EVENT_CONNECTED, {"test": True})

        assert emitter.queue_size == 0  # 未 start，不入隊

    @pytest.mark.asyncio
    async def test_emit_triggers_handler_via_worker(self):
        """emit() 事件應由 worker 處理"""
        emitter = DeviceEventEmitter()
        handler = AsyncMock()
        emitter.on(EVENT_CONNECTED, handler)

        await emitter.start()
        try:
            emitter.emit(EVENT_CONNECTED, {"status": "ok"})

            # 等待 worker 處理
            await asyncio.sleep(0.1)

            handler.assert_called_once_with({"status": "ok"})
        finally:
            await emitter.stop()

    @pytest.mark.asyncio
    async def test_emit_nonblocking(self):
        """emit() 應為非阻塞"""
        emitter = DeviceEventEmitter()

        async def slow_handler(payload):
            await asyncio.sleep(1.0)

        emitter.on(EVENT_CONNECTED, slow_handler)

        await emitter.start()
        try:
            import time

            start = time.monotonic()
            emitter.emit(EVENT_CONNECTED, None)
            elapsed = time.monotonic() - start

            # emit 應立即返回
            assert elapsed < 0.1
        finally:
            await emitter.stop()

    @pytest.mark.asyncio
    async def test_emit_queue_full_drops_event(self):
        """佇列滿時 emit() 應丟棄事件"""
        emitter = DeviceEventEmitter(max_queue_size=2)

        async def slow_handler(payload):
            await asyncio.sleep(10)  # 阻塞 worker 防止消費

        emitter.on(EVENT_CONNECTED, slow_handler)
        await emitter.start()
        try:
            emitter.emit(EVENT_CONNECTED, 1)
            emitter.emit(EVENT_CONNECTED, 2)
            emitter.emit(EVENT_CONNECTED, 3)  # 應被丟棄（佇列滿）
            # worker 在處理第 1 個（slow），佇列剩 1-2 個
            # 至少驗證第 3 個被丟棄（queue_size <= 2）
            assert emitter.queue_size <= 2
        finally:
            await emitter.stop()


class TestDeviceEventEmitterEmitAwait:
    """DeviceEventEmitter emit_await 測試"""

    @pytest.mark.asyncio
    async def test_emit_await_processes_immediately(self):
        """emit_await() 應立即處理事件"""
        emitter = DeviceEventEmitter()
        handler = AsyncMock()
        emitter.on(EVENT_CONNECTED, handler)

        # 不需要 start()，emit_await 直接處理
        await emitter.emit_await(EVENT_CONNECTED, {"status": "ok"})

        handler.assert_called_once_with({"status": "ok"})

    @pytest.mark.asyncio
    async def test_emit_await_waits_for_handler(self):
        """emit_await() 應等待處理器完成"""
        emitter = DeviceEventEmitter()
        completed = []

        async def slow_handler(payload):
            await asyncio.sleep(0.1)
            completed.append(True)

        emitter.on(EVENT_CONNECTED, slow_handler)

        await emitter.emit_await(EVENT_CONNECTED, None)

        # 處理器應已完成
        assert len(completed) == 1


# ======================== DeviceEventEmitter Handler Tests ========================


class TestDeviceEventEmitterHandlers:
    """DeviceEventEmitter 處理器測試"""

    @pytest.fixture
    def emitter(self) -> DeviceEventEmitter:
        return DeviceEventEmitter()

    @pytest.mark.asyncio
    async def test_multiple_handlers_all_called(self, emitter: DeviceEventEmitter):
        """多個處理器應全部被呼叫"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        emitter.on(EVENT_VALUE_CHANGE, handler1)
        emitter.on(EVENT_VALUE_CHANGE, handler2)

        payload = ValueChangePayload(
            device_id="device_001",
            point_name="power",
            old_value=0,
            new_value=100,
        )
        await emitter.emit_await(EVENT_VALUE_CHANGE, payload)

        handler1.assert_called_once_with(payload)
        handler2.assert_called_once_with(payload)

    @pytest.mark.asyncio
    async def test_handlers_run_sequentially(self, emitter: DeviceEventEmitter):
        """處理器應順序執行（避免競爭）"""
        execution_order: list[int] = []

        async def handler1(payload):
            execution_order.append(1)

        async def handler2(payload):
            execution_order.append(2)

        emitter.on(EVENT_CONNECTED, handler1)
        emitter.on(EVENT_CONNECTED, handler2)

        await emitter.emit_await(EVENT_CONNECTED, None)

        assert execution_order == [1, 2]

    def test_has_listeners_true(self, emitter: DeviceEventEmitter):
        """有監聽器時應回傳 True"""
        emitter.on(EVENT_CONNECTED, AsyncMock())

        assert emitter.has_listeners(EVENT_CONNECTED) is True

    def test_has_listeners_false(self, emitter: DeviceEventEmitter):
        """無監聽器時應回傳 False"""
        assert emitter.has_listeners(EVENT_CONNECTED) is False


class TestDeviceEventEmitterCancel:
    """取消訂閱測試"""

    @pytest.fixture
    def emitter(self) -> DeviceEventEmitter:
        return DeviceEventEmitter()

    @pytest.mark.asyncio
    async def test_cancel_removes_handler(self, emitter: DeviceEventEmitter):
        """取消訂閱後處理器不應被呼叫"""
        handler = AsyncMock()
        cancel = emitter.on(EVENT_CONNECTED, handler)

        cancel()

        await emitter.emit_await(EVENT_CONNECTED, None)

        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_only_removes_specific_handler(self, emitter: DeviceEventEmitter):
        """取消訂閱只應移除特定處理器"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        cancel1 = emitter.on(EVENT_CONNECTED, handler1)
        emitter.on(EVENT_CONNECTED, handler2)

        cancel1()

        await emitter.emit_await(EVENT_CONNECTED, None)

        handler1.assert_not_called()
        handler2.assert_called_once()

    def test_cancel_twice_no_error(self, emitter: DeviceEventEmitter):
        """重複取消不應報錯"""
        handler = AsyncMock()
        cancel = emitter.on(EVENT_CONNECTED, handler)

        cancel()
        cancel()  # 第二次取消不應報錯


class TestDeviceEventEmitterClear:
    """清除處理器測試"""

    @pytest.fixture
    def emitter(self) -> DeviceEventEmitter:
        return DeviceEventEmitter()

    @pytest.mark.asyncio
    async def test_clear_specific_event(self, emitter: DeviceEventEmitter):
        """清除特定事件的處理器"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        emitter.on(EVENT_CONNECTED, handler1)
        emitter.on(EVENT_DISCONNECTED, handler2)

        emitter.clear(EVENT_CONNECTED)

        await emitter.emit_await(EVENT_CONNECTED, None)
        await emitter.emit_await(EVENT_DISCONNECTED, None)

        handler1.assert_not_called()
        handler2.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_all_events(self, emitter: DeviceEventEmitter):
        """清除所有事件處理器"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        emitter.on(EVENT_CONNECTED, handler1)
        emitter.on(EVENT_DISCONNECTED, handler2)

        emitter.clear()

        await emitter.emit_await(EVENT_CONNECTED, None)
        await emitter.emit_await(EVENT_DISCONNECTED, None)

        handler1.assert_not_called()
        handler2.assert_not_called()

    def test_clear_nonexistent_event_no_error(self, emitter: DeviceEventEmitter):
        """清除不存在的事件不應報錯"""
        emitter.clear("nonexistent_event")


class TestDeviceEventEmitterErrorHandling:
    """錯誤處理測試"""

    @pytest.fixture
    def emitter(self) -> DeviceEventEmitter:
        return DeviceEventEmitter()

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_break_others(self, emitter: DeviceEventEmitter):
        """處理器異常不應影響其他處理器"""
        handler1 = AsyncMock(side_effect=Exception("Handler 1 failed"))
        handler2 = AsyncMock()

        emitter.on(EVENT_CONNECTED, handler1)
        emitter.on(EVENT_CONNECTED, handler2)

        # 不應拋錯，且 handler2 仍應被呼叫
        await emitter.emit_await(EVENT_CONNECTED, None)

        handler1.assert_called_once()
        handler2.assert_called_once()


# ======================== Event Constants Tests ========================


class TestEventConstants:
    """事件常數測試"""

    def test_event_constants_are_strings(self):
        """事件常數應為字串"""
        assert isinstance(EVENT_CONNECTED, str)
        assert isinstance(EVENT_DISCONNECTED, str)
        assert isinstance(EVENT_READ_COMPLETE, str)
        assert isinstance(EVENT_VALUE_CHANGE, str)

    def test_event_constants_values(self):
        """事件常數值應正確"""
        assert EVENT_CONNECTED == "connected"
        assert EVENT_DISCONNECTED == "disconnected"
        assert EVENT_READ_COMPLETE == "read_complete"
        assert EVENT_VALUE_CHANGE == "value_change"


# ======================== WeakHandler Tests ========================


class TestWeakHandlerWrapper:
    """_WeakHandler 包裝器測試"""

    def test_alive_when_referent_exists(self):
        """referent 存在時 alive 應為 True"""

        async def handler(payload):
            pass

        wh = _WeakHandler(handler)
        assert wh.alive is True

    def test_dead_after_referent_gc(self):
        """referent 被 GC 後 alive 應為 False"""

        async def handler(payload):
            pass

        wh = _WeakHandler(handler)
        del handler
        gc.collect()
        assert wh.alive is False

    @pytest.mark.asyncio
    async def test_call_invokes_handler(self):
        """__call__ 應正確呼叫 handler"""
        called_with = []

        async def handler(payload):
            called_with.append(payload)

        wh = _WeakHandler(handler)
        await wh("test_payload")
        assert called_with == ["test_payload"]

    @pytest.mark.asyncio
    async def test_call_noop_when_dead(self):
        """referent 被 GC 後 __call__ 應為 no-op"""

        async def handler(payload):
            raise AssertionError("Should not be called")

        wh = _WeakHandler(handler)
        del handler
        gc.collect()
        # Should not raise
        await wh("test_payload")

    def test_bound_method_weakref(self):
        """bound method 應使用 WeakMethod"""

        class Listener:
            async def on_event(self, payload):
                pass

        obj = Listener()
        wh = _WeakHandler(obj.on_event)
        assert wh.alive is True

        del obj
        gc.collect()
        assert wh.alive is False

    def test_lambda_dies_immediately_without_strong_ref(self):
        """lambda 若無強引用，弱引用會立即失效"""
        # Lambda is alive while local var exists
        fn = lambda payload: None  # noqa: E731
        wh = _WeakHandler(fn)  # type: ignore[arg-type]
        assert wh.alive is True

        # Once the only strong ref is dropped, the weakref dies
        del fn
        gc.collect()
        assert wh.alive is False


class TestDeviceEventEmitterWeakOn:
    """DeviceEventEmitter weak=True 註冊測試"""

    @pytest.fixture
    def emitter(self) -> DeviceEventEmitter:
        return DeviceEventEmitter()

    @pytest.mark.asyncio
    async def test_weak_handler_called_while_alive(self, emitter: DeviceEventEmitter):
        """weak handler 存活時應被呼叫"""
        called = []

        async def handler(payload):
            called.append(payload)

        emitter.on(EVENT_CONNECTED, handler, weak=True)
        await emitter.emit_await(EVENT_CONNECTED, "alive")
        assert called == ["alive"]

    @pytest.mark.asyncio
    async def test_weak_handler_auto_removed_after_gc(self, emitter: DeviceEventEmitter):
        """weak handler referent 被 GC 後應自動移除"""
        called = []

        async def handler(payload):
            called.append(payload)

        emitter.on(EVENT_CONNECTED, handler, weak=True)

        # Delete the handler and force GC
        del handler
        gc.collect()

        await emitter.emit_await(EVENT_CONNECTED, "should_not_arrive")
        assert called == []

    @pytest.mark.asyncio
    async def test_weak_handler_has_listeners_false_after_gc(self, emitter: DeviceEventEmitter):
        """weak handler GC 後 has_listeners 應回傳 False"""

        async def handler(payload):
            pass

        emitter.on(EVENT_CONNECTED, handler, weak=True)
        assert emitter.has_listeners(EVENT_CONNECTED) is True

        del handler
        gc.collect()
        assert emitter.has_listeners(EVENT_CONNECTED) is False

    @pytest.mark.asyncio
    async def test_weak_and_strong_coexist(self, emitter: DeviceEventEmitter):
        """weak 和 strong handler 可以共存"""
        strong_calls = []
        weak_calls = []

        async def strong_handler(payload):
            strong_calls.append(payload)

        async def weak_handler(payload):
            weak_calls.append(payload)

        emitter.on(EVENT_CONNECTED, strong_handler)
        emitter.on(EVENT_CONNECTED, weak_handler, weak=True)

        await emitter.emit_await(EVENT_CONNECTED, "both")
        assert strong_calls == ["both"]
        assert weak_calls == ["both"]

        # GC the weak handler
        del weak_handler
        gc.collect()

        await emitter.emit_await(EVENT_CONNECTED, "strong_only")
        assert strong_calls == ["both", "strong_only"]
        assert weak_calls == ["both"]  # No new call

    @pytest.mark.asyncio
    async def test_weak_bound_method_auto_cleanup(self, emitter: DeviceEventEmitter):
        """bound method 以 weak=True 註冊，物件 GC 後應自動移除"""
        called = []

        class Listener:
            async def on_event(self, payload):
                called.append(payload)

        obj = Listener()
        emitter.on(EVENT_CONNECTED, obj.on_event, weak=True)

        await emitter.emit_await(EVENT_CONNECTED, "before_gc")
        assert called == ["before_gc"]

        del obj
        gc.collect()

        await emitter.emit_await(EVENT_CONNECTED, "after_gc")
        assert called == ["before_gc"]  # No new call

    def test_weak_false_default_backward_compat(self, emitter: DeviceEventEmitter):
        """weak=False (default) 應保持原有行為"""
        handler = AsyncMock()
        cancel = emitter.on(EVENT_CONNECTED, handler)

        # Handler stored directly, not wrapped
        assert emitter._handlers[EVENT_CONNECTED][0] is handler

        cancel()
        assert not emitter.has_listeners(EVENT_CONNECTED)

    @pytest.mark.asyncio
    async def test_cancel_weak_handler(self, emitter: DeviceEventEmitter):
        """手動取消 weak handler"""
        called = []

        async def handler(payload):
            called.append(payload)

        cancel = emitter.on(EVENT_CONNECTED, handler, weak=True)
        cancel()

        await emitter.emit_await(EVENT_CONNECTED, "cancelled")
        assert called == []
