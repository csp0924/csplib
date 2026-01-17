"""告警 Repository - 資料存取層"""

from datetime import datetime
from typing import Protocol

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import IndexModel

from .schema import AlarmRecord, AlarmStatus


class AlarmRepository(Protocol):
    """告警 Repository Protocol"""

    async def upsert(self, record: AlarmRecord) -> tuple[str, bool]: ...
    async def resolve(self, alarm_key: str, resolved_at: datetime) -> bool: ...
    async def get_active_alarms(self) -> list[AlarmRecord]: ...
    async def get_active_by_device(self, device_id: str) -> list[AlarmRecord]: ...


class MongoAlarmRepository:
    """MongoDB 告警 Repository 實作"""

    COLLECTION_NAME = "alarms"

    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str = COLLECTION_NAME) -> None:
        self._db = db
        self._collection = db[collection_name]

    async def ensure_indexes(self) -> None:
        """建立索引（啟動時呼叫）"""
        await self._collection.create_indexes(
            [
                IndexModel([("alarm_key", 1)]),
                IndexModel([("device_id", 1)]),
                IndexModel([("status", 1)]),
                IndexModel([("device_id", 1), ("status", 1)]),
                IndexModel([("occurred_at", -1)]),
            ]
        )

    async def upsert(self, record: AlarmRecord) -> tuple[str, bool]:
        """新增告警（若已有 ACTIVE 則跳過）

        Returns:
            (alarm_id, is_new): 告警 ID 與是否為新增
        """
        existing = await self._collection.find_one(
            {
                "alarm_key": record.alarm_key,
                "status": AlarmStatus.ACTIVE.value,
            }
        )

        if existing:
            return existing["_id"], False
        result = await self._collection.insert_one(record.to_document())
        return result.inserted_id, True

    async def resolve(self, alarm_key: str, resolved_at: datetime) -> bool:
        """解除告警"""
        result = await self._collection.update_one(
            {
                "alarm_key": alarm_key,
                "status": AlarmStatus.ACTIVE.value,
            },
            {
                "$set": {
                    "status": AlarmStatus.RESOLVED.value,
                    "resolved_at": resolved_at,
                }
            },
        )
        return result.modified_count == 1

    async def get_active_alarms(self) -> list[AlarmRecord]:
        """取得所有 ACTIVE 告警"""
        cursor = self._collection.find(
            {
                "status": AlarmStatus.ACTIVE.value,
            }
        )
        return [AlarmRecord.from_document(doc) async for doc in cursor]

    async def get_active_by_device(self, device_id: str) -> list[AlarmRecord]:
        """取得指定設備的 ACTIVE 告警"""
        cursor = self._collection.find(
            {
                "device_id": device_id,
                "status": AlarmStatus.ACTIVE.value,
            }
        )
        return [AlarmRecord.from_document(doc) async for doc in cursor]
