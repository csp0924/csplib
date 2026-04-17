"""
SQLite backend for ``LocalBufferStore``

使用 ``aiosqlite`` 以 WAL 模式提供 crash-safe 的本地緩衝。此為
``LocalBufferedUploader`` 的預設 backend 實作。

資料表 ``pending_documents`` 欄位：
    - id                INTEGER PRIMARY KEY AUTOINCREMENT
    - collection_name   TEXT    NOT NULL
    - document_json     TEXT    NOT NULL
    - idempotency_key   TEXT    NOT NULL (UNIQUE)
    - enqueued_at       REAL    NOT NULL
    - synced            INTEGER NOT NULL DEFAULT 0
    - synced_at         REAL    NULL
    - retry_count       INTEGER NOT NULL DEFAULT 0

索引：
    - ``idx_pending_synced``     (synced, collection_name, id)
    - ``idx_pending_synced_at``  (synced, synced_at)
    - ``idx_idempotency_key``    (idempotency_key) UNIQUE
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

try:
    import aiosqlite
except ImportError as e:  # pragma: no cover — 由使用者環境決定
    raise ImportError(
        "SqliteBufferStore requires 'aiosqlite' package. Install with: uv pip install 'csp0924_lib[local-buffer]'"
    ) from e

from csp_lib.core import get_logger
from csp_lib.mongo.local_buffer.store import BufferedRow

logger = get_logger(__name__)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pending_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_name TEXT NOT NULL,
    document_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    enqueued_at REAL NOT NULL,
    synced INTEGER NOT NULL DEFAULT 0,
    synced_at REAL,
    retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_pending_synced
    ON pending_documents (synced, collection_name, id);

CREATE INDEX IF NOT EXISTS idx_pending_synced_at
    ON pending_documents (synced, synced_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_idempotency_key
    ON pending_documents (idempotency_key);
"""


