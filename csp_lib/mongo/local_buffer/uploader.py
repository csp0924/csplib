"""
LocalBufferedUploader 與 ``LocalBufferConfig``

提供「本地 buffer + 背景 replay 到 MongoDB」的容錯上傳策略：

- ``enqueue`` / ``write_immediate`` 先落地 ``LocalBufferStore``，再由
  背景任務重送至下游 ``MongoBatchUploader``
- 下游 MongoDB 斷線、錯誤或 flush 失敗時，資料不會遺失
- 透過 ``_idempotency_key`` + MongoDB 唯一稀疏索引實現冪等 replay
- 支援 TTL 清理已同步資料，避免本地 DB 無限增長
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from csp_lib.core import get_logger
from csp_lib.core.lifecycle import AsyncLifecycleMixin
from csp_lib.mongo.local_buffer.store import LocalBufferStore

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

    from csp_lib.mongo.uploader import MongoBatchUploader
    from csp_lib.mongo.writer import WriteResult

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LocalBufferConfig:
    """
    LocalBufferedUploader 設定

    具體儲存路徑/連線由 ``LocalBufferStore`` 實作自行保存；此設定
    只包含 replay / cleanup 行為參數。

    Attributes:
        replay_interval: 背景 replay 間隔（秒）
        replay_batch_size: 單次 replay 從 store 取出的最大筆數
        cleanup_interval: 已同步資料清理間隔（秒）
        retention_seconds: 已同步資料保留秒數（超過則刪除）
        max_retry_count: 單筆資料的最大 replay 重試次數（超過則記 log
            但不丟棄）
    """

    replay_interval: float = 5.0
    replay_batch_size: int = 500
    cleanup_interval: float = 3600.0
    retention_seconds: float = 86400.0 * 7  # 7 天
    max_retry_count: int = 100

    def __post_init__(self) -> None:
        if self.replay_interval <= 0:
            raise ValueError(f"replay_interval 必須為正數，收到: {self.replay_interval}")
        if self.replay_batch_size <= 0:
            raise ValueError(f"replay_batch_size 必須為正整數，收到: {self.replay_batch_size}")
        if self.cleanup_interval <= 0:
            raise ValueError(f"cleanup_interval 必須為正數，收到: {self.cleanup_interval}")
        if self.retention_seconds < 0:
            raise ValueError(f"retention_seconds 不可為負，收到: {self.retention_seconds}")
        if self.max_retry_count < 0:
            raise ValueError(f"max_retry_count 不可為負，收到: {self.max_retry_count}")


class LocalBufferedUploader(AsyncLifecycleMixin):
    """
    本地緩衝上傳器

    結構：
        上層（DataUploadManager / AlarmPersistenceManager）
              ↓ enqueue / write_immediate
        LocalBufferedUploader （此類）
              ↓ append → LocalBufferStore （例如 SqliteBufferStore）
              ↓ 背景 replay
        下游 MongoBatchUploader
              ↓ insert_many(ordered=False)
        MongoDB

    特性：
        - 所有寫入先落地 ``LocalBufferStore``，確保下游故障時資料不遺失
        - Replay 時採 ``ordered=False`` + 唯一稀疏索引實現冪等
        - 啟動時自動 refresh 計數器，支援重啟後恢復未送出資料

    Example:
        ```python
        from csp_lib.mongo.local_buffer import (
            LocalBufferConfig,
            LocalBufferedUploader,
            SqliteBufferStore,
        )

        store = SqliteBufferStore("./buffer.db")
        cfg = LocalBufferConfig(replay_interval=5.0)
        local = LocalBufferedUploader(downstream=mongo_uploader, store=store, config=cfg)

        async with local:
            await local.enqueue("telemetry", {"ts": 123, "val": 42})
        ```
    """

    def __init__(
        self,
        downstream: MongoBatchUploader,
        store: LocalBufferStore,
        config: LocalBufferConfig | None = None,
    ) -> None:
        """
        Args:
            downstream: 下游 ``MongoBatchUploader``，供 replay 使用
            store: 本地緩衝儲存後端（實作 ``LocalBufferStore`` Protocol）
            config: 本地 buffer 設定，未提供則使用預設值
        """
        self._downstream = downstream
        self._store = store
        self._config = config or LocalBufferConfig()
        self._stop_event = asyncio.Event()
        self._replay_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        # 已知 collection set，僅用於 ensure_indexes 等批次操作
        self._collections: set[str] = set()

    # ================ Lifecycle ================

    async def _on_start(self) -> None:
        """啟動：開啟 store、log 恢復狀態、啟動 replay / cleanup 背景任務"""
        logger.info("LocalBufferedUploader: 啟動")
        self._stop_event.clear()

        await self._store.open()

        pending = await self._store.count_pending()
        cursor = await self._store.max_synced_sequence()
        logger.info(f"LocalBufferedUploader: 恢復狀態 (pending={pending}, synced_cursor={cursor})")

        self._replay_task = asyncio.create_task(self._replay_loop(), name="local-buffer-replay")
        self._cleanup_task = asyncio.create_task(self._cleanup_loop(), name="local-buffer-cleanup")

    async def _on_stop(self) -> None:
        """停止：set stop_event → gather 背景 task → 最後 drain 一次 → 關閉 store"""
        logger.info("LocalBufferedUploader: 停止中")
        self._stop_event.set()

        tasks = [t for t in (self._replay_task, self._cleanup_task) if t is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # 最後嘗試 drain 一次（盡力而為，失敗不 raise）
        try:
            await self._replay_once()
        except Exception:
            logger.opt(exception=True).warning("LocalBufferedUploader: 最後 drain 失敗")

        try:
            await self._store.close()
        except Exception:
            logger.opt(exception=True).warning("LocalBufferedUploader: store 關閉失敗")

        logger.info("LocalBufferedUploader: 已停止")

    # ================ Public API ================

    def register_collection(self, collection_name: str) -> None:
        """
        註冊 collection（同步轉發給下游）

        Args:
            collection_name: MongoDB collection 名稱
        """
        self._collections.add(collection_name)
        self._downstream.register_collection(collection_name)

    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None:
        """
        將文件寫入本地 buffer（等待背景 replay）

        此方法不直接呼叫下游，僅確保資料落地 store，故不會因
        MongoDB 斷線而遺失。

        Args:
            collection_name: 目標 collection 名稱
            document: 要上傳的文件
        """
        self._collections.add(collection_name)
        key = self._compute_idempotency_key(collection_name, document)
        doc_json = self._serialize_document(document)

        await self._store.append(collection_name, doc_json, key, synced=False)

    async def write_immediate(
        self,
        collection_name: str,
        document: dict[str, Any],
    ) -> WriteResult:
        """
        關鍵路徑寫入：先落地 buffer，成功後立即同步寫入下游 MongoDB

        若下游寫入成功則立刻標記 synced=1；失敗則留在 buffer 等待 replay。
        無論下游結果如何，資料都已落地本地，不會遺失。

        Args:
            collection_name: 目標 collection 名稱
            document: 要寫入的單一文件

        Returns:
            WriteResult: 下游 ``MongoBatchUploader.write_immediate`` 的結果；
                若寫入本地 store 即失敗則回傳 success=False
        """
        # 延遲 import，僅用於例外分支的 WriteResult 建構
        from csp_lib.mongo.writer import WriteResult as _WR

        self._collections.add(collection_name)
        key = self._compute_idempotency_key(collection_name, document)
        doc_json = self._serialize_document(document)

        # 步驟 1：先落地 buffer
        row_id = await self._store.append(collection_name, doc_json, key, synced=False)

        # 步驟 2：附加 _idempotency_key 供 MongoDB 端唯一索引去重
        payload = dict(document)
        payload.setdefault("_idempotency_key", key)

        # 步驟 3：嘗試立即同步至下游；下游拋錯時仍保證資料已落地
        try:
            result = await self._downstream.write_immediate(collection_name, payload)
        except Exception as e:
            logger.opt(exception=True).warning(
                f"LocalBufferedUploader: '{collection_name}' write_immediate 下游失敗，資料保留於本地"
            )
            return _WR(success=False, inserted_count=0, error_message=str(e))

        if row_id is not None and (result.success or (result.inserted_count + result.duplicate_key_count) >= 1):
            await self._store.mark_synced([row_id])

        return result

    async def ensure_indexes(self, db: AsyncIOMotorDatabase | None = None) -> None:
        """
        對所有已註冊 collection 建立 ``_idempotency_key`` 唯一稀疏索引

        應於應用程式啟動時（下游 MongoDB 已連線後）呼叫一次。多個
        collection 的索引會並行建立。

        Args:
            db: 選擇性覆寫的 MongoDB database handle。若未提供則從
                ``downstream.writer.db`` 取得。
        """
        target_db = db if db is not None else getattr(self._downstream.writer, "db", None)
        if target_db is None:
            logger.warning("LocalBufferedUploader: 無法取得 MongoDB db，跳過 ensure_indexes")
            return

        async def _create_one(coll: str) -> None:
            try:
                await target_db[coll].create_index(
                    [("_idempotency_key", 1)],
                    unique=True,
                    sparse=True,
                    name="idempotency_key_unique",
                )
            except Exception:
                logger.opt(exception=True).warning(f"LocalBufferedUploader: 建立 '{coll}' 的 idempotency 索引失敗")

        collections = list(self._collections)
        if collections:
            await asyncio.gather(*(_create_one(c) for c in collections))

    async def health_check(self) -> bool:
        """代理 ``store.health_check()``"""
        return await self._store.health_check()

    async def get_pending_count(self) -> int:
        """代理 ``store.count_pending()``"""
        return await self._store.count_pending()

    async def get_sync_cursor(self) -> int | str:
        """
        代理 ``store.max_synced_sequence()``

        Returns:
            最新已同步 row 的 id。SQLite backend 回傳 ``int``；
            MongoDB backend 回傳 ``str``（ObjectId）。無資料時回 ``0``。
        """
        return await self._store.max_synced_sequence()

    # ================ Background loops ================

    async def _periodic(
        self,
        interval: float,
        once: Callable[[], Awaitable[None]],
        *,
        error_msg: str,
        log_level: str = "error",
    ) -> None:
        """
        共用背景 loop：每 ``interval`` 秒呼叫一次 ``once``，收到 stop_event 即結束

        Args:
            interval: 兩次呼叫間的等待秒數
            once: 單次工作 coroutine 工廠
            error_msg: 未預期錯誤的 log 訊息
            log_level: "error" 或 "warning"，對應 logger 層級
        """
        opt_logger = logger.opt(exception=True)
        emit = opt_logger.error if log_level == "error" else opt_logger.warning
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass

            try:
                await once()
            except asyncio.CancelledError:
                break
            except Exception:
                emit(error_msg)

    async def _replay_loop(self) -> None:
        """背景 replay 任務：定期將未同步資料送至下游"""
        await self._periodic(
            self._config.replay_interval,
            self._replay_once,
            error_msg="LocalBufferedUploader: replay 發生未預期錯誤",
            log_level="error",
        )

    async def _cleanup_loop(self) -> None:
        """背景清理任務：定期刪除已同步且超過 retention 的資料"""
        await self._periodic(
            self._config.cleanup_interval,
            self._cleanup_once,
            error_msg="LocalBufferedUploader: cleanup 發生錯誤",
            log_level="warning",
        )

    # ================ Internal helpers ================

    async def _replay_once(self) -> None:
        """
        執行單次 replay：依 collection 分組並行將未同步資料送至下游

        成功判定：
            - ``result.success`` 為 True，或
            - ``inserted_count + duplicate_key_count >= len(docs)``
              （代表所有文件要嘛寫入成功要嘛已是重複鍵 → idempotent）

        滿足任一條件則標記整批為 synced。
        """
        rows = await self._store.fetch_pending(self._config.replay_batch_size)
        if not rows:
            return

        # 依 collection 分組
        rows_by_coll: dict[str, list[tuple[int | str, str, str]]] = {}
        for r in rows:
            rows_by_coll.setdefault(r.collection, []).append((r.row_id, r.doc_json, r.idempotency_key))

        # 並行對多個 collection 執行 replay；每個 collection 獨立處理失敗
        await asyncio.gather(
            *(self._replay_collection(coll, group) for coll, group in rows_by_coll.items() if group),
            return_exceptions=True,
        )

    async def _replay_collection(
        self,
        coll: str,
        group: list[tuple[int | str, str, str]],
    ) -> None:
        """Replay 單一 collection 的一組 row（供 ``_replay_once`` 並行呼叫）"""
        ids: list[int | str] = [row_id for row_id, _, _ in group]
        docs: list[dict[str, Any]] = []
        for _, doc_json, key in group:
            try:
                doc = json.loads(doc_json)
            except ValueError:
                logger.warning(f"LocalBufferedUploader: 解析 doc_json 失敗，跳過 id 範圍 {ids}")
                continue
            if isinstance(doc, dict):
                doc.setdefault("_idempotency_key", key)
                docs.append(doc)

        if not docs:
            return

        try:
            result = await self._downstream.writer.write_batch(coll, docs, ordered=False)
        except Exception:
            logger.opt(exception=True).warning(f"LocalBufferedUploader: '{coll}' replay 失敗，保留於本地等待下次")
            await self._store.bump_retry(ids)
            return

        success_total = result.inserted_count + result.duplicate_key_count
        if result.success or success_total >= len(docs):
            await self._store.mark_synced(ids)
            logger.debug(
                f"LocalBufferedUploader: '{coll}' 同步 {len(ids)} 筆 "
                f"(inserted={result.inserted_count}, duplicates={result.duplicate_key_count})"
            )
        else:
            await self._store.bump_retry(ids)
            logger.warning(
                f"LocalBufferedUploader: '{coll}' 部分失敗 "
                f"(inserted={result.inserted_count}, non_dup_errors，"
                f"msg={result.error_message}) 保留等待重試"
            )

    async def _cleanup_once(self) -> None:
        """刪除超過 retention 的已同步資料"""
        cutoff = datetime.now(UTC).timestamp() - self._config.retention_seconds
        deleted = await self._store.delete_synced_before(cutoff)
        if deleted:
            logger.debug(f"LocalBufferedUploader: cleanup 刪除 {deleted} 筆過期已同步資料")

    @staticmethod
    def _serialize_document(document: dict[str, Any]) -> str:
        """將 document 序列化為 JSON 字串（使用 default=str 容錯）"""
        return json.dumps(document, default=str, ensure_ascii=False)

    @staticmethod
    def _compute_idempotency_key(collection_name: str, document: dict[str, Any]) -> str:
        """
        產生 idempotency_key：優先使用文件既有的 ``_idempotency_key``，
        否則以 collection + uuid4 產生一次性唯一 key

        uuid4 已提供 122-bit 亂數，不需對 document 內容額外 hash 來
        避免「內容相同 → 被下游唯一索引誤判為重複」的情況。

        Args:
            collection_name: 目標 collection 名稱
            document: 文件內容

        Returns:
            唯一 key 字串
        """
        explicit = document.get("_idempotency_key") if isinstance(document, dict) else None
        if isinstance(explicit, str) and explicit:
            return explicit
        return f"{collection_name}:{uuid.uuid4().hex}"


__all__ = [
    "LocalBufferConfig",
    "LocalBufferedUploader",
]
