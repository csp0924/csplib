# =============== Manager - MongoRepositoryBase 測試 ===============
#
# 驗證 MongoRepositoryBase 共用基底：
# - health_check 走 db.command("ping")，任何 Exception 回 False
# - ensure_indexes 預設 raise NotImplementedError（子類必須覆寫）
# - 三個 Mongo repo 皆繼承 MongoRepositoryBase
# - MongoCommandRepository 的 collection= 保留為 deprecated alias

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.manager.alarm.repository import MongoAlarmRepository
from csp_lib.manager.base import MongoRepositoryBase
from csp_lib.manager.command.repository import MongoCommandRepository
from csp_lib.manager.schedule.repository import MongoScheduleRepository


def _make_mock_db() -> MagicMock:
    """建立 Motor AsyncIOMotorDatabase 的最小 mock。"""
    db = MagicMock()
    db.command = AsyncMock()
    collection = MagicMock()
    collection.create_indexes = AsyncMock()
    db.__getitem__.return_value = collection
    return db


class TestMongoRepositoryBaseHealthCheck:
    """health_check 走 db.command('ping') 並吞例外。"""

    async def test_health_check_ok(self):
        db = _make_mock_db()

        class _Repo(MongoRepositoryBase):
            async def ensure_indexes(self) -> None:  # pragma: no cover
                pass

        repo = _Repo(db, "any_coll")
        assert await repo.health_check() is True
        db.command.assert_awaited_once_with("ping")

    async def test_health_check_returns_false_on_any_exception(self):
        db = _make_mock_db()
        db.command.side_effect = RuntimeError("connection refused")

        class _Repo(MongoRepositoryBase):
            async def ensure_indexes(self) -> None:  # pragma: no cover
                pass

        repo = _Repo(db, "any_coll")
        assert await repo.health_check() is False


class TestMongoRepositoryBaseEnsureIndexes:
    """ensure_indexes 預設 raise NotImplementedError，訊息含子類名。"""

    async def test_default_ensure_indexes_raises(self):
        db = _make_mock_db()

        class _Repo(MongoRepositoryBase):
            pass

        repo = _Repo(db, "any_coll")
        with pytest.raises(NotImplementedError, match="_Repo"):
            await repo.ensure_indexes()


class TestMongoRepoSubclassIdentity:
    """驗證三個 Mongo repo 皆繼承 MongoRepositoryBase。"""

    def test_alarm_repo_is_subclass(self):
        db = _make_mock_db()
        repo = MongoAlarmRepository(db)
        assert isinstance(repo, MongoRepositoryBase)

    def test_schedule_repo_is_subclass(self):
        db = _make_mock_db()
        repo = MongoScheduleRepository(db)
        assert isinstance(repo, MongoRepositoryBase)

    def test_command_repo_is_subclass(self):
        db = _make_mock_db()
        repo = MongoCommandRepository(db)
        assert isinstance(repo, MongoRepositoryBase)


class TestMongoCommandRepoCollectionAlias:
    """MongoCommandRepository 的 collection= 為 deprecated alias。"""

    def test_new_collection_name_param(self):
        db = _make_mock_db()
        repo = MongoCommandRepository(db, collection_name="cmds_v2")
        db.__getitem__.assert_called_with("cmds_v2")
        # 無 DeprecationWarning
        assert isinstance(repo, MongoRepositoryBase)

    def test_legacy_collection_kwarg_emits_warning(self):
        db = _make_mock_db()
        with pytest.warns(DeprecationWarning, match="collection_name"):
            MongoCommandRepository(db, collection="cmds_legacy")
        db.__getitem__.assert_called_with("cmds_legacy")

    def test_default_collection_name(self):
        db = _make_mock_db()
        MongoCommandRepository(db)
        db.__getitem__.assert_called_with(MongoCommandRepository.COLLECTION_NAME)

    def test_mixing_collection_name_and_collection_raises(self):
        db = _make_mock_db()
        with pytest.raises(ValueError, match="cannot specify both"):
            MongoCommandRepository(db, collection_name="a", collection="b")
