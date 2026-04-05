# =============== Core Tests - LogContext ===============
#
# LogContext 結構化日誌上下文測試

from __future__ import annotations

import asyncio

from csp_lib.core.logging.context import LogContext


class TestLogContextSync:
    """LogContext 同步 context manager 測試"""

    def test_sync_context_manager(self):
        """sync with 綁定/解綁"""
        assert LogContext.current() == {}
        with LogContext(request_id="abc"):
            ctx = LogContext.current()
            assert ctx["request_id"] == "abc"
        assert LogContext.current() == {}

    def test_nested_context(self):
        """嵌套 context：內層覆蓋外層，離開後恢復"""
        with LogContext(a="1", b="2"):
            assert LogContext.current() == {"a": "1", "b": "2"}
            with LogContext(b="override", c="3"):
                ctx = LogContext.current()
                assert ctx["a"] == "1"  # 繼承外層
                assert ctx["b"] == "override"  # 內層覆蓋
                assert ctx["c"] == "3"  # 內層新增
            # 離開內層後恢復
            ctx = LogContext.current()
            assert ctx["b"] == "2"
            assert "c" not in ctx
        assert LogContext.current() == {}


class TestLogContextAsync:
    """LogContext 非同步 context manager 測試"""

    async def test_async_context_manager(self):
        """async with 綁定/解綁"""
        assert LogContext.current() == {}
        async with LogContext(device_id="PCS-01"):
            ctx = LogContext.current()
            assert ctx["device_id"] == "PCS-01"
        assert LogContext.current() == {}

    async def test_concurrent_tasks_isolation(self):
        """兩個 async task 的 context 互不干擾"""
        results: dict[str, str] = {}

        async def task_a():
            async with LogContext(task="A"):
                await asyncio.sleep(0.01)
                results["a"] = LogContext.current().get("task", "")

        async def task_b():
            async with LogContext(task="B"):
                await asyncio.sleep(0.01)
                results["b"] = LogContext.current().get("task", "")

        await asyncio.gather(task_a(), task_b())
        assert results["a"] == "A"
        assert results["b"] == "B"


class TestLogContextDecorator:
    """LogContext 作為 decorator 測試"""

    async def test_decorator_async(self):
        """LogContext 裝飾 async 函式"""

        @LogContext(operation="calibrate")
        async def calibrate():
            return LogContext.current()

        ctx = await calibrate()
        assert ctx["operation"] == "calibrate"
        # 離開 decorator 後 context 應清空
        assert LogContext.current() == {}

    def test_decorator_sync(self):
        """LogContext 裝飾 sync 函式"""

        @LogContext(step="init")
        def init():
            return LogContext.current()

        ctx = init()
        assert ctx["step"] == "init"
        assert LogContext.current() == {}


class TestLogContextStaticMethods:
    """LogContext 靜態方法 bind/unbind/current 測試"""

    def test_bind_unbind(self):
        """靜態方法 bind/unbind"""
        LogContext.bind(key1="val1", key2="val2")
        ctx = LogContext.current()
        assert ctx["key1"] == "val1"
        assert ctx["key2"] == "val2"

        LogContext.unbind("key1")
        ctx = LogContext.current()
        assert "key1" not in ctx
        assert ctx["key2"] == "val2"

        # 清理
        LogContext.unbind("key2")

    def test_current_returns_copy(self):
        """current() 回傳防禦性複製"""
        with LogContext(x="1"):
            ctx = LogContext.current()
            ctx["y"] = "2"
            assert "y" not in LogContext.current()

    def test_current_empty_when_no_context(self):
        """無 context 時回傳空 dict"""
        assert LogContext.current() == {}
