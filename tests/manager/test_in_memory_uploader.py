# =============== Manager Tests - In-Memory Uploader ===============
#
# NullBatchUploader + InMemoryBatchUploader 單元測試
#
# 測試覆蓋：
# - NullBatchUploader: no-op 行為驗證
# - InMemoryBatchUploader: CRUD 流程、自動建立 collection、清除、thread safety

from __future__ import annotations

import asyncio
import threading

from csp_lib.manager.in_memory_uploader import InMemoryBatchUploader, NullBatchUploader

# ======================== NullBatchUploader ========================


class TestNullBatchUploader:
    """NullBatchUploader 空操作驗證"""

    def test_register_collection_no_error(self):
        """register_collection 不報錯"""
        uploader = NullBatchUploader()
        uploader.register_collection("test_col")  # 不應拋出例外

    async def test_enqueue_no_error(self):
        """enqueue 不報錯"""
        uploader = NullBatchUploader()
        await uploader.enqueue("test_col", {"key": "value"})  # 不應拋出例外

    async def test_health_check_returns_true(self):
        """health_check 永遠回傳 True"""
        uploader = NullBatchUploader()
        result = await uploader.health_check()
        assert result is True


# ======================== InMemoryBatchUploader ========================


class TestInMemoryBatchUploader:
    """InMemoryBatchUploader 功能測試"""

    async def test_register_and_enqueue_flow(self):
        """完整流程：register → enqueue → get_documents"""
        uploader = InMemoryBatchUploader()
        uploader.register_collection("col_a")
        await uploader.enqueue("col_a", {"x": 1})
        await uploader.enqueue("col_a", {"x": 2})

        docs = uploader.get_documents("col_a")
        assert len(docs) == 2
        assert docs[0] == {"x": 1}
        assert docs[1] == {"x": 2}

    async def test_enqueue_auto_creates_collection(self):
        """未註冊的 collection 自動建立"""
        uploader = InMemoryBatchUploader()
        await uploader.enqueue("unregistered", {"auto": True})

        docs = uploader.get_documents("unregistered")
        assert len(docs) == 1
        assert docs[0] == {"auto": True}

    async def test_get_documents_returns_copy(self):
        """get_documents 回傳副本，修改不影響內部"""
        uploader = InMemoryBatchUploader()
        await uploader.enqueue("col", {"val": 1})

        docs = uploader.get_documents("col")
        docs.append({"val": 999})
        assert len(uploader.get_documents("col")) == 1

    async def test_get_documents_empty_collection(self):
        """對不存在的 collection 查詢回傳空列表"""
        uploader = InMemoryBatchUploader()
        assert uploader.get_documents("nonexistent") == []

    async def test_clear_specific_collection(self):
        """clear 指定 collection 只清除該 collection"""
        uploader = InMemoryBatchUploader()
        await uploader.enqueue("a", {"v": 1})
        await uploader.enqueue("b", {"v": 2})

        uploader.clear("a")
        assert uploader.get_documents("a") == []
        assert len(uploader.get_documents("b")) == 1

    async def test_clear_all(self):
        """clear(None) 清除全部"""
        uploader = InMemoryBatchUploader()
        await uploader.enqueue("a", {"v": 1})
        await uploader.enqueue("b", {"v": 2})

        uploader.clear()
        assert uploader.get_all_documents() == {}

    async def test_get_all_documents(self):
        """get_all_documents 回傳所有 collection 的文件"""
        uploader = InMemoryBatchUploader()
        await uploader.enqueue("x", {"k": 1})
        await uploader.enqueue("y", {"k": 2})
        await uploader.enqueue("y", {"k": 3})

        all_docs = uploader.get_all_documents()
        assert len(all_docs["x"]) == 1
        assert len(all_docs["y"]) == 2

    async def test_get_all_documents_returns_copy(self):
        """get_all_documents 回傳副本"""
        uploader = InMemoryBatchUploader()
        await uploader.enqueue("c", {"a": 1})

        result = uploader.get_all_documents()
        result["c"].append({"a": 999})
        assert len(uploader.get_documents("c")) == 1

    async def test_health_check_returns_true(self):
        """health_check 永遠回傳 True"""
        uploader = InMemoryBatchUploader()
        assert await uploader.health_check() is True

    def test_thread_safety_concurrent_enqueue(self):
        """多執行緒 concurrent enqueue 不遺失資料"""
        uploader = InMemoryBatchUploader()
        num_threads = 10
        docs_per_thread = 100
        barrier = threading.Barrier(num_threads)

        async def _enqueue_batch(tid: int):
            for i in range(docs_per_thread):
                await uploader.enqueue("col", {"tid": tid, "i": i})

        def _worker(tid: int):
            barrier.wait()
            asyncio.run(_enqueue_batch(tid))

        threads = [threading.Thread(target=_worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        docs = uploader.get_documents("col")
        assert len(docs) == num_threads * docs_per_thread
