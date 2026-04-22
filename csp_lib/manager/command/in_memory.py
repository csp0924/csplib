# =============== Manager Command - In-Memory Repository ===============
#
# 記憶體內指令記錄儲存庫
#
# 提供不依賴 MongoDB 的 CommandRepository 實作：
#   - InMemoryCommandRepository: 記憶體內實作（供測試與開發使用）

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from csp_lib.core import get_logger

from .schema import TERMINAL_STATUSES, CommandRecord, CommandStatus

logger = get_logger(__name__)


class InMemoryCommandRepository:
    """
    記憶體內指令記錄儲存庫

    實作 CommandRepository Protocol，將指令記錄儲存在記憶體中。
    使用 uuid4 生成唯一 ID。

    Attributes:
        _lock: 執行緒安全鎖
        _records: command_id → CommandRecord 的映射
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, CommandRecord] = {}

    async def health_check(self) -> bool:
        """檢查健康狀態

        Returns:
            永遠回傳 True
        """
        return True

    async def create(self, record: CommandRecord) -> str:
        """建立指令記錄

        Args:
            record: 指令記錄

        Returns:
            記錄 ID（uuid4 hex）
        """
        record_id = uuid4().hex
        with self._lock:
            self._records[record_id] = record
        logger.debug(f"指令記錄已建立: {record.command_id} (id={record_id})")
        return record_id

    async def update_status(
        self,
        command_id: str,
        status: CommandStatus,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> bool:
        """更新指令狀態

        依據狀態自動設定時間戳：
        - EXECUTING → 設定 executed_at
        - SUCCESS/FAILED/DEVICE_NOT_FOUND/VALIDATION_FAILED → 設定 completed_at

        Args:
            command_id: 指令 ID
            status: 新狀態
            result: 執行結果
            error_message: 錯誤訊息

        Returns:
            是否更新成功
        """
        with self._lock:
            # 以 command_id 欄位搜尋（與 Mongo 版行為一致）
            record = self._find_by_command_id(command_id)
            if record is None:
                return False

            record.status = status

            if status == CommandStatus.EXECUTING:
                record.executed_at = datetime.now(timezone.utc)
            elif status in TERMINAL_STATUSES:
                record.completed_at = datetime.now(timezone.utc)

            if result is not None:
                record.result = result

            if error_message is not None:
                record.error_message = error_message

        logger.debug(f"指令狀態已更新: {command_id} -> {status.value}")
        return True

    async def get(self, command_id: str) -> CommandRecord | None:
        """取得指令記錄

        Args:
            command_id: 指令 ID

        Returns:
            指令記錄，不存在時返回 None
        """
        with self._lock:
            return self._find_by_command_id(command_id)

    async def list_by_device(self, device_id: str, limit: int = 100) -> list[CommandRecord]:
        """取得設備的指令記錄

        按 timestamp DESC 排序。

        Args:
            device_id: 設備 ID
            limit: 最大數量

        Returns:
            指令記錄列表
        """
        with self._lock:
            matched = [r for r in self._records.values() if r.device_id == device_id]
        # 按 timestamp DESC 排序
        matched.sort(key=lambda r: r.timestamp, reverse=True)
        return matched[:limit]

    def _find_by_command_id(self, command_id: str) -> CommandRecord | None:
        """以 command_id 欄位搜尋記錄（需持有 _lock）

        Args:
            command_id: 指令 ID

        Returns:
            找到的記錄，或 None
        """
        for record in self._records.values():
            if record.command_id == command_id:
                return record
        return None

    # === 測試輔助方法 ===

    def get_all_records(self) -> dict[str, CommandRecord]:
        """取得所有指令記錄

        Returns:
            內部 ID → CommandRecord 的映射副本
        """
        with self._lock:
            return dict(self._records)

    def clear(self) -> None:
        """清除所有記錄"""
        with self._lock:
            self._records.clear()


__all__ = [
    "InMemoryCommandRepository",
]
