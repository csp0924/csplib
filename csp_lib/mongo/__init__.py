"""
MongoDB Module

提供 MongoDB 批次上傳功能與客戶端封裝。

需安裝 optional dependency：
    uv pip install csp0924_lib[mongo]

Local buffer backend 選項：
    - ``SqliteBufferStore``（檔案式，aiosqlite）：額外安裝 ``[local-buffer]``
    - ``MongoBufferStore``（本地 mongod，motor）：已包含於 ``[mongo]`` extra

``SqliteBufferStore`` / ``MongoBufferStore`` 採 lazy import：僅當實際
存取時才觸發底層 import。若對應 extra 未安裝，會拋出明確的
``ImportError``（由子模組頂層守衛產生），而非 ``NoneType is not callable``。

Usage:
    from csp_lib.mongo import (
        MongoConfig,
        create_mongo_client,
        MongoBatchUploader,
        UploaderConfig,
        WriteResult,
        LocalBufferConfig,
        LocalBufferedUploader,
        LocalBufferStore,
        SqliteBufferStore,
        MongoBufferStore,
        BufferedRow,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from motor.motor_asyncio import AsyncIOMotorDatabase  # noqa: F401
except ImportError as e:
    raise ImportError("MongoDB module requires 'motor' package. Install with: uv pip install csp0924_lib[mongo]") from e

from csp_lib.mongo.client import MongoConfig, create_mongo_client
from csp_lib.mongo.config import UploaderConfig
from csp_lib.mongo.local_buffer import (
    BufferedRow,
    LocalBufferConfig,
    LocalBufferedUploader,
    LocalBufferStore,
)
from csp_lib.mongo.uploader import MongoBatchUploader
from csp_lib.mongo.writer import WriteResult

if TYPE_CHECKING:
    from csp_lib.mongo.local_buffer import MongoBufferStore, SqliteBufferStore

__all__ = [
    "BufferedRow",
    "LocalBufferConfig",
    "LocalBufferStore",
    "LocalBufferedUploader",
    "MongoBatchUploader",
    "MongoBufferStore",
    "MongoConfig",
    "SqliteBufferStore",
    "UploaderConfig",
    "WriteResult",
    "create_mongo_client",
]


def __getattr__(name: str) -> Any:
    """Lazy import optional backends，對齊 :mod:`csp_lib.mongo.local_buffer`。

    若 aiosqlite / motor 相關 extra 未裝，子模組頂層守衛會 raise
    明確 ``ImportError``，直接向呼叫端傳遞。
    """
    if name in ("SqliteBufferStore", "MongoBufferStore"):
        from csp_lib.mongo import local_buffer

        return getattr(local_buffer, name)
    raise AttributeError(f"module 'csp_lib.mongo' has no attribute {name!r}")
