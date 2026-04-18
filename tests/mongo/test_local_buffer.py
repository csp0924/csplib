# =============== Mongo Tests - LocalBufferedUploader ===============
#
# LocalBufferedUploader 單元測試（v0.8.2）
#
# v0.8.2 重構：
#   - LocalBufferConfig 不再擁有 db_path（由具體 backend 自行保存）
#   - LocalBufferedUploader 必須注入 LocalBufferStore（通常為 SqliteBufferStore）
#
# 測試覆蓋：
#   - LocalBufferConfig __post_init__ 驗證
#   - 生命週期：啟動建表、停止清理、重啟保留資料
#   - enqueue 寫 SQLite、idempotency_key 注入（自動/尊重既有）
#   - replay happy path、downstream 失敗保留、duplicate 視為成功
#   - write_immediate 成功/失敗落地保證
#   - cleanup retention 行為
#   - ensure_indexes 對 MongoDB 建立唯一稀疏索引
#   - health_check / crash recovery / counter 語義

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

aiosqlite = pytest.importorskip("aiosqlite")  # 未安裝則整個測試檔跳過

from csp_lib.mongo.local_buffer import (  # noqa: E402
    LocalBufferConfig,
    LocalBufferedUploader,
    SqliteBufferStore,
)
from csp_lib.mongo.writer import WriteResult  # noqa: E402

# ======================== 工具：建立 mock downstream / store / uploader ========================


def _make_mock_downstream(
    default_result: WriteResult | None = None,
) -> MagicMock:
    """
    建立一個 mock MongoBatchUploader，具備：
    - writer.write_batch: AsyncMock（replay 路徑使用）
    - write_immediate: AsyncMock（write_immediate 路徑使用）
    - register_collection: MagicMock
    """
    downstream = MagicMock()
    downstream.register_collection = MagicMock()
    downstream.write_immediate = AsyncMock(return_value=default_result or WriteResult(success=True, inserted_count=1))
    writer = MagicMock()
    writer.write_batch = AsyncMock(return_value=default_result or WriteResult(success=True, inserted_count=1))
    # 下游 writer.db 可供 ensure_indexes 取用；預設 None，由需要者自行注入
    writer.db = None
    downstream.writer = writer
    return downstream


def _db_path(tmp_path: Path) -> str:
    return str(tmp_path / "buffer.db")


def _make_store(tmp_path: Path) -> SqliteBufferStore:
    """建立 SqliteBufferStore，db_path 指向 tmp_path/buffer.db"""
    return SqliteBufferStore(_db_path(tmp_path))


def _fast_config(**overrides: object) -> LocalBufferConfig:
    """產生一個將 interval 縮短以利測試的 config（v0.8.2：不再含 db_path）"""
    kwargs: dict[str, object] = {
        "replay_interval": 0.1,
        "replay_batch_size": 500,
        "cleanup_interval": 0.1,
        "retention_seconds": 86400.0,
        "max_retry_count": 3,
    }
    kwargs.update(overrides)
    return LocalBufferConfig(**kwargs)  # type: ignore[arg-type]


def _make_uploader(
    tmp_path: Path,
    downstream: MagicMock | None = None,
    **config_overrides: object,
) -> tuple[LocalBufferedUploader, SqliteBufferStore, str]:
    """
    組合建構（v0.8.2 標準呼叫）：
        LocalBufferedUploader(downstream, store=SqliteBufferStore(...), config=...)

    Returns:
        (uploader, store, db_path)
    """
    ds = downstream if downstream is not None else _make_mock_downstream()
    store = _make_store(tmp_path)
    cfg = _fast_config(**config_overrides)
    uploader = LocalBufferedUploader(downstream=ds, store=store, config=cfg)
    return uploader, store, _db_path(tmp_path)


def _count_rows(db_path: str, where: str = "1=1") -> int:
    """同步以 sqlite3 讀取 pending_documents 列數"""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM pending_documents WHERE {where}")
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


