# =============== Manager Command - Repository ===============
#
# 指令記錄儲存庫
#
# 提供指令記錄的持久化：
#   - CommandRepository: Protocol 介面
#   - MongoCommandRepository: MongoDB 實作

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from csp_lib.core import get_logger

from .schema import CommandRecord, CommandStatus

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

logger = get_logger(__name__)


class CommandRepository(Protocol):
    """指令記錄儲存庫介面"""

    async def create(self, record: CommandRecord) -> str:
        """
        建立指令記錄

        Args:
            record: 指令記錄

        Returns:
            記錄 ID
        """
        ...

    async def update_status(
        self,
        command_id: str,
        status: CommandStatus,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> bool:
        """
        更新指令狀態

        Args:
            command_id: 指令 ID
            status: 新狀態
            result: 執行結果
            error_message: 錯誤訊息

        Returns:
            是否更新成功
        """
        ...

    async def get(self, command_id: str) -> CommandRecord | None:
        """
        取得指令記錄

        Args:
            command_id: 指令 ID

        Returns:
            指令記錄，不存在時返回 None
        """
        ...

    async def list_by_device(self, device_id: str, limit: int = 100) -> list[CommandRecord]:
        """
        取得設備的指令記錄

        Args:
            device_id: 設備 ID
            limit: 最大數量

        Returns:
            指令記錄列表
        """
        ...


class MongoCommandRepository:
    """
    MongoDB 指令記錄儲存庫

    將指令記錄儲存至 MongoDB。

    Example:
        ```python
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient("mongodb://localhost:27017")
        collection = client["my_db"]["commands"]
        repo = MongoCommandRepository(collection)

        # 建立記錄
        record = CommandRecord.from_command(command)
        await repo.create(record)

        # 更新狀態
        await repo.update_status(command_id, CommandStatus.SUCCESS, result)
        ```
    """

    COLLECTION_NAME = "commands"

    def __init__(self, db: AsyncIOMotorDatabase, collection: str = COLLECTION_NAME) -> None:
        """
        初始化 MongoDB 儲存庫

        Args:
            collection: MongoDB collection
        """
        self._collection = db[collection]

    async def create(self, record: CommandRecord) -> str:
        """建立指令記錄"""
        doc = record.to_dict()
        result = await self._collection.insert_one(doc)
        logger.debug(f"指令記錄已建立: {record.command_id}")
        return str(result.inserted_id)

    async def update_status(
        self,
        command_id: str,
        status: CommandStatus,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> bool:
        """更新指令狀態"""
        from datetime import timezone

        update: dict[str, Any] = {
            "status": status.value,
        }

        if status == CommandStatus.EXECUTING:
            update["executed_at"] = datetime.now(timezone.utc)
        elif status in (CommandStatus.SUCCESS, CommandStatus.FAILED, CommandStatus.DEVICE_NOT_FOUND):
            update["completed_at"] = datetime.now(timezone.utc)

        if result is not None:
            update["result"] = result

        if error_message is not None:
            update["error_message"] = error_message

        mongo_result = await self._collection.update_one(
            {"command_id": command_id},
            {"$set": update},
        )

        if mongo_result.modified_count > 0:
            logger.debug(f"指令狀態已更新: {command_id} -> {status.value}")
            return True
        return False

    async def get(self, command_id: str) -> CommandRecord | None:
        """取得指令記錄"""
        doc = await self._collection.find_one({"command_id": command_id})
        if doc:
            return CommandRecord.from_dict(doc)
        return None

    async def list_by_device(self, device_id: str, limit: int = 100) -> list[CommandRecord]:
        """取得設備的指令記錄"""
        cursor = self._collection.find({"device_id": device_id}).sort("created_at", -1).limit(limit)
        records = []
        async for doc in cursor:
            records.append(CommandRecord.from_dict(doc))
        return records


__all__ = [
    "CommandRepository",
    "MongoCommandRepository",
]
