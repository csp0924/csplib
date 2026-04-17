import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.mongo.config import UploaderConfig
from csp_lib.mongo.uploader import MongoBatchUploader
from csp_lib.mongo.writer import WriteResult


class TestMongoBatchUploader:
    def _make_uploader(self, write_result=None):
        mock_db = MagicMock()
        config = UploaderConfig(flush_interval=1, max_retry_count=2)
        uploader = MongoBatchUploader(mock_db, config)
        if write_result is not None:
            uploader._writer = MagicMock()
            uploader._writer.write_batch = AsyncMock(return_value=write_result)
        return uploader

    @pytest.mark.asyncio
    async def test_flush_empty_queues(self):
        uploader = self._make_uploader(WriteResult(success=True))
        uploader.register_collection("col1")
        await uploader.flush_all()
        # No data to flush, writer should not be called
        uploader._writer.write_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_flush_success_resets_retry(self):
        uploader = self._make_uploader(WriteResult(success=True, inserted_count=1))
        await uploader.enqueue("col1", {"a": 1})
        uploader._retry_counts["col1"] = 2
        await uploader.flush_all()
        assert uploader._retry_counts["col1"] == 0

    @pytest.mark.asyncio
    async def test_flush_failure_restores_documents(self):
        uploader = self._make_uploader(WriteResult(success=False, error_message="fail"))
        await uploader.enqueue("col1", {"a": 1})
        await uploader.flush_all()
        # Document should be restored to the queue for retry
        assert await uploader._queues["col1"].size() == 1
        assert uploader._retry_counts["col1"] == 1

    @pytest.mark.asyncio
    async def test_max_retry_exceeded_drops_data(self):
        uploader = self._make_uploader(WriteResult(success=False, error_message="fail"))
        await uploader.enqueue("col1", {"a": 1})
        uploader._retry_counts["col1"] = 2  # already at max
        await uploader.flush_all()
        # Data should be dropped, retry count reset
        assert uploader._retry_counts["col1"] == 0

    @pytest.mark.asyncio
    async def test_enqueue_auto_registers(self):
        uploader = self._make_uploader(WriteResult(success=True, inserted_count=1))
        await uploader.enqueue("new_col", {"x": 1})
        assert "new_col" in uploader._queues

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        mock_db = MagicMock()
        uploader = MongoBatchUploader(mock_db)
        uploader.start()
        assert uploader._flush_task is not None
        assert not uploader._flush_task.done()
        await uploader.stop()