# ======================== LocalBufferConfig 驗證 ========================


class TestLocalBufferConfig:
    """LocalBufferConfig __post_init__ 邊界驗證（v0.8.2：已無 db_path 欄位）"""

    def test_default_values(self):
        """預設值應全部合法"""
        cfg = LocalBufferConfig()
        assert cfg.replay_interval > 0
        assert cfg.replay_batch_size > 0
        assert cfg.cleanup_interval > 0
        assert cfg.retention_seconds >= 0
        assert cfg.max_retry_count >= 0

    def test_non_positive_replay_interval_raises(self):
        with pytest.raises(ValueError, match="replay_interval"):
            LocalBufferConfig(replay_interval=0)
        with pytest.raises(ValueError, match="replay_interval"):
            LocalBufferConfig(replay_interval=-1)

    def test_non_positive_replay_batch_size_raises(self):
        with pytest.raises(ValueError, match="replay_batch_size"):
            LocalBufferConfig(replay_batch_size=0)
        with pytest.raises(ValueError, match="replay_batch_size"):
            LocalBufferConfig(replay_batch_size=-5)

    def test_non_positive_cleanup_interval_raises(self):
        with pytest.raises(ValueError, match="cleanup_interval"):
            LocalBufferConfig(cleanup_interval=0)
        with pytest.raises(ValueError, match="cleanup_interval"):
            LocalBufferConfig(cleanup_interval=-0.1)

    def test_negative_retention_seconds_raises(self):
        with pytest.raises(ValueError, match="retention_seconds"):
            LocalBufferConfig(retention_seconds=-1)

    def test_zero_retention_seconds_allowed(self):
        """retention_seconds=0 允許（代表立即清理）"""
        cfg = LocalBufferConfig(retention_seconds=0)
        assert cfg.retention_seconds == 0

    def test_negative_max_retry_count_raises(self):
        with pytest.raises(ValueError, match="max_retry_count"):
            LocalBufferConfig(max_retry_count=-1)


# ======================== SqliteBufferStore 基本驗證 ========================


class TestSqliteBufferStoreBasic:
    """SqliteBufferStore ctor 與基本語義"""

    def test_empty_db_path_raises(self):
        with pytest.raises(ValueError, match="db_path"):
            SqliteBufferStore("")


# ======================== Lifecycle ========================


class TestLocalBufferedUploaderLifecycle:
    """啟動建表、停止、重啟保留資料"""

    async def test_start_creates_schema(self, tmp_path: Path):
        """start() 應建立 pending_documents 表與索引"""
        uploader, store, db_path = _make_uploader(tmp_path)

        await uploader.start()
        try:
            # 此時 db 已建立
            assert os.path.exists(db_path)
            # 檢查 schema
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_documents'")
                assert cur.fetchone() is not None
                # 索引應存在（至少 unique idempotency_key）
                cur = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_idempotency_key'")
                assert cur.fetchone() is not None
            finally:
                conn.close()
        finally:
            await uploader.stop()

    async def test_stop_closes_connection(self, tmp_path: Path):
        """stop() 後 store._conn 應為 None"""
        uploader, store, _ = _make_uploader(tmp_path)
        await uploader.start()
        await uploader.stop()
        assert store._conn is None

    async def test_restart_preserves_data(self, tmp_path: Path):
        """停止後重啟，既有資料仍可見"""
        downstream1 = _make_mock_downstream()
        uploader1, _, db_path = _make_uploader(tmp_path, downstream=downstream1, replay_interval=60.0)

        await uploader1.start()
        try:
            await uploader1.enqueue("telemetry", {"val": 1})
            await uploader1.enqueue("telemetry", {"val": 2})
            assert await uploader1.get_pending_count() == 2
        finally:
            await uploader1.stop()

        # 重新建立一個 uploader（相同 db_path；需要新 Store 實例）
        downstream2 = _make_mock_downstream()
        store2 = SqliteBufferStore(db_path)
        cfg2 = _fast_config(replay_interval=60.0)
        uploader2 = LocalBufferedUploader(downstream=downstream2, store=store2, config=cfg2)
        await uploader2.start()
        try:
            pending = await uploader2.get_pending_count()
            # 重啟後既有未同步資料仍存在（可能 >= 2，因 stop() 最後會 drain 一次）
            # 但由於 downstream 為 AsyncMock 會回 success → drain 會標記為 synced
            # 因此 pending 可能為 0。重點是總 row 數 >= 2
            total = _count_rows(db_path)
            assert total >= 2, f"重啟後應保留資料（total={total}, pending={pending}）"
        finally:
            await uploader2.stop()

    async def test_context_manager_usage(self, tmp_path: Path):
        """async with 語法使用正常"""
        uploader, store, _ = _make_uploader(tmp_path)

        async with uploader:
            await uploader.enqueue("c1", {"x": 1})
            assert store._conn is not None

        assert store._conn is None


