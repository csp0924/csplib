"""
MongoBatchUploader 模組

集合式批次上傳器：
- 所有資料按 collection 進入對應的 queue
- 定期或資料量達閾值時批次上傳 (insert_many)
- 支援重試機制與容量上限保護
"""

import asyncio
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from csp_lib.core import get_logger
from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.mongo.config import UploaderConfig
from csp_lib.mongo.queue import BatchQueue
from csp_lib.mongo.writer import MongoWriter, WriteResult

logger = get_logger(__name__)


class MongoBatchUploader:
    """
    MongoDB 批次上傳器

    組合 BatchQueue + MongoWriter，負責：
    - 管理多個 collection 的 queue
    - 排程定期 flush
    - 處理重試邏輯
    - threshold 即時喚醒：queue 達到 ``batch_size_threshold`` 時主動通知
      ``_flush_loop`` 立即 flush，避免等待整個 ``flush_interval`` 期間
      累積到 ``max_queue_size`` 造成資料被 ``popleft`` 丟棄

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
        config: UploaderConfig | None = None,
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
        # threshold 達到時立即喚醒 _flush_loop
        self._threshold_event = asyncio.Event()
        self._flush_task: asyncio.Task[None] | None = None

    @property
    def writer(self) -> MongoWriter:
        """
        取得底層 MongoWriter（唯讀）

        供 ``LocalBufferedUploader`` 等上層模組取得 ``write_batch`` 的
        細粒度介面（如 ``ordered=False`` / 重複鍵處理）。

        Returns:
            MongoWriter: 目前使用的 writer 實例
        """
        return self._writer

    def health(self) -> HealthReport:
        """
        回傳 uploader 當前健康狀態（實作 :class:`csp_lib.core.HealthCheckable`）。

        狀態判定規則：

        - ``UNHEALTHY``：``_flush_task`` 未啟動、已 done（含崩潰），或 ``_stop_event``
          已設置但仍有 queue 內含未上傳資料
        - ``DEGRADED``：running 中，但有任一 queue 使用率 >= 80%（接近 ``max_queue_size``
          容量會觸發 ``popleft`` 丟資料），或有 collection 正在重試（retry_count > 0）
        - ``HEALTHY``：running，所有 queue 使用率 < 80%，無 retry 中

        ``details`` 包含每個已註冊 collection 的 ``queue_size`` / ``max_size`` /
        ``usage_ratio`` 以及 ``retry_counts`` 字典，供 SystemController 聚合觀測。
        """
        running = self._flush_task is not None and not self._flush_task.done()
        stopped_with_pending = self._stop_event.is_set() and any(q.size_sync() > 0 for q in self._queues.values())

        queues_detail: dict[str, dict[str, Any]] = {}
        max_usage_ratio = 0.0
        for name, queue in self._queues.items():
            size = queue.size_sync()
            max_size = queue.max_size
            usage_ratio = size / max_size if max_size > 0 else 0.0
            queues_detail[name] = {"queue_size": size, "max_size": max_size, "usage_ratio": usage_ratio}
            if usage_ratio > max_usage_ratio:
                max_usage_ratio = usage_ratio

        active_retries = {name: count for name, count in self._retry_counts.items() if count > 0}

        if not running or stopped_with_pending:
            status = HealthStatus.UNHEALTHY
            if not running:
                message = "flush task not running" if self._flush_task is None else "flush task already done"
            else:
                message = "stopped with pending data in queues"
        elif max_usage_ratio >= 0.8 or active_retries:
            status = HealthStatus.DEGRADED
            reasons: list[str] = []
            if max_usage_ratio >= 0.8:
                reasons.append(f"queue usage {max_usage_ratio:.0%} >= 80%")
            if active_retries:
                reasons.append(f"retrying collections: {sorted(active_retries.keys())}")
            message = "; ".join(reasons)
        else:
            status = HealthStatus.HEALTHY
            message = f"{len(self._queues)} collection(s) running"

        return HealthReport(
            status=status,
            component="MongoBatchUploader",
            message=message,
            details={
                "running": running,
                "queues": queues_detail,
                "retry_counts": dict(self._retry_counts),
                "max_queue_usage_ratio": max_usage_ratio,
            },
        )

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

        若加入後該 queue 的大小 >= ``batch_size_threshold``，會設定
        ``_threshold_event`` 立即喚醒 ``_flush_loop``。

        Args:
            collection_name: MongoDB collection 名稱
            document: 要加入的文件
        """
        if collection_name not in self._queues:
            self.register_collection(collection_name)

        await self._queues[collection_name].enqueue(document)

        # 達到閾值 → 主動喚醒 _flush_loop
        if self._queues[collection_name].size_sync() >= self._config.batch_size_threshold:
            self._threshold_event.set()

    async def write_immediate(
        self,
        collection_name: str,
        document: dict[str, Any],
    ) -> WriteResult:
        """
        繞過 batch queue，直接將單一文件寫入 MongoDB

        用於 alarm history 等必須即時落庫的關鍵資料。此方法不進入
        任何 queue，也不會觸發 threshold/flush 機制，成功與否直接
        由 ``MongoWriter.write_batch`` 的結果決定。

        Args:
            collection_name: 目標 MongoDB collection 名稱
            document: 要寫入的單一文件

        Returns:
            WriteResult: ``csp_lib.mongo.WriteResult`` 寫入結果
        """
        return await self._writer.write_batch(collection_name, [document])

    def start(self) -> "MongoBatchUploader":
        """
        啟動定期 flush 任務

        Returns:
            self，支援 fluent interface
        """
        if self._flush_task is None or self._flush_task.done():
            self._stop_event.clear()
            self._threshold_event.clear()
            self._flush_task = asyncio.create_task(self._flush_loop())
            logger.info("MongoBatchUploader: 啟動批次上傳任務")
        return self

    async def stop(self) -> None:
        """停止 flush 任務，並確保所有資料都已上傳"""
        # _wait_for_trigger 已同時監聽 _stop_event；setting it alone 就足以喚醒 waiter
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

    async def _wait_for_trigger(self) -> None:
        """
        多事件等待：同時監聽 stop / threshold / timeout 三路訊號

        - ``_stop_event`` 被設定 → 立即返回（停止流程）
        - ``_threshold_event`` 被設定 → 立即返回（有 queue 達閾值）
        - ``flush_interval`` 到期 → 返回（定期 flush）

        停止時正確 cancel 未完成的 waiter task，避免 task leak。
        """
        stop_task = asyncio.create_task(self._stop_event.wait())
        threshold_task = asyncio.create_task(self._threshold_event.wait())
        try:
            await asyncio.wait(
                {stop_task, threshold_task},
                timeout=self._config.flush_interval,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (stop_task, threshold_task):
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass

    async def _flush_loop(self) -> None:
        """
        定期檢查並上傳所有 collection 的資料

        採用多事件等待（stop / threshold / timeout），threshold 達到
        時可立即 flush，不必等整個 ``flush_interval``。
        """
        while not self._stop_event.is_set():
            try:
                # 等待 stop / threshold / timeout 三路任一
                await self._wait_for_trigger()

                if self._stop_event.is_set():
                    # 結束迴圈前 flush 所有資料
                    await self.flush_all()
                    break

                # 被 threshold 喚醒或 timeout 到期 → flush 所有 queue
                await self.flush_all()

                # 清除 threshold 旗標等待下次達閾值
                self._threshold_event.clear()

            except asyncio.CancelledError:
                # 結束前 flush 所有資料
                await self.flush_all()
                break
            except Exception as e:
                logger.error(f"MongoBatchUploader: flush loop 錯誤: {e}")
                await asyncio.sleep(1)
