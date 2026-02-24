"""
BatchQueue 模組

提供 async-safe 的批次佇列管理，職責單一：管理資料的進出與容量控制。
"""

import asyncio
from collections import deque
from typing import Any

from csp_lib.core import get_logger

logger = get_logger(__name__)


class BatchQueue:
    """
    Async-safe 批次佇列

    特點：
    - 使用 asyncio.Lock 確保協程安全
    - 支援容量上限，超過時丟棄最舊資料
    - 提供 drain/restore 操作支援批次處理

    Attributes:
        collection_name: 對應的 MongoDB collection 名稱
        max_size: 佇列最大容量
    """

    def __init__(self, collection_name: str, max_size: int = 10000) -> None:
        self.collection_name = collection_name
        self.max_size = max_size
        self._queue: deque[dict[str, Any]] = deque()
        self._lock = asyncio.Lock()

    async def enqueue(self, document: dict[str, Any]) -> bool:
        """
        將文件加入佇列

        Args:
            document: 要加入的文件

        Returns:
            True 表示成功加入，False 表示因容量已滿而丟棄舊資料
        """
        async with self._lock:
            dropped = False
            if len(self._queue) >= self.max_size:
                self._queue.popleft()  # 丟棄最舊的資料
                dropped = True
                logger.warning(f"BatchQueue[{self.collection_name}]: 容量已滿，丟棄最舊資料")
            self._queue.append(document)
            return not dropped

    async def drain(self) -> list[dict[str, Any]]:
        """
        取出所有資料並清空佇列

        Returns:
            佇列中的所有文件
        """
        async with self._lock:
            documents = list(self._queue)
            self._queue.clear()
            return documents

    async def restore(self, documents: list[dict[str, Any]]) -> None:
        """
        將資料放回佇列前端（用於重試失敗時）

        Args:
            documents: 要放回的文件列表
        """
        async with self._lock:
            for doc in reversed(documents):
                if len(self._queue) < self.max_size:
                    self._queue.appendleft(doc)
                else:
                    logger.warning(f"BatchQueue[{self.collection_name}]: restore 時容量已滿，丟棄資料")
                    break

    async def size(self) -> int:
        """取得目前佇列大小"""
        async with self._lock:
            return len(self._queue)

    def size_sync(self) -> int:
        """
        同步取得目前佇列大小（僅供檢查用，不保證精確）

        注意：此方法不使用 lock，僅供快速判斷是否需要 flush
        """
        return len(self._queue)