# ======================== Enqueue ========================


class TestLocalBufferedUploaderEnqueue:
    """enqueue 寫 SQLite 與 idempotency_key 處理"""

    async def test_enqueue_persists_to_sqlite(self, tmp_path: Path):
        """enqueue 後 SQLite 應有未同步 row"""
        uploader, _, db_path = _make_uploader(tmp_path, replay_interval=60.0)

        async with uploader:
            await uploader.enqueue("telemetry", {"ts": 1234, "val": 42})
            pending = await uploader.get_pending_count()
            assert pending == 1

            # 直接驗 SQLite 欄位
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute(
                    "SELECT collection_name, document_json, idempotency_key, synced FROM pending_documents"
                )
                rows = cur.fetchall()
                assert len(rows) == 1
                coll, doc_json, key, synced = rows[0]
                assert coll == "telemetry"
                assert "42" in doc_json
                assert key  # 非空
                assert synced == 0
            finally:
                conn.close()

    async def test_enqueue_auto_generates_idempotency_key(self, tmp_path: Path):
        """文件無 _idempotency_key 時應自動產生"""
        uploader, _, db_path = _make_uploader(tmp_path, replay_interval=60.0)

        async with uploader:
            await uploader.enqueue("coll", {"a": 1})
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute("SELECT idempotency_key FROM pending_documents")
                key = cur.fetchone()[0]
                assert key.startswith("coll:"), "自動生成 key 應以 collection 名為前綴"
                # 格式為 "<collection>:<uuid4 hex>"（uuid4 已提供足夠亂數，不再疊加 sha1）
                parts = key.split(":")
                assert len(parts) == 2
                assert len(parts[1]) == 32  # uuid4 hex 為 32 chars
            finally:
                conn.close()

    async def test_enqueue_respects_explicit_idempotency_key(self, tmp_path: Path):
        """文件既有 _idempotency_key 應被保留"""
        uploader, _, db_path = _make_uploader(tmp_path, replay_interval=60.0)

        async with uploader:
            await uploader.enqueue("coll", {"_idempotency_key": "my-custom-key-42", "val": 7})
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute("SELECT idempotency_key FROM pending_documents")
                assert cur.fetchone()[0] == "my-custom-key-42"
            finally:
                conn.close()

    async def test_enqueue_duplicate_explicit_key_is_deduplicated(self, tmp_path: Path):
        """相同顯式 key 多次 enqueue 應只保留一筆（UNIQUE constraint）"""
        uploader, _, db_path = _make_uploader(tmp_path, replay_interval=60.0)

        async with uploader:
            await uploader.enqueue("coll", {"_idempotency_key": "same-key", "v": 1})
            await uploader.enqueue("coll", {"_idempotency_key": "same-key", "v": 2})

            # 僅一筆
            assert _count_rows(db_path) == 1


# ======================== Replay ========================


