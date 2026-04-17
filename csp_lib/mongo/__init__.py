"""
MongoDB Module

提供 MongoDB 批次上傳功能與客戶端封裝。

需安裝 optional dependency：
    uv pip install csp0924_lib[mongo]

Local buffer backend 選項：
    - ``SqliteBufferStore``（檔案式，aiosqlite）：額外安裝 ``[local-buffer]``
    - ``MongoBufferStore``（本地 mongod，motor）：已包含於 ``[mongo]`` extra

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
    MongoBufferStore,
    SqliteBufferStore,
)
from csp_lib.mongo.uploader import MongoBatchUploader
from csp_lib.mongo.writer import WriteResult

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
