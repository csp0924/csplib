# =============== Manager - In-Memory Uploader ===============
#
# 記憶體內批次上傳器實作
#
# 提供不依賴外部儲存的 BatchUploader 實作：
#   - NullBatchUploader: 空操作實作（靜默丟棄所有資料）
#   - InMemoryBatchUploader: 記憶體內實作（供測試與開發使用）

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

from csp_lib.core import get_logger

logger = get_logger(__name__)


class NullBatchUploader:
    """
    空操作批次上傳器

    實作 BatchUploader Protocol，所有操作皆為 no-op。
    適用於不需要資料上傳的場景（如單機模式、測試環境）。
    """

    def register_collection(self, collection_name: str) -> None:
        """註冊 collection（no-op）

        Args:
            collection_name: Collection 名稱
        """

    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None:
        """將文件加入佇列（no-op）

        Args:
            collection_name: 目標 collection 名稱
            document: 要上傳的文件
        """

    async def health_check(self) -> bool:
        """檢查健康狀態

        Returns:
            永遠回傳 True
        """
        return True


class InMemoryBatchUploader:
    """
    記憶體內批次上傳器

    實作 BatchUploader Protocol，將文件儲存在記憶體中。
    適用於測試場景，可透過輔助方法檢查已入列的文件。

    Attributes:
        _lock: 執行緒安全鎖
        _collections: 已註冊的 collection 集合
        _documents: 各 collection 的文件列表
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._collections: set[str] = set()
        self._documents: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    def register_collection(self, collection_name: str) -> None:
        """註冊 collection 名稱

        Args:
            collection_name: Collection 名稱
        """
        with self._lock:
            self._collections.add(collection_name)

    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None:
        """將文件加入佇列

        未註冊的 collection 會自動建立。

        Args:
            collection_name: 目標 collection 名稱
            document: 要上傳的文件
        """
        with self._lock:
            self._documents[collection_name].append(document)

    async def health_check(self) -> bool:
        """檢查健康狀態

        Returns:
            永遠回傳 True
        """
        return True

    # === 測試輔助方法 ===

    def get_documents(self, collection_name: str) -> list[dict[str, Any]]:
        """取得指定 collection 的所有文件

        Args:
            collection_name: Collection 名稱

        Returns:
            該 collection 的文件列表副本
        """
        with self._lock:
            return list(self._documents[collection_name])

    def get_all_documents(self) -> dict[str, list[dict[str, Any]]]:
        """取得所有 collection 的文件

        Returns:
            collection 名稱到文件列表的映射副本
        """
        with self._lock:
            return {k: list(v) for k, v in self._documents.items()}

    def clear(self, collection_name: str | None = None) -> None:
        """清除文件

        Args:
            collection_name: 指定 collection 名稱，None 時清除全部
        """
        with self._lock:
            if collection_name is None:
                self._documents.clear()
            else:
                self._documents[collection_name].clear()


__all__ = [
    "InMemoryBatchUploader",
    "NullBatchUploader",
]
