# =============== Core Tests - AsyncSinkAdapter ===============
#
# AsyncSinkAdapter 非同步 sink 轉接器測試

from __future__ import annotations

import asyncio

import pytest

from csp_lib.core.logging.async_sink import AsyncSinkAdapter
from csp_lib.core.logging.sink_manager import SinkManager


@pytest.fixture(autouse=True)
def _reset_sink_manager():
    """每個測試前後重置 SinkManager"""
    SinkManager.reset()
    yield
    SinkManager.reset()


class TestAsyncSinkAdapter:
    """AsyncSinkAdapter 轉接器測試"""

    async def test_async_sink_adapter_write(self):
        """同步 write 排入 queue，async handler 收到訊息"""
        received: list[str] = []

        async def handler(msg: str) -> None:
            received.append(msg)

        loop = asyncio.get_event_loop()
        adapter = AsyncSinkAdapter(handler, loop=loop, max_queue_size=100)

        adapter.write("test message\n")
        # 等待 drain task 處理
        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert "test message" in received[0]

        await adapter.close()

    async def test_async_sink_adapter_close(self):
        """close 後 flush 剩餘訊息"""
        received: list[str] = []

        async def handler(msg: str) -> None:
            received.append(msg)

        loop = asyncio.get_event_loop()
        adapter = AsyncSinkAdapter(handler, loop=loop, max_queue_size=100)

        adapter.write("msg1\n")
        adapter.write("msg2\n")
        await adapter.close()

        assert len(received) == 2

    async def test_async_sink_adapter_queue_full_silent(self):
        """queue 滿時靜默丟棄，不拋例外"""

        async def handler(msg: str) -> None:
            await asyncio.sleep(10)  # 故意慢，讓 queue 堆積

        loop = asyncio.get_event_loop()
        adapter = AsyncSinkAdapter(handler, loop=loop, max_queue_size=2)

        # 寫入超過 queue 上限的訊息，不應拋錯
        for i in range(10):
            adapter.write(f"msg{i}\n")

        # 清理
        adapter._closed = True
        if adapter._drain_task and not adapter._drain_task.done():
            adapter._drain_task.cancel()
            try:
                await adapter._drain_task
            except asyncio.CancelledError:
                pass

    async def test_async_sink_with_manager(self):
        """透過 SinkManager.add_async_sink 使用"""
        received: list[str] = []

        async def handler(msg: str) -> None:
            received.append(msg)

        mgr = SinkManager.get_instance()
        sid = mgr.add_async_sink(handler, name="async_via_mgr")

        info = mgr.get_sink("async_via_mgr")
        assert info is not None
        assert info.sink_type == "async"
        assert isinstance(sid, int)

    async def test_write_after_close_ignored(self):
        """關閉後的 write 應被忽略"""
        received: list[str] = []

        async def handler(msg: str) -> None:
            received.append(msg)

        loop = asyncio.get_event_loop()
        adapter = AsyncSinkAdapter(handler, loop=loop)
        await adapter.close()

        adapter.write("should be ignored\n")
        await asyncio.sleep(0.05)
        assert len(received) == 0
