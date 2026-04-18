"""
MongoWriter 模組

負責將批次資料寫入 MongoDB，職責單一：執行寫入操作並回報結果。
"""

from dataclasses import dataclass
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from csp_lib.core import get_logger

logger = get_logger(__name__)


@dataclass
class WriteResult:
    """
    寫入結果

    Attributes:
        success: 是否成功（``ordered=False`` 情境下，僅有重複鍵錯誤仍視為 True）
        inserted_count: 成功插入的文件數量
        error_message: 錯誤訊息（若失敗）
        duplicate_key_count: 重複鍵錯誤數量（供 replay 判定用）
    """

    success: bool
    inserted_count: int = 0
    error_message: str | None = None
    duplicate_key_count: int = 0


class MongoWriter:
    """
    MongoDB 批次寫入器

    職責：
    - 接收文件列表並執行 insert_many
    - 回報寫入結果，不處理重試邏輯
    - 支援 ``ordered=False`` 模式以容忍重複鍵（idempotent replay 場景）
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """
        Args:
            db: Motor async MongoDB 資料庫實例
        """
        self._db = db

    @property
    def db(self) -> AsyncIOMotorDatabase:
        """底層 MongoDB database handle（唯讀）"""
        return self._db

    async def write_batch(
        self,
        collection_name: str,
        documents: list[dict[str, Any]],
        *,
        ordered: bool = True,
    ) -> WriteResult:
        """
        批次寫入文件到指定 collection

        Args:
            collection_name: MongoDB collection 名稱
            documents: 要寫入的文件列表
            ordered: 是否使用 ordered insert（預設 True 保持向後相容）。
                ``ordered=False`` 時會捕捉 ``BulkWriteError`` 並將重複鍵錯誤
                （code 11000）與其他錯誤分開計數。若所有錯誤都是重複鍵，
                ``success`` 仍回 True（供 idempotent replay 判定）。

        Returns:
            WriteResult 包含成功/失敗狀態、插入數量、重複鍵數量與詳細訊息
        """
        if not documents:
            return WriteResult(success=True, inserted_count=0)

        try:
            result = await self._db[collection_name].insert_many(documents, ordered=ordered)
            inserted_count = len(result.inserted_ids)
            logger.debug(f"MongoWriter: 成功寫入 {inserted_count} 筆至 '{collection_name}'")
            return WriteResult(success=True, inserted_count=inserted_count)

        except Exception as e:
            # ordered=False 時，捕捉 BulkWriteError 以分離重複鍵與其他錯誤
            if not ordered:
                bwe_result = self._handle_bulk_write_error(collection_name, e)
                if bwe_result is not None:
                    return bwe_result

            error_msg = f"寫入 '{collection_name}' 失敗: {e}"
            logger.error(f"MongoWriter: {error_msg}")
            return WriteResult(success=False, error_message=error_msg)

    @staticmethod
    def _handle_bulk_write_error(collection_name: str, exc: Exception) -> WriteResult | None:
        """
        處理 ``BulkWriteError``，分離重複鍵與其他錯誤

        Args:
            collection_name: collection 名稱（僅用於 log）
            exc: 捕捉到的例外

        Returns:
            若為 ``BulkWriteError`` 則回傳對應 ``WriteResult``；
            其他例外回傳 None 交由呼叫端處理。
        """
        # 延遲 import，避免使用者未安裝 pymongo optional extras 時 import 失敗
        try:
            from pymongo.errors import BulkWriteError
        except ImportError:  # pragma: no cover — pymongo 是 motor 的硬依賴
            return None

        if not isinstance(exc, BulkWriteError):
            return None

        details = exc.details or {}
        write_errors = details.get("writeErrors", []) or []
        duplicates = sum(1 for e in write_errors if isinstance(e, dict) and e.get("code") == 11000)
        non_dups = len(write_errors) - duplicates
        inserted = int(details.get("nInserted", 0) or 0)

        if non_dups == 0:
            logger.debug(
                f"MongoWriter: '{collection_name}' 部分重複鍵但無其他錯誤 "
                f"(inserted={inserted}, duplicates={duplicates})"
            )
            return WriteResult(
                success=True,
                inserted_count=inserted,
                duplicate_key_count=duplicates,
            )

        error_msg = f"{non_dups} non-duplicate errors"
        logger.error(
            f"MongoWriter: '{collection_name}' 寫入失敗 "
            f"(inserted={inserted}, duplicates={duplicates}, non_dup_errors={non_dups})"
        )
        return WriteResult(
            success=False,
            inserted_count=inserted,
            duplicate_key_count=duplicates,
            error_message=error_msg,
        )
