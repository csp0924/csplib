"""
MongoWriter 模組

負責將批次資料寫入 MongoDB，職責單一：執行寫入操作並回報結果。
"""

from dataclasses import dataclass
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from csp_lib.core import get_logger

logger = get_logger(__name__)


@dataclass
class WriteResult:
    """
    寫入結果

    Attributes:
        success: 是否成功
        inserted_count: 成功插入的文件數量
        error_message: 錯誤訊息（若失敗）
    """

    success: bool
    inserted_count: int = 0
    error_message: Optional[str] = None


class MongoWriter:
    """
    MongoDB 批次寫入器

    職責：
    - 接收文件列表並執行 insert_many
    - 回報寫入結果，不處理重試邏輯
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """
        Args:
            db: Motor async MongoDB 資料庫實例
        """
        self._db = db

    async def write_batch(
        self,
        collection_name: str,
        documents: list[dict[str, Any]],
    ) -> WriteResult:
        """
        批次寫入文件到指定 collection

        Args:
            collection_name: MongoDB collection 名稱
            documents: 要寫入的文件列表

        Returns:
            WriteResult 包含成功/失敗狀態與詳細資訊
        """
        if not documents:
            return WriteResult(success=True, inserted_count=0)

        try:
            result = await self._db[collection_name].insert_many(documents)
            inserted_count = len(result.inserted_ids)
            logger.debug(f"MongoWriter: 成功寫入 {inserted_count} 筆至 '{collection_name}'")
            return WriteResult(success=True, inserted_count=inserted_count)

        except Exception as e:
            error_msg = f"寫入 '{collection_name}' 失敗: {e}"
            logger.error(f"MongoWriter: {error_msg}")
            return WriteResult(success=False, error_message=error_msg)
