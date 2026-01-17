"""
MongoDB Module

提供 MongoDB 批次上傳功能與客戶端封裝。

需安裝 optional dependency：
    uv pip install csp_lib[mongo]

Usage:
    from csp_lib.mongo import (
        MongoConfig,
        create_mongo_client,
        MongoBatchUploader,
        UploaderConfig,
        WriteResult,
    )
"""

try:
    from motor.motor_asyncio import AsyncIOMotorDatabase  # noqa: F401
except ImportError as e:
    raise ImportError("MongoDB module requires 'motor' package. Install with: uv pip install csp_lib[mongo]") from e

from csp_lib.mongo.client import MongoConfig, create_mongo_client
from csp_lib.mongo.config import UploaderConfig
from csp_lib.mongo.uploader import MongoBatchUploader
from csp_lib.mongo.writer import WriteResult

__all__ = [
    "MongoConfig",
    "create_mongo_client",
    "MongoBatchUploader",
    "UploaderConfig",
    "WriteResult",
]
