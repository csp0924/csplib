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