class TestLocalBufferedUploaderReplay:
    """背景 replay 行為"""

    async def test_replay_once_sends_to_downstream(self, tmp_path: Path):
        """replay 成功路徑：writer.write_batch 被呼叫，pending 歸零"""
        downstream = _make_mock_downstream(default_result=WriteResult(success=True, inserted_count=10))
        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            for i in range(10):
                await uploader.enqueue("telemetry", {"i": i})
            assert await uploader.get_pending_count() == 10

            await uploader._replay_once()

            # writer.write_batch 被呼叫（ordered=False）
            downstream.writer.write_batch.assert_awaited_once()
            call = downstream.writer.write_batch.await_args
            assert call.args[0] == "telemetry"
            assert len(call.args[1]) == 10
            assert call.kwargs.get("ordered") is False

            assert await uploader.get_pending_count() == 0

    async def test_replay_downstream_failure_preserves_rows(self, tmp_path: Path):
        """downstream 失敗（含 non-dup errors）→ row 保留 synced=0 等重試"""
        downstream = _make_mock_downstream(
            default_result=WriteResult(success=False, error_message="mongo down"),
        )
        uploader, _, db_path = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            for i in range(5):
                await uploader.enqueue("telemetry", {"i": i})

            await uploader._replay_once()

            # 全部仍保留
            assert await uploader.get_pending_count() == 5

            # retry_count 有 +1
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute("SELECT MIN(retry_count), MAX(retry_count) FROM pending_documents")
                min_r, max_r = cur.fetchone()
                assert min_r >= 1
                assert max_r >= 1
            finally:
                conn.close()

    async def test_replay_duplicate_key_treated_as_success(self, tmp_path: Path):
        """downstream 回 success=True + duplicates → 仍應 mark synced"""
        # 5 筆全部 insert_count=0 + duplicate=5 代表「全是重複鍵」，仍算成功
        downstream = _make_mock_downstream(
            default_result=WriteResult(success=True, inserted_count=0, duplicate_key_count=5),
        )
        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            for i in range(5):
                await uploader.enqueue("telemetry", {"i": i})

            await uploader._replay_once()

            # 全部標為 synced
            assert await uploader.get_pending_count() == 0

    async def test_replay_partial_duplicate_partial_insert_is_success(self, tmp_path: Path):
        """downstream success=False 但 inserted + duplicates >= len(docs) 仍應 mark synced"""
        # 5 筆：2 inserted + 3 duplicate = 5 → 視為完整覆蓋
        # 此情境下 success 可為 False（部分錯誤），但 LocalBuffer 的判定條件
        # 包含 inserted + duplicate >= len(docs) 所以也算成功
        downstream = _make_mock_downstream(
            default_result=WriteResult(
                success=False,
                inserted_count=2,
                duplicate_key_count=3,
                error_message="some non-dup",
            ),
        )
        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            for i in range(5):
                await uploader.enqueue("telemetry", {"i": i})

            await uploader._replay_once()

            # 根據實作的判定條件（result.success OR inserted + duplicates >= len）
            # 應全部 mark synced
            assert await uploader.get_pending_count() == 0

    async def test_replay_injects_idempotency_key_into_payload(self, tmp_path: Path):
        """replay 時應將 idempotency_key 寫入 document payload（供 MongoDB 去重）"""
        downstream = _make_mock_downstream()
        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            await uploader.enqueue("telemetry", {"_idempotency_key": "explicit-123", "v": 1})

            await uploader._replay_once()

            call = downstream.writer.write_batch.await_args
            sent_docs = call.args[1]
            assert len(sent_docs) == 1
            assert sent_docs[0]["_idempotency_key"] == "explicit-123"

    async def test_replay_downstream_exception_is_caught(self, tmp_path: Path):
        """downstream writer.write_batch 拋例外不應 crash，row 保留"""
        downstream = _make_mock_downstream()
        downstream.writer.write_batch = AsyncMock(side_effect=RuntimeError("boom"))
        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            await uploader.enqueue("c1", {"x": 1})

            # 不應拋錯
            await uploader._replay_once()

            assert await uploader.get_pending_count() == 1

    async def test_replay_loop_fires_automatically(self, tmp_path: Path):
        """設定短 replay_interval → 背景任務會自動觸發 replay"""
        downstream = _make_mock_downstream()
        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream, replay_interval=0.1)

        async with uploader:
            await uploader.enqueue("c1", {"x": 1})

            # 等待至多 2 秒讓背景 replay 觸發
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if downstream.writer.write_batch.await_count >= 1:
                    break
                await asyncio.sleep(0.05)

            assert downstream.writer.write_batch.await_count >= 1