class TestThresholdEventFlush:
    """
    WI-MB-01 / WI-MB-02 — Threshold 即時喚醒與多事件等待

    既有實作 `_flush_loop` 只用 `asyncio.wait_for(stop_event.wait(), timeout=flush_interval)`
    單事件等待。當 queue 達到 `batch_size_threshold` 時，無法即時喚醒，
    必須等到 `flush_interval` 到期才 flush。極端情況（queue 累積到 max_queue_size）
    會導致最舊資料被 `popleft()` 丟棄（silent data loss）。

    以下測試設定刻意把 `flush_interval` 拉到 10 秒，只有 threshold 即時路徑
    能在 2 秒內觸發 flush。修復前測試 A 必會 FAIL。
    """

    def _make_uploader(
        self,
        batch_size_threshold: int = 50,
        flush_interval: int = 10,
        max_queue_size: int = 10000,
    ) -> MongoBatchUploader:
        """建立一個 mock writer 的 uploader，write_batch 為 AsyncMock"""
        mock_db = MagicMock()
        config = UploaderConfig(
            flush_interval=flush_interval,
            batch_size_threshold=batch_size_threshold,
            max_queue_size=max_queue_size,
            max_retry_count=3,
        )
        uploader = MongoBatchUploader(mock_db, config)
        # 用 AsyncMock 取代 writer.write_batch，觀察 await_count
        uploader._writer = MagicMock()
        uploader._writer.write_batch = AsyncMock(return_value=WriteResult(success=True, inserted_count=0))
        return uploader

    async def _wait_until_flushed(
        self,
        uploader: MongoBatchUploader,
        timeout: float,
    ) -> float:
        """
        輪詢等待 write_batch 被呼叫，回傳觀察到 flush 發生時所經過的秒數。
        若 timeout 內未 flush，回傳 timeout（由呼叫端斷言）。
        """
        import time

        start = time.perf_counter()
        deadline = start + timeout
        while time.perf_counter() < deadline:
            if uploader._writer.write_batch.await_count > 0:
                return time.perf_counter() - start
            # 讓 _flush_loop coroutine 有機會執行
            await asyncio.sleep(0.05)
        return timeout

    @pytest.mark.asyncio
    async def test_threshold_triggers_flush_before_interval(self):
        """
        測試 A — threshold 即時喚醒（WI-MB-01/02 核心 bug）

        Setup: batch_size_threshold=50, flush_interval=10
        Action: 在 100ms 內 enqueue 50 筆
        Expectation: 2 秒內觸發 flush（遠小於 flush_interval=10）

        修復前：_flush_loop 只靠 timer 喚醒，必須等 10 秒才 flush → FAIL
        修復後：enqueue 達閾值時應主動 notify _flush_loop → PASS
        """
        import time

        uploader = self._make_uploader(batch_size_threshold=50, flush_interval=10)
        uploader.start()

        try:
            # 關鍵：先讓 _flush_loop 真正進入 asyncio.wait_for(stop_event.wait())
            # 否則第一次 iteration 還沒執行前 enqueue 就把 queue 灌滿，
            # 變成「首次 iteration 已看到 size >= threshold」的快樂路徑，
            # 無法重現「等待中無法被 threshold 喚醒」的 bug。
            # 0.3s 足夠 _flush_loop 完成首次 iteration 並進入 wait_for。
            await asyncio.sleep(0.3)

            # 此時 writer 尚未被呼叫（queue 還是空的）
            assert uploader._writer.write_batch.await_count == 0, "初始 0.3s 內不應有任何 flush（queue 為空）"

            # 在 100ms 內塞入 50 筆，預期 queue 立即達到閾值
            t0 = time.perf_counter()
            for i in range(50):
                await uploader.enqueue("col_a", {"i": i})
            enqueue_elapsed = time.perf_counter() - t0
            assert enqueue_elapsed < 1.0, f"enqueue 本身應在 1 秒內完成，實際 {enqueue_elapsed:.3f}s"

            # 等最多 2 秒觀察 flush（若需等 10 秒的 timer 就會 FAIL）
            elapsed = await self._wait_until_flushed(uploader, timeout=2.0)

            # 關鍵斷言：必須在 2 秒內發生 flush
            assert uploader._writer.write_batch.await_count >= 1, (
                f"threshold 達到後 2 秒內未 flush（WI-MB-01 bug）；"
                f"await_count={uploader._writer.write_batch.await_count}"
            )
            assert elapsed < 2.0, f"flush 延遲 {elapsed:.3f}s 超過 2 秒上限"

            # 確認 flush 的是正確的 collection 且包含 50 筆
            call_args = uploader._writer.write_batch.await_args_list[0]
            assert call_args.args[0] == "col_a"
            assert len(call_args.args[1]) == 50
        finally:
            await uploader.stop()

    @pytest.mark.asyncio
    async def test_stop_does_not_leak_waiter_tasks(self):
        """
        測試 B — 停止後不留下 waiter task

        Setup: 啟動 uploader 後立即 stop
        Expectation: _flush_task 已 done，且 event loop 中無殘留的 _flush_loop task

        修復前後皆應 PASS（既有 stop() 已正確 await _flush_task），
        此測試作為「多事件等待改動後不能破壞 stop 語義」的回歸保護。
        """
        uploader = self._make_uploader(batch_size_threshold=50, flush_interval=10)
        uploader.start()
        flush_task = uploader._flush_task
        assert flush_task is not None

        # 給 _flush_loop 一點時間真正進入 wait
        await asyncio.sleep(0.05)

        await uploader.stop()

        # 1) _flush_task 必須 done
        assert flush_task.done(), "stop() 後 _flush_task 應已完成"
        assert not flush_task.cancelled() or flush_task.cancelled(), "task 狀態合法（done 或 cancelled 皆可）"

        # 2) event loop 中不應殘留 _flush_loop 衍生的 task
        current = asyncio.current_task()
        leaked = [
            t
            for t in asyncio.all_tasks()
            if t is not current and not t.done() and "_flush_loop" in (t.get_coro().__qualname__ or "")
        ]
        assert not leaked, f"stop() 後殘留 _flush_loop 相關 task: {leaked}"

    @pytest.mark.asyncio
    async def test_below_threshold_does_not_flush_within_interval(self):
        """
        測試 C — baseline，未達閾值不應提前 flush

        Setup: batch_size_threshold=100, flush_interval=10
        Action: enqueue 50 筆（未達閾值）
        Expectation: 2 秒內不發生 flush

        此測試在修復前後都應 PASS，確保 threshold notify 不會誤觸發。
        """
        uploader = self._make_uploader(batch_size_threshold=100, flush_interval=10)
        uploader.start()

        try:
            # 塞入 50 筆，未達 threshold=100
            for i in range(50):
                await uploader.enqueue("col_b", {"i": i})

            # 等 2 秒，預期不會 flush（因為未達閾值且 flush_interval=10）
            await asyncio.sleep(2.0)

            assert uploader._writer.write_batch.await_count == 0, (
                f"未達 threshold 不應在 flush_interval 內 flush，"
                f"實際 await_count={uploader._writer.write_batch.await_count}"
            )
        finally:
            await uploader.stop()


