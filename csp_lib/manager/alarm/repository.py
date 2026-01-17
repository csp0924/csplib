# =============== Manager Alarm - Repository ===============
#
# 告警資料存取層
#
# 提供告警資料的 CRUD 操作：
#   - AlarmRepository: 資料存取介面 (Protocol)
#   - MongoAlarmRepository: MongoDB 實作
#
# 設計原則：
#   - 依賴倒置：業務層依賴 Protocol，不依賴具體實作
#   - 單一職責：僅負責資料存取，不包含業務邏輯

from datetime import datetime
from typing import Protocol

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import IndexModel

from .schema import AlarmRecord, AlarmStatus


class AlarmRepository(Protocol):
    """
    告警 Repository 介面

    定義告警資料存取的標準介面，遵循依賴倒置原則。
    業務層應依賴此 Protocol，而非具體實作。
    """

    async def upsert(self, record: AlarmRecord) -> tuple[str, bool]:
        """新增或更新告警記錄"""
        ...

    async def resolve(self, alarm_key: str, resolved_at: datetime) -> bool:
        """解除告警（更新 resolved_at 與 status）"""
        ...

    async def get_active_alarms(self) -> list[AlarmRecord]:
        """取得所有進行中的告警"""
        ...

    async def get_active_by_device(self, device_id: str) -> list[AlarmRecord]:
        """取得指定設備的進行中告警"""
        ...


class MongoAlarmRepository:
    """
    MongoDB 告警 Repository 實作

    使用 Motor 非同步驅動實作 AlarmRepository 介面。
    支援告警的 CRUD 操作與索引管理。

    Attributes:
        COLLECTION_NAME: 預設 collection 名稱
    """

    COLLECTION_NAME = "alarms"

    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str = COLLECTION_NAME) -> None:
        """
        初始化 MongoDB Repository

        Args:
            db: Motor 非同步資料庫連線
            collection_name: Collection 名稱（預設 "alarms"）
        """
        self._db = db
        self._collection = db[collection_name]

    async def ensure_indexes(self) -> None:
        """
        建立資料庫索引

        應於應用程式啟動時呼叫一次。建立的索引包括：
        - alarm_key: 唯一鍵查詢
        - device_id: 設備篩選
        - status: 狀態篩選
        - (device_id, status): 複合查詢
        - occurred_at: 時間排序
        """
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
        """
        新增告警記錄

        若已存在相同 alarm_key 且狀態為 ACTIVE 的告警，則跳過新增。
        此設計避免重複寫入同一告警事件。

        Args:
            record: 告警記錄

        Returns:
            tuple[str, bool]: (告警 ID, 是否為新增)
                - 若為既有告警：返回既有 _id，is_new=False
                - 若為新告警：返回新 _id，is_new=True
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
        """
        解除告警

        將指定告警的狀態從 ACTIVE 更新為 RESOLVED，
        並記錄解除時間。僅更新狀態為 ACTIVE 的告警。

        Args:
            alarm_key: 告警唯一鍵
            resolved_at: 解除時間

        Returns:
            bool: 是否成功解除（True 表示有更新，False 表示無對應告警）
        """
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
        """
        取得所有進行中的告警

        Returns:
            list[AlarmRecord]: 所有狀態為 ACTIVE 的告警清單
        """
        cursor = self._collection.find(
            {
                "status": AlarmStatus.ACTIVE.value,
            }
        )
        return [AlarmRecord.from_document(doc) async for doc in cursor]

    async def get_active_by_device(self, device_id: str) -> list[AlarmRecord]:
        """
        取得指定設備的進行中告警

        Args:
            device_id: 設備識別碼

        Returns:
            list[AlarmRecord]: 該設備所有狀態為 ACTIVE 的告警清單
        """
        cursor = self._collection.find(
            {
                "device_id": device_id,
                "status": AlarmStatus.ACTIVE.value,
            }
        )
        return [AlarmRecord.from_document(doc) async for doc in cursor]
