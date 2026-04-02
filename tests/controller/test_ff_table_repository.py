"""Tests for FFTableRepository implementations: JsonFFTableRepository, MongoFFTableRepository."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.controller.compensator import (
    FFTableRepository,
    JsonFFTableRepository,
    MongoFFTableRepository,
)

# ===========================================================================
# Protocol conformance
# ===========================================================================


class TestFFTableRepositoryProtocol:
    def test_json_repo_satisfies_protocol(self):
        repo = JsonFFTableRepository(path="/tmp/unused.json")
        assert isinstance(repo, FFTableRepository)

    def test_mongo_repo_satisfies_protocol(self):
        repo = MongoFFTableRepository(collection=MagicMock())
        assert isinstance(repo, FFTableRepository)


# ===========================================================================
# JsonFFTableRepository
# ===========================================================================


class TestJsonFFTableRepository:
    def test_save_load_roundtrip(self, tmp_path):
        """Save a table and load it back — values should match."""
        path = str(tmp_path / "ff_table.json")
        repo = JsonFFTableRepository(path=path)

        table = {-10: 0.95, 0: 1.0, 5: 1.05, 10: 1.12}
        repo.save(table)
        loaded = repo.load()

        assert loaded is not None
        assert loaded == table

    def test_load_nonexistent_file_returns_none(self, tmp_path):
        """Loading from a path that doesn't exist should return None."""
        path = str(tmp_path / "does_not_exist.json")
        repo = JsonFFTableRepository(path=path)
        result = repo.load()
        assert result is None

    def test_load_empty_json_returns_none(self, tmp_path):
        """An empty JSON object {} should return None."""
        path = tmp_path / "empty.json"
        path.write_text("{}", encoding="utf-8")
        repo = JsonFFTableRepository(path=str(path))
        result = repo.load()
        assert result is None

    def test_load_corrupt_json_returns_none(self, tmp_path):
        """Corrupt JSON should return None (not raise)."""
        path = tmp_path / "corrupt.json"
        path.write_text("not valid json {{", encoding="utf-8")
        repo = JsonFFTableRepository(path=str(path))
        result = repo.load()
        assert result is None

    def test_save_creates_parent_directories(self, tmp_path):
        """save() should create intermediate directories if needed."""
        path = str(tmp_path / "sub" / "dir" / "ff.json")
        repo = JsonFFTableRepository(path=path)
        repo.save({0: 1.0})
        loaded = repo.load()
        assert loaded is not None
        assert loaded[0] == pytest.approx(1.0)

    def test_keys_converted_to_int_on_load(self, tmp_path):
        """JSON keys are strings; load() should convert them back to int."""
        path = str(tmp_path / "ff_table.json")
        repo = JsonFFTableRepository(path=path)
        repo.save({-5: 0.98, 0: 1.0, 5: 1.03})
        loaded = repo.load()
        assert all(isinstance(k, int) for k in loaded.keys())
        assert all(isinstance(v, float) for v in loaded.values())


# ===========================================================================
# MongoFFTableRepository
# ===========================================================================


class TestMongoFFTableRepository:
    def test_sync_load_returns_none(self):
        """sync load() always returns None — MongoDB requires async."""
        repo = MongoFFTableRepository(collection=MagicMock(), document_id="test")
        assert repo.load() is None

    @pytest.mark.asyncio
    async def test_async_load_existing_document(self):
        """async_load() should parse a document with 'table' field."""
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "_id": "ff_table",
                "table": {"0": 1.0, "5": 1.05, "-10": 0.92},
            }
        )
        repo = MongoFFTableRepository(collection=mock_collection, document_id="ff_table")
        result = await repo.async_load()

        assert result is not None
        assert result == {0: 1.0, 5: 1.05, -10: 0.92}
        mock_collection.find_one.assert_awaited_once_with({"_id": "ff_table"})

    @pytest.mark.asyncio
    async def test_async_load_no_document_returns_none(self):
        """async_load() returns None when no document found."""
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        repo = MongoFFTableRepository(collection=mock_collection)
        result = await repo.async_load()
        assert result is None

    @pytest.mark.asyncio
    async def test_async_load_document_without_table_key(self):
        """Document exists but has no 'table' field -> None."""
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value={"_id": "ff_table", "other": "data"})
        repo = MongoFFTableRepository(collection=mock_collection)
        result = await repo.async_load()
        assert result is None

    @pytest.mark.asyncio
    async def test_async_load_exception_returns_none(self):
        """If find_one raises, async_load should return None (not propagate)."""
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(side_effect=Exception("connection lost"))
        repo = MongoFFTableRepository(collection=mock_collection)
        result = await repo.async_load()
        assert result is None

    @pytest.mark.asyncio
    async def test_async_save_calls_update_one(self):
        """_async_save should call update_one with upsert=True."""
        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock()
        repo = MongoFFTableRepository(collection=mock_collection, document_id="my_ff")

        table = {0: 1.0, 5: 1.05}
        await repo._async_save(table)

        mock_collection.update_one.assert_awaited_once()
        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"_id": "my_ff"}
        assert call_args[1]["upsert"] is True
        # The $set should contain stringified keys
        set_data = call_args[0][1]["$set"]
        assert set_data["table"] == {"0": 1.0, "5": 1.05}

    @pytest.mark.asyncio
    async def test_async_save_exception_does_not_propagate(self):
        """If update_one raises, _async_save should not propagate."""
        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(side_effect=Exception("write error"))
        repo = MongoFFTableRepository(collection=mock_collection)
        # Should not raise
        await repo._async_save({0: 1.0})

    def test_custom_document_id(self):
        """document_id should be customizable."""
        repo = MongoFFTableRepository(collection=MagicMock(), document_id="custom_id")
        assert repo._doc_id == "custom_id"

    def test_default_document_id(self):
        """Default document_id is 'ff_table'."""
        repo = MongoFFTableRepository(collection=MagicMock())
        assert repo._doc_id == "ff_table"
