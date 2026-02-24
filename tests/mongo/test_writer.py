from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.mongo.writer import MongoWriter


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