# ======================== write_immediate ========================


class TestLocalBufferedUploaderWriteImmediate:
    """write_immediate：先落地再同步寫下游"""

    async def test_write_immediate_success_marks_synced(self, tmp_path: Path):
        """downstream 成功 → row 立即 synced=1"""
        downstream = _make_mock_downstream(default_result=WriteResult(success=True, inserted_count=1))
        uploader, _, db_path = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            result = await uploader.write_immediate("alarm_history", {"alarm_key": "k1"})

            assert result.success is True
            downstream.write_immediate.assert_awaited_once()

            # SQLite 應有 row 且 synced=1
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute("SELECT synced FROM pending_documents WHERE collection_name = 'alarm_history'")
                rows = cur.fetchall()
                assert len(rows) == 1
                assert rows[0][0] == 1  # synced
            finally:
                conn.close()

    async def test_write_immediate_downstream_failure_keeps_row_pending(self, tmp_path: Path):
        """downstream 失敗 → row 留 synced=0（等待後續 replay）"""
        downstream = _make_mock_downstream(default_result=WriteResult(success=False, error_message="boom"))
        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            result = await uploader.write_immediate("alarm_history", {"alarm_key": "k2"})

            assert result.success is False
            # row 應仍為 pending
            assert await uploader.get_pending_count() == 1

    async def test_write_immediate_injects_idempotency_key(self, tmp_path: Path):
        """write_immediate 送給 downstream 時 payload 應帶 _idempotency_key"""
        downstream = _make_mock_downstream()
        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            await uploader.write_immediate("alarm_history", {"alarm_key": "k3"})

            # 下游收到的 payload 應包含 _idempotency_key
            call = downstream.write_immediate.await_args
            assert call.args[0] == "alarm_history"
            payload = call.args[1]
            assert "_idempotency_key" in payload
            assert payload["alarm_key"] == "k3"

    async def test_write_immediate_respects_explicit_key(self, tmp_path: Path):
        """文件已有 _idempotency_key 時不應覆寫"""
        downstream = _make_mock_downstream()
        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            await uploader.write_immediate(
                "alarm_history",
                {"_idempotency_key": "preset-99", "alarm_key": "k4"},
            )

            call = downstream.write_immediate.await_args
            payload = call.args[1]
            assert payload["_idempotency_key"] == "preset-99"

    async def test_write_immediate_downstream_exception_returns_failure(self, tmp_path: Path):
        """downstream 拋例外時仍應回傳 success=False 而非傳播例外"""
        downstream = _make_mock_downstream()
        downstream.write_immediate = AsyncMock(side_effect=RuntimeError("down"))
        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            result = await uploader.write_immediate("alarm_history", {"alarm_key": "k5"})
            assert result.success is False
            # row 仍留在 buffer 中
            assert await uploader.get_pending_count() == 1


# ======================== Cleanup / retention ========================


