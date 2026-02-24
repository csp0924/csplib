"""
MongoBatchUploader 模組

集合式批次上傳器：
- 所有資料按 collection 進入對應的 queue
- 定期或資料量達閾值時批次上傳 (insert_many)
- 支援重試機制與容量上限保護
"""

import asyncio
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from csp_lib.core import get_logger
from csp_lib.mongo.config import UploaderConfig
from csp_lib.mongo.queue import BatchQueue
from csp_lib.mongo.writer import MongoWriter

logger = get_logger(__name__)


class MongoBatchUploader:
    """
    MongoDB 批次上傳器

    組合 BatchQueue + MongoWriter，負責：
    - 管理多個 collection 的 queue
    - 排程定期 flush
    - 處理重試邏輯

    Example:
        ```python
        from motor.motor_asyncio import AsyncIOMotorClient
        from csp_lib.mongo import MongoBatchUploader, UploaderConfig

        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client["my_database"]

        uploader = MongoBatchUploader(db)
        uploader.start()

        await uploader.enqueue("my_collection", {"key": "value"})

        # 關閉時
        await uploader.stop()
        ```
    """

    def __init__(
        self,
        mongo_db: AsyncIOMotorDatabase,
        config: Optional[UploaderConfig] = None,
    ) -> None:
        """
        Args:
            mongo_db: Motor async MongoDB 資料庫實例
            config: 上傳器設定，若未提供則使用預設值
        """
        self._config = config or UploaderConfig()
        self._writer = MongoWriter(mongo_db)
        self._queues: dict[str, BatchQueue] = {}
        self._retry_counts: dict[str, int] = {}  # collection_name -> retry count
        self._stop_event = asyncio.Event()
        self._flush_task: Optional[asyncio.Task[None]] = None

    def register_collection(self, collection_name: str) -> None:
        """
        預先註冊一個 collection 的 queue

        Args:
            collection_name: MongoDB collection 名稱
        """
        if collection_name not in self._queues:
            self._queues[collection_name] = BatchQueue(
                collection_name,
                max_size=self._config.max_queue_size,
            )
            self._retry_counts[collection_name] = 0
            logger.debug(f"MongoBatchUploader: 註冊 collection '{collection_name}'")

    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None:
        """
        將資料加入對應 collection 的 queue

        Args:
            collection_name: MongoDB collection 名稱
            document: 要加入的文件
        """
        if collection_name not in self._queues:
            self.register_collection(collection_name)

        await self._queues[collection_name].enqueue(document)

    def start(self) -> "MongoBatchUploader":
        """
        啟動定期 flush 任務

        Returns:
            self，支援 fluent interface
        """
        if self._flush_task is None or self._flush_task.done():
            self._stop_event.clear()
            self._flush_task = asyncio.create_task(self._flush_loop())
            logger.info("MongoBatchUploader: 啟動批次上傳任務")
        return self

    async def stop(self) -> None:
        """停止 flush 任務，並確保所有資料都已上傳"""
        self._stop_event.set()
        if self._flush_task:
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            logger.info("MongoBatchUploader: 批次上傳任務已停止")

    async def flush_all(self) -> None:
        """強制將所有 queue 中的資料上傳"""
        for collection_name in list(self._queues.keys()):
            await self._flush_collection(collection_name)

    async def _flush_collection(self, collection_name: str) -> None:
        """將指定 collection 的 queue 資料批次上傳"""
        if collection_name not in self._queues:
            return

        queue = self._queues[collection_name]
        documents = await queue.drain()

        if not documents:
            return

        result = await self._writer.write_batch(collection_name, documents)

        if result.success:
            self._retry_counts[collection_name] = 0
        else:
            await self._handle_write_failure(collection_name, documents)

    async def _handle_write_failure(
        self,
        collection_name: str,
        documents: list[dict[str, Any]],
    ) -> None:
        """處理寫入失敗：重試或丟棄"""
        self._retry_counts[collection_name] += 1
        retry_count = self._retry_counts[collection_name]

        if retry_count <= self._config.max_retry_count:
            logger.warning(
                f"MongoBatchUploader: '{collection_name}' 寫入失敗，重試 {retry_count}/{self._config.max_retry_count}"
            )
            await self._queues[collection_name].restore(documents)
        else:
            logger.error(
                f"MongoBatchUploader: '{collection_name}' 超過最大重試次數 "
                f"({self._config.max_retry_count})，丟棄 {len(documents)} 筆資料"
            )
            self._retry_counts[collection_name] = 0

    async def _flush_loop(self) -> None:
        """定期檢查並上傳所有 collection 的資料"""
        while not self._stop_event.is_set():
            try:
                # 檢查達到閾值的 collection 並立即上傳
                for name, queue in list(self._queues.items()):
                    if queue.size_sync() >= self._config.batch_size_threshold:
                        await self._flush_collection(name)

                # 等待下一次檢查或收到停止信號
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._config.flush_interval,
                    )
                    # stop_event 被設定，結束迴圈前 flush 所有資料
                    await self.flush_all()
                    break
                except asyncio.TimeoutError:
                    # 定期 flush 所有 queue（無論是否達閾值）
                    await self.flush_all()

            except asyncio.CancelledError:
                # 結束前 flush 所有資料
                await self.flush_all()
                break
            except Exception as e:
                logger.error(f"MongoBatchUploader: flush loop 錯誤: {e}")
                await asyncio.sleep(1)
