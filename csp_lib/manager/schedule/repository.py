# =============== Manager Schedule - Repository ===============
#
# 排程規則資料存取層
#
# 提供排程規則的查詢操作：
#   - ScheduleRepository: 資料存取介面 (Protocol)
#   - MongoScheduleRepository: MongoDB 實作
#
# 設計原則：
#   - 依賴倒置：業務層依賴 Protocol，不依賴具體實作
#   - 時間比對在 Python 端完成（彈性處理跨午夜等邏輯）

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from csp_lib.manager.base import AsyncRepository

from . import matcher
from .schema import ScheduleRule

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


@runtime_checkable
class ScheduleRepository(AsyncRepository, Protocol):
    """
    排程 Repository 介面

    定義排程資料存取的標準介面，遵循依賴倒置原則。

    繼承自 ``AsyncRepository``，統一所有 Repository 的健康檢查介面。
    """

    async def find_active_rules(self, site_id: str, now: datetime) -> list[ScheduleRule]:
        """查詢當前時間匹配的啟用規則（依 priority DESC 排序）"""
        ...

    async def get_all_enabled(self, site_id: str) -> list[ScheduleRule]:
        """取得指定站點所有啟用的規則"""
        ...

    async def upsert(self, rule: ScheduleRule) -> str:
        """新增或更新排程規則"""
        ...


class MongoScheduleRepository:
    """
    MongoDB 排程 Repository 實作

    使用 Motor 非同步驅動實作 ScheduleRepository 介面。
    時間/星期/日期的匹配邏輯在 Python 端完成。

    Attributes:
        COLLECTION_NAME: 預設 collection 名稱
    """

    COLLECTION_NAME = "schedule_rules"

    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str = COLLECTION_NAME) -> None:
        """
        初始化 MongoDB Repository

        Args:
            db: Motor 非同步資料庫連線
            collection_name: Collection 名稱（預設 "schedule_rules"）
        """
        self._db = db
        self._collection = db[collection_name]

    async def health_check(self) -> bool:
        """
        檢查 MongoDB 連線是否正常

        Returns:
            bool: True 表示連線正常
        """
        try:
            await self._db.command("ping")
            return True
        except Exception:
            return False

    async def ensure_indexes(self) -> None:
        """
        建立資料庫索引

        應於應用程式啟動時呼叫一次。
        """
        from pymongo import IndexModel

        await self._collection.create_indexes(
            [
                IndexModel([("site_id", 1), ("enabled", 1)]),
                IndexModel([("site_id", 1), ("priority", -1)]),
            ]
        )

    async def find_active_rules(self, site_id: str, now: datetime) -> list[ScheduleRule]:
        """
        查詢當前時間匹配的啟用規則

        先從 MongoDB 取得所有啟用的規則，再於 Python 端過濾
        時間/星期/日期條件，最後依 priority DESC 排序。

        跨午夜處理：若 start_time > end_time（如 22:00-06:00），
        匹配 now >= start_time OR now < end_time。

        Args:
            site_id: 站點識別碼
            now: 當前時間（含時區）

        Returns:
            list[ScheduleRule]: 匹配的規則列表（priority DESC）
        """
        all_enabled = await self.get_all_enabled(site_id)

        now_time = now.strftime("%H:%M")
        now_weekday = now.weekday()  # 0=Mon..6=Sun
        now_date = now.date()

        matched: list[ScheduleRule] = []
        for rule in all_enabled:
            if not self._matches_time(rule, now_time):
                continue
            if not self._matches_schedule(rule, now_weekday, now_date):
                continue
            matched.append(rule)

        # Priority DESC
        matched.sort(key=lambda r: r.priority, reverse=True)
        return matched

    async def get_all_enabled(self, site_id: str) -> list[ScheduleRule]:
        """
        取得指定站點所有啟用的規則

        Args:
            site_id: 站點識別碼

        Returns:
            list[ScheduleRule]: 啟用的規則列表
        """
        cursor = self._collection.find({"site_id": site_id, "enabled": True})
        return [ScheduleRule.from_document(doc) async for doc in cursor]

    async def upsert(self, rule: ScheduleRule) -> str:
        """
        新增或更新排程規則

        使用 (site_id, name) 作為唯一鍵進行 upsert。

        Args:
            rule: 排程規則

        Returns:
            str: 文件 ID
        """
        result = await self._collection.update_one(
            {"site_id": rule.site_id, "name": rule.name},
            {"$set": rule.to_document()},
            upsert=True,
        )
        if result.upserted_id:
            return str(result.upserted_id)
        return rule.name

    @staticmethod
    def _matches_time(rule: ScheduleRule, now_time: str) -> bool:
        """檢查時間是否匹配（委派至 matcher 模組）

        Args:
            rule: 排程規則
            now_time: 當前時間（"HH:MM" 格式）

        Returns:
            bool: 是否匹配
        """
        return matcher.matches_time(rule, now_time)

    @staticmethod
    def _matches_schedule(rule: ScheduleRule, now_weekday: int, now_date: date) -> bool:
        """檢查排程類型條件是否匹配（委派至 matcher 模組）

        Args:
            rule: 排程規則
            now_weekday: 當前星期幾（0=Mon..6=Sun）
            now_date: 當前日期

        Returns:
            bool: 是否匹配
        """
        return matcher.matches_schedule(rule, now_weekday, now_date)


__all__ = [
    "MongoScheduleRepository",
    "ScheduleRepository",
]