class TestLocalBufferedUploaderCleanup:
    """retention_seconds 到期的 synced=1 row 應被清除"""

    async def test_cleanup_removes_expired_synced_rows(self, tmp_path: Path):
        """已 synced 且超過 retention 的 row 應被刪除"""
        uploader, store, db_path = _make_uploader(
            tmp_path,
            replay_interval=60.0,
            cleanup_interval=60.0,  # 禁用自動 cleanup
            retention_seconds=1.0,  # 1 秒保留
        )

        async with uploader:
            # 寫入 + 立即標為 synced（模擬已同步）
            await uploader.enqueue("c1", {"v": 1})
            await store.mark_synced([1])

            # 手動把 synced_at 調到遠古時間，保證遠小於 cutoff
            # 透過 sqlite3 同步更新（測試內部 API 存取底層 DB）
            assert store._conn is not None
            await store._conn.execute("UPDATE pending_documents SET synced_at = ? WHERE id = 1", (0.0,))
            await store._conn.commit()

            # 執行 cleanup
            await uploader._cleanup_once()

            # 已被刪除
            assert _count_rows(db_path) == 0

    async def test_cleanup_preserves_pending_rows(self, tmp_path: Path):
        """未 synced 的 row 不應被 cleanup 刪除，即使時間已過"""
        uploader, _, db_path = _make_uploader(
            tmp_path,
            replay_interval=60.0,
            cleanup_interval=60.0,
            retention_seconds=0.0,  # 立即過期
        )

        async with uploader:
            await uploader.enqueue("c1", {"v": 1})
            # 沒有 mark_synced → 不應被清掉

            await uploader._cleanup_once()

            assert _count_rows(db_path) == 1
            assert await uploader.get_pending_count() == 1


# ======================== ensure_indexes ========================


class TestLocalBufferedUploaderEnsureIndexes:
    """ensure_indexes 對 MongoDB 建立唯一稀疏索引"""

    async def test_ensure_indexes_calls_create_index_for_registered_collections(self, tmp_path: Path):
        """已註冊 collection 應呼叫 create_index(unique=True, sparse=True)"""
        downstream = _make_mock_downstream()

        mock_collection = MagicMock()
        mock_collection.create_index = AsyncMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        downstream.writer.db = mock_db

        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream)

        async with uploader:
            uploader.register_collection("alarm_history")
            uploader.register_collection("telemetry")

            await uploader.ensure_indexes()

            # create_index 至少被呼叫 2 次（每個 collection 一次）
            assert mock_collection.create_index.await_count == 2
            # 抽查 kwargs
            for call in mock_collection.create_index.await_args_list:
                assert call.kwargs.get("unique") is True
                assert call.kwargs.get("sparse") is True
                # index spec 應為 _idempotency_key ASC
                assert call.args[0] == [("_idempotency_key", 1)]

    async def test_ensure_indexes_noop_when_db_unavailable(self, tmp_path: Path):
        """writer.db 為 None 時 ensure_indexes 應不拋錯（logger warning）"""
        downstream = _make_mock_downstream()
        downstream.writer.db = None

        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream)

        async with uploader:
            uploader.register_collection("c1")
            # 不應拋錯
            await uploader.ensure_indexes()

    async def test_ensure_indexes_tolerates_individual_failure(self, tmp_path: Path):
        """單一 collection create_index 失敗不應影響其他 collection"""
        downstream = _make_mock_downstream()

        mock_coll_ok = MagicMock()
        mock_coll_ok.create_index = AsyncMock()
        mock_coll_fail = MagicMock()
        mock_coll_fail.create_index = AsyncMock(side_effect=RuntimeError("index failed"))

        def getitem(name: str):
            return mock_coll_fail if name == "bad" else mock_coll_ok

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(side_effect=getitem)
        downstream.writer.db = mock_db

        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream)

        async with uploader:
            uploader.register_collection("bad")
            uploader.register_collection("good")

            # 不應拋錯
            await uploader.ensure_indexes()


# ======================== health_check ========================


class TestLocalBufferedUploaderHealthCheck:
    """health_check：conn 開啟時 True，關閉時 False"""

    async def test_health_check_true_when_running(self, tmp_path: Path):
        uploader, _, _ = _make_uploader(tmp_path)
        async with uploader:
            assert await uploader.health_check() is True

    async def test_health_check_false_when_stopped(self, tmp_path: Path):
        uploader, _, _ = _make_uploader(tmp_path)
        # 未啟動
        assert await uploader.health_check() is False

        # 啟動後再停止
        await uploader.start()
        await uploader.stop()
        assert await uploader.health_check() is False


