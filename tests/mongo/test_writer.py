from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import BulkWriteError

from csp_lib.mongo.writer import MongoWriter, WriteResult


class TestMongoWriter:
    @pytest.mark.asyncio
    async def test_write_batch_success(self):
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.inserted_ids = ["id1", "id2"]
        mock_collection.insert_many = AsyncMock(return_value=mock_result)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        writer = MongoWriter(mock_db)
        result = await writer.write_batch("test_col", [{"a": 1}, {"b": 2}])
        assert result.success is True
        assert result.inserted_count == 2

    @pytest.mark.asyncio
    async def test_write_batch_empty(self):
        mock_db = MagicMock()
        writer = MongoWriter(mock_db)
        result = await writer.write_batch("test_col", [])
        assert result.success is True
        assert result.inserted_count == 0

    @pytest.mark.asyncio
    async def test_write_batch_db_error(self):
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_collection.insert_many = AsyncMock(side_effect=Exception("DB down"))
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        writer = MongoWriter(mock_db)
        result = await writer.write_batch("test_col", [{"a": 1}])
        assert result.success is False
        assert "DB down" in result.error_message


# ======================== WriteResult 向後相容測試 ========================


class TestWriteResultDefaults:
    """WriteResult 新增欄位不可影響既有呼叫點（v0.8.2 向後相容保護）"""

    def test_duplicate_key_count_default_is_zero(self):
        """未顯式設定時 duplicate_key_count 應為 0"""
        result = WriteResult(success=True, inserted_count=3)
        assert result.duplicate_key_count == 0

    def test_minimal_construction(self):
        """僅給 success 仍可建構（保持既有最小介面）"""
        result = WriteResult(success=False)
        assert result.inserted_count == 0
        assert result.duplicate_key_count == 0
        assert result.error_message is None


# ======================== ordered=False 路徑測試（v0.8.2）========================


def _make_writer_with_insert_mock(insert_many_mock: AsyncMock) -> MongoWriter:
    """輔助：以 MagicMock db + collection.insert_many 建立 MongoWriter"""
    mock_db = MagicMock()
    mock_collection = AsyncMock()
    mock_collection.insert_many = insert_many_mock
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    return MongoWriter(mock_db)


class TestWriteBatchUnordered:
    """
    ordered=False 時對 BulkWriteError 的重複鍵處理

    v0.8.2 LocalBufferedUploader replay 場景會呼叫 ordered=False，
    並以 inserted_count + duplicate_key_count 判定是否可標記 synced。
    """

    @pytest.mark.asyncio
    async def test_unordered_all_success_no_error(self):
        """全部成功（無 BulkWriteError）→ success=True, duplicate_key_count=0"""
        mock_result = MagicMock()
        mock_result.inserted_ids = ["id1", "id2", "id3"]
        insert_mock = AsyncMock(return_value=mock_result)
        writer = _make_writer_with_insert_mock(insert_mock)

        result = await writer.write_batch("col", [{"a": 1}, {"b": 2}, {"c": 3}], ordered=False)

        assert result.success is True
        assert result.inserted_count == 3
        assert result.duplicate_key_count == 0
        assert result.error_message is None
        # 確認 ordered=False 被正確傳遞
        call_kwargs = insert_mock.await_args.kwargs
        assert call_kwargs.get("ordered") is False

    @pytest.mark.asyncio
    async def test_unordered_all_duplicate_keys_success(self):
        """全部 duplicate（code=11000）→ success=True, 記錄 duplicate_key_count"""
        details = {
            "writeErrors": [
                {"code": 11000, "errmsg": "dup key 1"},
                {"code": 11000, "errmsg": "dup key 2"},
                {"code": 11000, "errmsg": "dup key 3"},
            ],
            "nInserted": 0,
        }
        insert_mock = AsyncMock(side_effect=BulkWriteError(details))
        writer = _make_writer_with_insert_mock(insert_mock)

        result = await writer.write_batch("col", [{"a": 1}, {"b": 2}, {"c": 3}], ordered=False)

        assert result.success is True
        assert result.inserted_count == 0
        assert result.duplicate_key_count == 3
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_unordered_partial_duplicate_partial_success(self):
        """部分 inserted + 部分 duplicate（全為 11000）→ success=True"""
        details = {
            "writeErrors": [
                {"code": 11000, "errmsg": "dup 1"},
                {"code": 11000, "errmsg": "dup 2"},
            ],
            "nInserted": 2,
        }
        insert_mock = AsyncMock(side_effect=BulkWriteError(details))
        writer = _make_writer_with_insert_mock(insert_mock)

        result = await writer.write_batch("col", [{"i": i} for i in range(4)], ordered=False)

        # 已 insert 2 筆 + duplicates 2 筆 = 4 筆文件全部「被處理」
        assert result.success is True
        assert result.inserted_count == 2
        assert result.duplicate_key_count == 2
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_unordered_mixed_duplicate_and_other_error_fails(self):
        """部分 duplicate + 部分非 duplicate（如 code=121）→ success=False"""
        details = {
            "writeErrors": [
                {"code": 11000, "errmsg": "dup key"},
                {"code": 121, "errmsg": "document validation failure"},
            ],
            "nInserted": 1,
        }
        insert_mock = AsyncMock(side_effect=BulkWriteError(details))
        writer = _make_writer_with_insert_mock(insert_mock)

        result = await writer.write_batch("col", [{"i": i} for i in range(3)], ordered=False)

        assert result.success is False
        assert result.inserted_count == 1
        assert result.duplicate_key_count == 1
        assert result.error_message is not None
        # non-dup error 應被反映於錯誤訊息
        assert "non-duplicate" in result.error_message

    @pytest.mark.asyncio
    async def test_unordered_all_non_duplicate_errors_fails(self):
        """全部非 duplicate 錯誤 → success=False, duplicate_key_count=0"""
        details = {
            "writeErrors": [
                {"code": 121, "errmsg": "validation fail 1"},
                {"code": 121, "errmsg": "validation fail 2"},
            ],
            "nInserted": 0,
        }
        insert_mock = AsyncMock(side_effect=BulkWriteError(details))
        writer = _make_writer_with_insert_mock(insert_mock)

        result = await writer.write_batch("col", [{"i": i} for i in range(2)], ordered=False)

        assert result.success is False
        assert result.duplicate_key_count == 0
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_unordered_non_bulk_write_error_still_propagated(self):
        """ordered=False 但非 BulkWriteError（如連線中斷）→ success=False"""
        insert_mock = AsyncMock(side_effect=ConnectionError("mongodb unreachable"))
        writer = _make_writer_with_insert_mock(insert_mock)

        result = await writer.write_batch("col", [{"a": 1}], ordered=False)

        assert result.success is False
        assert result.inserted_count == 0
        assert result.duplicate_key_count == 0
        assert "unreachable" in result.error_message

    @pytest.mark.asyncio
    async def test_ordered_true_default_does_not_trigger_duplicate_path(self):
        """ordered=True（預設）時 BulkWriteError 應當成一般錯誤（向後相容）"""
        details = {
            "writeErrors": [{"code": 11000, "errmsg": "dup key"}],
            "nInserted": 0,
        }
        insert_mock = AsyncMock(side_effect=BulkWriteError(details))
        writer = _make_writer_with_insert_mock(insert_mock)

        # 不指定 ordered，預設為 True
        result = await writer.write_batch("col", [{"a": 1}])

        # ordered=True 時即便是重複鍵也算錯誤
        assert result.success is False
        # duplicate_key_count 預設為 0，不走 BulkWriteError 分流
        assert result.duplicate_key_count == 0
        assert result.error_message is not None
