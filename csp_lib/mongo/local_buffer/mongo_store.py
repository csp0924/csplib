"""
MongoDB backend for ``LocalBufferStore``

使用本地 mongod（或任何 motor 可連線的 MongoDB 實例）做為
``LocalBufferedUploader`` 的緩衝儲存。概念上對應使用者心智模型：

    本地 mongod（buffer）→ 遠端 mongod（downstream）

Collection schema（預設 ``csp_local_buffer.pending_documents``）：

    {
        "_id":              ObjectId,   # 天然單調遞增，作為 row_id
        "collection":       str,        # 目標下游 MongoDB collection
        "doc_json":         str,        # 序列化後的文件 JSON
        "idempotency_key":  str,        # 唯一鍵（用於去重）
        "enqueued_at":      datetime,   # UTC，入列時間
        "synced":           bool,       # 同步狀態
        "synced_at":        datetime?,  # 同步時間
        "retry_count":      int,        # replay 累計重試次數
    }

Indexes（``open()`` 時自動 ensure）：
    - ``{idempotency_key: 1}``         unique（去重）
    - ``{synced: 1, _id: 1}``          compound（加速 fetch_pending）
    - ``{synced: 1, synced_at: 1}``    compound（加速 cleanup）

設計約束：
    - Store **不擁有** motor client 的 lifecycle；由外部管理連線
    - ``open()`` 僅建立 index（冪等），``close()`` 為 no-op
    - row_id 以 ObjectId 字串表示（符合 Protocol ``int | str`` 型別）
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

try:
    from bson import ObjectId
    from bson.errors import InvalidId
    from pymongo.errors import DuplicateKeyError
except ImportError as e:  # pragma: no cover — motor/pymongo 由 [mongo] extra 保證
    raise ImportError(
        "MongoBufferStore requires 'motor' / 'pymongo'. Install with: uv pip install 'csp0924_lib[mongo]'"
    ) from e

from csp_lib.core import get_logger
from csp_lib.mongo.local_buffer.store import BufferedRow

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

logger = get_logger(__name__)


class MongoBufferStore:
    """
    MongoDB (motor) 版本的 ``LocalBufferStore`` 實作

    以本地 mongod 作為 buffer，搭配 ``LocalBufferedUploader`` 將資料
    replay 至遠端 MongoDB。適用於：
        - 已在部署環境跑 mongod，不想再引入 SQLite
        - 本地與遠端統一技術棧，運維工具（mongodump/mongostat）可共用
        - 需要 buffer 支援較大資料量或多進程共享的場景

    ctor 由使用者提供 motor client，Store 只管理一個 database 的一個
    collection。client lifecycle 由外部持有（通常是 application 主程序）。

    Example:
        ```python
        from motor.motor_asyncio import AsyncIOMotorClient
        from csp_lib.mongo.local_buffer import MongoBufferStore

        local_client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
        store = MongoBufferStore(local_client)
        await store.open()
        try:
            row_id = await store.append("telemetry", '{"v": 1}', "key-1")
            rows = await store.fetch_pending(100)
        finally:
            await store.close()
            local_client.close()
        ```
    """

    def __init__(
        self,
        client: AsyncIOMotorClient,
        *,
        database: str = "csp_local_buffer",
        collection: str = "pending_documents",
    ) -> None:
        """
        Args:
            client: motor AsyncIOMotorClient（指向本地 mongod）
            database: Buffer 使用的 database 名稱
            collection: Buffer 使用的 collection 名稱
        """
        if not database:
            raise ValueError("database 不可為空")
        if not collection:
            raise ValueError("collection 不可為空")

        self._client = client
        self._database_name = database
        self._collection_name = collection
        self._col: AsyncIOMotorCollection = client[database][collection]
        self._opened: bool = False

    # ================ Lifecycle ================

    async def open(self) -> None:
        """
        建立必要 index（冪等）

        重複呼叫為 no-op。Index 已存在且 key/name/options 一致時 MongoDB
        會直接略過；真正的連線/權限錯誤應直接 raise 讓上層啟動中斷，
        因此本方法不吞例外。
        """
        if self._opened:
            return

        # 多個 create_index 可並行；MongoDB 對同名同結構 index 的重複建立為 no-op
        await asyncio.gather(
            self._col.create_index(
                [("idempotency_key", 1)],
                unique=True,
                name="idempotency_key_unique",
            ),
            self._col.create_index(
                [("synced", 1), ("_id", 1)],
                name="synced_id_compound",
            ),
            self._col.create_index(
                [("synced", 1), ("synced_at", 1)],
                name="synced_synced_at_compound",
            ),
        )

        self._opened = True
        logger.debug(f"MongoBufferStore: 已開啟（db={self._database_name}, coll={self._collection_name}）")

    async def close(self) -> None:
        """
        no-op：motor client 的 lifecycle 由外部管理，Store 僅釋放狀態旗標
        """
        self._opened = False

    # ================ CRUD ================

    async def append(
        self,
        collection: str,
        doc_json: str,
        idempotency_key: str,
        *,
        synced: bool = False,
    ) -> int | str | None:
        """
        新增一筆資料

        Args:
            collection: 目標下游 MongoDB collection 名稱
            doc_json: 序列化後的文件 JSON 字串
            idempotency_key: 唯一鍵；重複則回 ``None``
            synced: 入列時即標記為已同步

        Returns:
            新增 row 的 ObjectId 字串；重複鍵衝突則回 ``None``
        """
        now = datetime.now(UTC)
        doc: dict[str, Any] = {
            "collection": collection,
            "doc_json": doc_json,
            "idempotency_key": idempotency_key,
            "enqueued_at": now,
            "synced": synced,
            "synced_at": now if synced else None,
            "retry_count": 0,
        }
        try:
            result = await self._col.insert_one(doc)
            return str(result.inserted_id)
        except DuplicateKeyError:
            logger.debug(f"MongoBufferStore: idempotency_key 重複（{idempotency_key}），跳過插入")
            return None

    async def fetch_pending(self, limit: int) -> list[BufferedRow]:
        """
        依 ``_id`` 升冪取出 ``synced=False`` 的資料
        """
        if limit <= 0:
            return []

        rows: list[BufferedRow] = []
        cursor = self._col.find({"synced": False}).sort("_id", 1).limit(limit)
        async for doc in cursor:
            enqueued_at = doc.get("enqueued_at")
            if isinstance(enqueued_at, datetime):
                enqueued_ts = enqueued_at.timestamp()
            else:
                try:
                    enqueued_ts = float(enqueued_at)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    enqueued_ts = 0.0
            rows.append(
                BufferedRow(
                    row_id=str(doc["_id"]),
                    collection=str(doc.get("collection", "")),
                    doc_json=str(doc.get("doc_json", "")),
                    idempotency_key=str(doc.get("idempotency_key", "")),
                    enqueued_at=enqueued_ts,
                    retry_count=int(doc.get("retry_count", 0)),
                )
            )
        return rows

    async def mark_synced(self, row_ids: Sequence[int | str]) -> None:
        """
        將指定 row 標記為 ``synced=True`` 並記錄 ``synced_at``

        row_ids 可為 ObjectId 字串（str）或已存在的 int id；無法解析
        的 id 會被略過（不拋錯）。
        """
        if not row_ids:
            return
        object_ids = self._coerce_object_ids(row_ids)
        if not object_ids:
            return
        await self._col.update_many(
            {"_id": {"$in": object_ids}, "synced": False},
            {"$set": {"synced": True, "synced_at": datetime.now(UTC)}},
        )

    async def bump_retry(self, row_ids: Sequence[int | str]) -> None:
        """將指定 row 的 ``retry_count`` +1"""
        if not row_ids:
            return
        object_ids = self._coerce_object_ids(row_ids)
        if not object_ids:
            return
        await self._col.update_many(
            {"_id": {"$in": object_ids}},
            {"$inc": {"retry_count": 1}},
        )

    async def delete_synced_before(self, cutoff_ts: float) -> int:
        """
        刪除 ``synced=True`` 且 ``synced_at < cutoff_ts`` 的 row

        Returns:
            實際刪除的筆數
        """
        cutoff_dt = datetime.fromtimestamp(cutoff_ts, UTC)
        result = await self._col.delete_many(
            {
                "synced": True,
                "synced_at": {"$lt": cutoff_dt},
            }
        )
        return int(result.deleted_count or 0)

    async def count_pending(self) -> int:
        """回傳 ``synced=False`` 的筆數"""
        count = await self._col.count_documents({"synced": False})
        return int(count)

    async def max_synced_sequence(self) -> int | str:
        """
        回傳最新的已同步 row 的 ObjectId 字串

        若無任何已同步資料則回 ``0``（符合 Protocol 慣例）。
        """
        doc = await self._col.find_one({"synced": True}, sort=[("_id", -1)])
        if doc is None:
            return 0
        return str(doc["_id"])

    async def health_check(self) -> bool:
        """
        以 ``admin.command('ping')`` 檢查 motor client 是否可用

        Returns:
            ``True`` 表示健康；連線失敗或未開啟則回 ``False``
        """
        if not self._opened:
            return False
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False

    # ================ Internal helpers ================

    @staticmethod
    def _coerce_object_ids(row_ids: Sequence[int | str]) -> list[ObjectId]:
        """
        將外部傳入的 row_ids 轉為 ``ObjectId`` list

        非法或非字串型別會被略過（不拋錯，僅 debug log）。
        """
        object_ids: list[ObjectId] = []
        for rid in row_ids:
            if isinstance(rid, ObjectId):
                object_ids.append(rid)
                continue
            if not isinstance(rid, str):
                logger.debug(f"MongoBufferStore: 忽略非字串 row_id={rid!r}")
                continue
            try:
                object_ids.append(ObjectId(rid))
            except (InvalidId, TypeError):
                logger.debug(f"MongoBufferStore: 忽略無效 ObjectId 字串={rid!r}")
        return object_ids


__all__ = [
    "MongoBufferStore",
]