# ======================== Crash recovery ========================


class TestLocalBufferedUploaderCrashRecovery:
    """強制停止（不 drain）→ 重啟後能恢復未送出資料"""

    async def test_crash_recovery_pending_visible_after_restart(self, tmp_path: Path):
        """
        模擬 crash：直接關 store._conn 不走正常 stop() 流程，
        重啟後 pending_count 應等於未同步的筆數
        """
        uploader, store, db_path = _make_uploader(tmp_path, replay_interval=60.0)  # 禁 replay

        await uploader.start()
        try:
            # 塞 100 筆
            for i in range(100):
                await uploader.enqueue("telemetry", {"i": i})
            assert await uploader.get_pending_count() == 100
        finally:
            # 「強制」關 store connection 模擬 crash（跳過 drain）
            if store._conn is not None:
                await store._conn.close()
                store._conn = None
            # 同時取消背景任務避免 asyncio 警告
            uploader._stop_event.set()
            for t in (uploader._replay_task, uploader._cleanup_task):
                if t is not None:
                    t.cancel()
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass

        # 重啟（相同 db_path，新 Store 實例）
        downstream2 = _make_mock_downstream()
        store2 = SqliteBufferStore(db_path)
        cfg2 = _fast_config(replay_interval=60.0)
        uploader2 = LocalBufferedUploader(downstream=downstream2, store=store2, config=cfg2)
        await uploader2.start()
        try:
            # 所有 100 筆仍為 pending
            assert await uploader2.get_pending_count() == 100

            # 手動 replay 一次 → downstream 應被呼叫
            await uploader2._replay_once()
            assert downstream2.writer.write_batch.await_count == 1
            call = downstream2.writer.write_batch.await_args
            assert call.args[0] == "telemetry"
            assert len(call.args[1]) == 100
        finally:
            await uploader2.stop()


# ======================== Counters ========================


class TestLocalBufferedUploaderCounter:
    """get_pending_count / get_sync_cursor 語義"""

    async def test_get_pending_count_zero_when_empty(self, tmp_path: Path):
        uploader, _, _ = _make_uploader(tmp_path)
        async with uploader:
            assert await uploader.get_pending_count() == 0

    async def test_get_pending_count_before_start(self, tmp_path: Path):
        """未啟動時 conn=None → get_pending_count 應回 0"""
        uploader, _, _ = _make_uploader(tmp_path)
        assert await uploader.get_pending_count() == 0

    async def test_get_sync_cursor_tracks_max_synced_id(self, tmp_path: Path):
        """get_sync_cursor 應回傳最大已同步 id"""
        uploader, store, _ = _make_uploader(tmp_path, replay_interval=60.0)

        async with uploader:
            assert await uploader.get_sync_cursor() == 0

            # 塞 3 筆
            await uploader.enqueue("c1", {"i": 1})
            await uploader.enqueue("c1", {"i": 2})
            await uploader.enqueue("c1", {"i": 3})

            # 標記 id=1,2 為 synced（透過 store 直接呼叫）
            await store.mark_synced([1, 2])

            cursor = await uploader.get_sync_cursor()
            assert cursor == 2

    async def test_get_sync_cursor_before_start(self, tmp_path: Path):
        uploader, _, _ = _make_uploader(tmp_path)
        assert await uploader.get_sync_cursor() == 0

    async def test_pending_count_decreases_after_replay_success(self, tmp_path: Path):
        """成功 replay 後 pending_count 應減少"""
        downstream = _make_mock_downstream(default_result=WriteResult(success=True, inserted_count=3))
        uploader, _, _ = _make_uploader(tmp_path, downstream=downstream, replay_interval=60.0)

        async with uploader:
            for i in range(3):
                await uploader.enqueue("c1", {"i": i})
            assert await uploader.get_pending_count() == 3

            await uploader._replay_once()
            assert await uploader.get_pending_count() == 0
