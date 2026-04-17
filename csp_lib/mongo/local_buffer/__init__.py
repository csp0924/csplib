"""
LocalBufferedUploader 套件

提供「本地緩衝 + 背景 replay 到 MongoDB」的容錯上傳策略。

Package 結構：
    - ``store``         — ``LocalBufferStore`` Protocol + ``BufferedRow``
    - ``sqlite_store``  — ``SqliteBufferStore``（aiosqlite 實作，預設 backend）
    - ``mongo_store``   — ``MongoBufferStore``（motor 實作，本地 mongod 當 buffer）
    - ``uploader``      — ``LocalBufferedUploader`` + ``LocalBufferConfig``

Backend 選擇：
    - ``SqliteBufferStore`` (aiosqlite)：檔案式，適合輕量部署
    - ``MongoBufferStore`` (motor)：本地 mongod，適合已有 MongoDB 環境

Usage:
    ```python
    # SQLite backend
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

    # MongoDB backend（本地 mongod 當 buffer）
    from motor.motor_asyncio import AsyncIOMotorClient
    from csp_lib.mongo.local_buffer import MongoBufferStore

    local_client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    store = MongoBufferStore(local_client)
    local = LocalBufferedUploader(downstream=mongo_uploader, store=store, config=cfg)
    ```
"""

from __future__ import annotations

from csp_lib.mongo.local_buffer.store import BufferedRow, LocalBufferStore
from csp_lib.mongo.local_buffer.uploader import LocalBufferConfig, LocalBufferedUploader

try:
    from csp_lib.mongo.local_buffer.sqlite_store import SqliteBufferStore
except ImportError:  # pragma: no cover — aiosqlite 未安裝時 fallback
    SqliteBufferStore = None  # type: ignore[assignment,misc]

try:
    from csp_lib.mongo.local_buffer.mongo_store import MongoBufferStore
except ImportError:  # pragma: no cover — motor 未安裝時 fallback（理論上不會發生）
    MongoBufferStore = None  # type: ignore[assignment,misc]

__all__ = [
    "BufferedRow",
    "LocalBufferConfig",
    "LocalBufferStore",
    "LocalBufferedUploader",
    "MongoBufferStore",
    "SqliteBufferStore",
]
