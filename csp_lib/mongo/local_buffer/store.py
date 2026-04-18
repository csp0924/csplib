"""
LocalBufferStore Protocol 與 ``BufferedRow`` 資料類別

此模組定義 backend-agnostic 的本地緩衝儲存介面。上層
``LocalBufferedUploader`` 僅依賴此 Protocol，具體 backend
（SQLite/MongoDB/檔案）由各自的 Store 實作提供。

設計目的：
    - 讓 LocalBufferedUploader 與儲存實作解耦，支援多種 backend
    - 所有 CRUD 都是 async，上層可安全在 asyncio event loop 下呼叫
    - ``BufferedRow`` 為 backend 回傳的唯讀快照，跨邊界傳輸時使用
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class BufferedRow:
    """
    Buffer 中的單筆待同步資料快照

    由 ``LocalBufferStore`` 實作在 ``fetch_pending`` 時產出，上層
    ``LocalBufferedUploader`` 用此結構執行 replay 邏輯。

    Attributes:
        row_id: Backend 賦予的單調遞增 id，用於後續 ``mark_synced`` /
            ``bump_retry`` 指定目標列。SQLite backend 回傳 ``int``；
            MongoDB backend 回傳 ``str``（ObjectId 轉字串）。
        collection: 目標 MongoDB collection 名稱
        doc_json: 序列化後的 document JSON 字串（unicode 直出，非 ASCII
            不會被跳脫）
        idempotency_key: 用於下游去重的唯一 key；上層會在 replay 時
            把此 key 注入 payload
        enqueued_at: 入列時間戳（UTC epoch 秒），供監控或審計使用
        retry_count: 已累計的 replay 重試次數，僅作診斷用途，不影響
            同步判定
    """

    row_id: int | str
    collection: str
    doc_json: str
    idempotency_key: str
    enqueued_at: float
    retry_count: int


@runtime_checkable
class LocalBufferStore(Protocol):
    """
    本地緩衝儲存介面（async CRUD）

    所有方法必須為 async 並能被重複呼叫而不引發非預期的狀態變動
    （``open``/``close`` 需冪等）。實作者負責自己的 thread/task safety，
    上層不會加額外保護。
    """

    async def open(self) -> None:
        """
        開啟底層資源（連線 / 檔案 / schema 建立）

        若已開啟則不應重複建立資源，也不應 raise。
        """
        ...

    async def close(self) -> None:
        """
        關閉底層資源並釋放狀態

        若尚未開啟或已關閉，必須是 no-op，不得拋錯。
        """
        ...

    async def append(
        self,
        collection: str,
        doc_json: str,
        idempotency_key: str,
        *,
        synced: bool = False,
    ) -> int | str | None:
        """
        新增一筆資料到 buffer

        Args:
            collection: 目標 MongoDB collection 名稱
            doc_json: 已序列化好的 document JSON 字串
            idempotency_key: 唯一 key；若 backend 偵測到重複則視為
                已存在而非錯誤
            synced: 入列時即標記為已同步（通常用於 ``write_immediate``
                成功後的一次性寫入路徑）

        Returns:
            新增資料的 ``row_id``（SQLite 為 ``int``、MongoDB 為 ``str``）；
            若因 idempotency_key 衝突而跳過則回 ``None``
        """
        ...

    async def fetch_pending(self, limit: int) -> list[BufferedRow]:
        """
        抓取尚未同步的資料，以 ``row_id`` 升冪排序

        Args:
            limit: 單次最多回傳筆數

        Returns:
            ``BufferedRow`` list；若無資料回空 list
        """
        ...

    async def mark_synced(self, row_ids: Sequence[int | str]) -> None:
        """
        將指定 row 標記為已同步並記錄 ``synced_at``

        Args:
            row_ids: 要標記的 row id 序列；空序列為 no-op
        """
        ...

    async def bump_retry(self, row_ids: Sequence[int | str]) -> None:
        """
        將指定 row 的 ``retry_count`` +1（仍保持 synced=0）

        Args:
            row_ids: 要累加的 row id 序列；空序列為 no-op
        """
        ...

    async def delete_synced_before(self, cutoff_ts: float) -> int:
        """
        刪除 ``synced=1`` 且 ``synced_at < cutoff_ts`` 的 row

        Args:
            cutoff_ts: UTC epoch 秒的截止時間；小於此值的已同步 row
                會被刪除

        Returns:
            實際刪除的筆數
        """
        ...

    async def count_pending(self) -> int:
        """回傳目前尚未同步（``synced=0``）的資料筆數"""
        ...

    async def max_synced_sequence(self) -> int | str:
        """
        回傳已同步資料中最新的 ``row_id``（供監控使用）

        SQLite backend 回傳最大的 AUTOINCREMENT id；MongoDB backend
        回傳最新 ObjectId 的字串表示。若無任何已同步資料則回 ``0``。
        """
        ...

    async def health_check(self) -> bool:
        """
        檢查 backend 是否可查詢

        Returns:
            ``True`` 表示 backend 健康；``False`` 表示尚未開啟或
            發生連線錯誤
        """
        ...


__all__ = [
    "BufferedRow",
    "LocalBufferStore",
]
