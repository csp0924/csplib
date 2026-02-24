import asyncio

import pytest

from csp_lib.mongo.queue import BatchQueue


class TestBatchQueue:
    @pytest.mark.asyncio
    async def test_enqueue_single(self):
        q = BatchQueue("test", max_size=100)
        result = await q.enqueue({"a": 1})
        assert result is True
        assert await q.size() == 1

    @pytest.mark.asyncio
    async def test_enqueue_at_capacity_drops(self):
        q = BatchQueue("test", max_size=2)
        await q.enqueue({"a": 1})
        await q.enqueue({"b": 2})
        result = await q.enqueue({"c": 3})
        assert result is False  # oldest dropped
        assert await q.size() == 2

    @pytest.mark.asyncio
    async def test_drain_returns_all_and_clears(self):
        q = BatchQueue("test", max_size=100)
        await q.enqueue({"a": 1})
        await q.enqueue({"b": 2})
        docs = await q.drain()
        assert len(docs) == 2
        assert await q.size() == 0

    @pytest.mark.asyncio
    async def test_drain_empty(self):
        q = BatchQueue("test")
        docs = await q.drain()
        assert docs == []

    @pytest.mark.asyncio
    async def test_restore_puts_back_at_front(self):
        q = BatchQueue("test", max_size=100)
        await q.enqueue({"a": 1})
        docs = await q.drain()
        await q.enqueue({"b": 2})
        await q.restore(docs)
        all_docs = await q.drain()
        assert all_docs[0] == {"a": 1}
        assert all_docs[1] == {"b": 2}

    @pytest.mark.asyncio
    async def test_restore_at_capacity_drops_excess(self):
        q = BatchQueue("test", max_size=2)
        await q.enqueue({"a": 1})
        await q.enqueue({"b": 2})
        # queue is full, try to restore
        await q.restore([{"c": 3}])
        assert await q.size() == 2  # can't add more

    @pytest.mark.asyncio
    async def test_concurrent_enqueue_drain(self):
        q = BatchQueue("test", max_size=1000)

        async def producer():
            for i in range(50):
                await q.enqueue({"i": i})

        async def consumer():
            await asyncio.sleep(0.01)
            return await q.drain()

        await asyncio.gather(producer(), consumer())
        # After producer and consumer, some items may remain
        remaining = await q.drain()
        # Total items: up to 50, no crash
        assert isinstance(remaining, list)

    def test_size_sync(self):
        q = BatchQueue("test")
        assert q.size_sync() == 0