class SqliteBufferStore:
    """
    SQLite (aiosqlite) 版本的 ``LocalBufferStore`` 實作

    使用 WAL journal + NORMAL synchronous 取得較佳寫入效能，並在
    ``idempotency_key`` 上加唯一索引以支援重複入列的冪等判定。

    設計約束：
        - 所有 CRUD 共用一把 ``asyncio.Lock``，避免多 coroutine 同時
          commit 引起鎖衝突
        - ``open`` / ``close`` 皆冪等；重複呼叫不會重建 schema 或
          重複關閉
        - 擁有者為 ``LocalBufferedUploader``，其 lifecycle 會驅動
          ``open`` / ``close``

    Example:
        ```python
        store = SqliteBufferStore("./buffer.db")
        await store.open()
        try:
            await store.append("telemetry", '{"v": 1}', "key-1")
            rows = await store.fetch_pending(100)
        finally:
            await store.close()
        ```
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        wal_mode: bool = True,
        synchronous: Literal["OFF", "NORMAL", "FULL"] = "NORMAL",
    ) -> None:
        """
        Args:
            db_path: SQLite 檔路徑（建議放在 persistent volume）
            wal_mode: 是否使用 WAL journal 模式（預設 True）
            synchronous: SQLite ``synchronous`` PRAGMA 值
        """
        if not str(db_path):
            raise ValueError("db_path 不可為空")
        self._db_path = str(db_path)
        self._wal_mode = wal_mode
        self._synchronous = synchronous
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    # ================ Lifecycle ================

    async def open(self) -> None:
        """
        開啟 SQLite 連線、設置 PRAGMA 並建立 schema

        重複呼叫為 no-op（已開啟的連線不會被重建）。
        """
        if self._conn is not None:
            return

        self._conn = await aiosqlite.connect(self._db_path)
        if self._wal_mode:
            await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute(f"PRAGMA synchronous={self._synchronous};")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.executescript(_SCHEMA_SQL)
        await self._conn.commit()
        logger.debug(f"SqliteBufferStore: 已開啟（db_path={self._db_path}）")

    async def close(self) -> None:
        """
        關閉 SQLite 連線

        重複呼叫或尚未開啟時為 no-op，不拋錯。
        """
        if self._conn is None:
            return
        try:
            await self._conn.close()
        except Exception:
            logger.opt(exception=True).warning("SqliteBufferStore: 關閉失敗")
        finally:
            self._conn = None

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

        若 ``idempotency_key`` 重複則跳過並回 ``None``。
        SQLite backend 實際回傳 ``int``（AUTOINCREMENT id），回傳型別
        宣告為 ``int | str | None`` 以對齊 ``LocalBufferStore`` Protocol。
        """
        if self._conn is None:
            logger.warning("SqliteBufferStore: 尚未開啟，append 跳過")
            return None

        now = datetime.now(UTC).timestamp()

        async with self._lock:
            try:
                cursor = await self._conn.execute(
                    "INSERT INTO pending_documents "
                    "(collection_name, document_json, idempotency_key, enqueued_at, synced, synced_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        collection,
                        doc_json,
                        idempotency_key,
                        now,
                        1 if synced else 0,
                        now if synced else None,
                    ),
                )
                await self._conn.commit()
                return int(cursor.lastrowid) if cursor.lastrowid is not None else None
            except aiosqlite.IntegrityError:
                # idempotency_key 重複，視為已存在
                logger.debug(f"SqliteBufferStore: idempotency_key 重複（{idempotency_key}），跳過插入")
                return None

    async def fetch_pending(self, limit: int) -> list[BufferedRow]:
        """依 ``row_id`` 升冪取出尚未同步的資料"""
        if self._conn is None:
            return []

        rows: list[BufferedRow] = []
        async with self._conn.execute(
            "SELECT id, collection_name, document_json, idempotency_key, enqueued_at, retry_count "
            "FROM pending_documents WHERE synced = 0 ORDER BY id ASC LIMIT ?",
            (limit,),
        ) as cur:
            async for row in cur:
                rows.append(
                    BufferedRow(
                        row_id=int(row[0]),
                        collection=str(row[1]),
                        doc_json=str(row[2]),
                        idempotency_key=str(row[3]),
                        enqueued_at=float(row[4]),
                        retry_count=int(row[5]),
                    )
                )
        return rows

    async def mark_synced(self, row_ids: Sequence[int | str]) -> None:
        """
        將指定 row ids 標記為已同步

        SQLite backend 僅接受整數 id。非 int 型別的 row_id（例如
        MongoBufferStore 的 ObjectId 字串）會嘗試轉為 int，無法轉換
        則略過不更新，避免污染 SQL placeholder 型別。
        """
        if self._conn is None:
            return
        ids_int = self._coerce_int_ids(row_ids)
        if not ids_int:
            return
        now = datetime.now(UTC).timestamp()
        placeholders = ",".join("?" for _ in ids_int)
        params: list[float | int] = [now, *ids_int]
        async with self._lock:
            await self._conn.execute(
                f"UPDATE pending_documents SET synced = 1, synced_at = ? WHERE id IN ({placeholders}) AND synced = 0",
                params,
            )
            await self._conn.commit()

    async def bump_retry(self, row_ids: Sequence[int | str]) -> None:
        """累加指定 row 的 retry_count"""
        if self._conn is None:
            return
        ids_int = self._coerce_int_ids(row_ids)
        if not ids_int:
            return
        placeholders = ",".join("?" for _ in ids_int)
        async with self._lock:
            await self._conn.execute(
                f"UPDATE pending_documents SET retry_count = retry_count + 1 WHERE id IN ({placeholders})",
                ids_int,
            )
            await self._conn.commit()

    @staticmethod
    def _coerce_int_ids(row_ids: Sequence[int | str]) -> list[int]:
        """將外部 row_ids 轉為 int list；非 int-like 值會被略過"""
        return [int(rid) for rid in row_ids if isinstance(rid, int | str) and str(rid).lstrip("-").isdigit()]

    async def delete_synced_before(self, cutoff_ts: float) -> int:
        """刪除 synced=1 且 synced_at < cutoff_ts 的 row，回傳刪除筆數"""
        if self._conn is None:
            return 0
        async with self._lock:
            cursor = await self._conn.execute(
                "DELETE FROM pending_documents WHERE synced = 1 AND synced_at < ?",
                (cutoff_ts,),
            )
            await self._conn.commit()
        return int(cursor.rowcount or 0)

    async def count_pending(self) -> int:
        """回傳 synced=0 的筆數"""
        if self._conn is None:
            return 0
        async with self._conn.execute("SELECT COUNT(*) FROM pending_documents WHERE synced = 0") as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def max_synced_sequence(self) -> int | str:
        """回傳 synced=1 的最大 id（無資料時回 ``0``）"""
        if self._conn is None:
            return 0
        async with self._conn.execute("SELECT COALESCE(MAX(id), 0) FROM pending_documents WHERE synced = 1") as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def health_check(self) -> bool:
        """執行 ``SELECT 1`` 確認連線可用"""
        if self._conn is None:
            return False
        try:
            async with self._conn.execute("SELECT 1") as cur:
                row = await cur.fetchone()
            return row is not None
        except Exception:
            return False


__all__ = [
    "SqliteBufferStore",
]
