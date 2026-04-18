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

Optional dependency：``SqliteBufferStore`` 與 ``MongoBufferStore`` 採 lazy
import；僅當實際存取該 symbol 時才會觸發底層 import。若對應 extra
（``[local-buffer]`` / ``[mongo]``）未安裝，會拋出明確的 ``ImportError``
而非產生 ``'NoneType' object is not callable`` 的混淆錯誤。

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

from typing import TYPE_CHECKING, Any

from csp_lib.mongo.local_buffer.store import BufferedRow, LocalBufferStore
from csp_lib.mongo.local_buffer.uploader import LocalBufferConfig, LocalBufferedUploader

if TYPE_CHECKING:
    from csp_lib.mongo.local_buffer.mongo_store import MongoBufferStore
    from csp_lib.mongo.local_buffer.sqlite_store import SqliteBufferStore

__all__ = [
    "BufferedRow",
    "LocalBufferConfig",
    "LocalBufferStore",
    "LocalBufferedUploader",
    "MongoBufferStore",
    "SqliteBufferStore",
]


def __getattr__(name: str) -> Any:
    """Lazy import optional backends。

    未安裝對應 extra 時，``import`` 子模組會 raise ``ImportError``
    （由 ``sqlite_store.py`` / ``mongo_store.py`` 頂層守衛提供明確訊息），
    直接向呼叫端傳遞。
    """
    if name == "SqliteBufferStore":
        from csp_lib.mongo.local_buffer.sqlite_store import SqliteBufferStore

        return SqliteBufferStore
    if name == "MongoBufferStore":
        from csp_lib.mongo.local_buffer.mongo_store import MongoBufferStore

        return MongoBufferStore
    raise AttributeError(f"module 'csp_lib.mongo.local_buffer' has no attribute {name!r}")