# ======================== v0.8.2 新增: write_immediate / writer property ========================


class TestWriteImmediate:
    """
    v0.8.2：MongoBatchUploader.write_immediate 與 writer property

    write_immediate 繞過 batch queue，直接委派給 MongoWriter.write_batch([document])，
    不應影響現有 _queues 狀態。writer property 僅對外暴露內部 _writer，read-only。
    """

    def _make_uploader(self, write_result: WriteResult | None = None) -> MongoBatchUploader:
        """建立一個 writer 為 AsyncMock 的 uploader（不啟動 flush loop）"""
        mock_db = MagicMock()
        config = UploaderConfig(flush_interval=10, max_retry_count=2)
        uploader = MongoBatchUploader(mock_db, config)
        uploader._writer = MagicMock()
        uploader._writer.write_batch = AsyncMock(
            return_value=write_result or WriteResult(success=True, inserted_count=1)
        )
        return uploader

    @pytest.mark.asyncio
    async def test_write_immediate_calls_writer_write_batch_with_single_document(self):
        """write_immediate 應以 [document] 呼叫 MongoWriter.write_batch"""
        uploader = self._make_uploader()
        doc = {"alarm_key": "d1:disc:X", "event": "triggered"}

        result = await uploader.write_immediate("alarm_history", doc)

        uploader._writer.write_batch.assert_awaited_once()
        call_args = uploader._writer.write_batch.await_args
        assert call_args.args[0] == "alarm_history"
        assert call_args.args[1] == [doc]
        assert result.success is True
        assert result.inserted_count == 1

    @pytest.mark.asyncio
    async def test_write_immediate_does_not_touch_queue(self):
        """write_immediate 不應影響任何 collection 的 queue"""
        uploader = self._make_uploader()
        # 預先建立一個 queue 確認不會被誤用
        uploader.register_collection("alarm_history")
        queue_before = uploader._queues["alarm_history"]
        size_before = await queue_before.size()

        await uploader.write_immediate("alarm_history", {"a": 1})

        # queue 大小沒變化
        assert await uploader._queues["alarm_history"].size() == size_before

    @pytest.mark.asyncio
    async def test_write_immediate_propagates_writer_failure(self):
        """writer.write_batch 失敗時 write_immediate 應回傳同樣失敗結果"""
        fail_result = WriteResult(success=False, error_message="mongo down")
        uploader = self._make_uploader(write_result=fail_result)

        result = await uploader.write_immediate("col", {"x": 1})

        assert result.success is False
        assert result.error_message == "mongo down"


class TestWriterProperty:
    """v0.8.2：uploader.writer read-only property"""

    def test_writer_property_returns_internal_writer(self):
        """writer property 應回傳內部 _writer 實例本身"""
        mock_db = MagicMock()
        uploader = MongoBatchUploader(mock_db)

        assert uploader.writer is uploader._writer

    def test_writer_property_is_read_only(self):
        """writer property 無 setter，直接賦值應 AttributeError"""
        mock_db = MagicMock()
        uploader = MongoBatchUploader(mock_db)

        with pytest.raises(AttributeError):
            uploader.writer = MagicMock()  # type: ignore[misc]
