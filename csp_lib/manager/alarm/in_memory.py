# =============== Manager Alarm - In-Memory Repository ===============
#
# 記憶體內告警資料存取層
#
# 提供不依賴 MongoDB 的 AlarmRepository 實作：
#   - InMemoryAlarmRepository: 記憶體內實作（供測試與開發使用）

from __future__ import annotations

import threading
from datetime import datetime

from csp_lib.core import get_logger

from .schema import AlarmRecord, AlarmStatus

logger = get_logger(__name__)


class InMemoryAlarmRepository:
    """
    記憶體內告警 Repository 實作

    實作 AlarmRepository Protocol，將告警記錄儲存在記憶體中。
    使用 alarm_key 作為主鍵，支援 upsert 與狀態更新。

    Attributes:
        _lock: 執行緒安全鎖
        _records: alarm_key → AlarmRecord 的映射
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, AlarmRecord] = {}

    async def health_check(self) -> bool:
        """檢查健康狀態

        Returns:
            永遠回傳 True
        """
        return True

    async def upsert(self, record: AlarmRecord) -> tuple[str, bool]:
        """新增告警記錄

        若已存在相同 alarm_key 且狀態為 ACTIVE 的告警，則跳過新增。

        Args:
            record: 告警記錄

        Returns:
            tuple[str, bool]: (告警 ID, 是否為新增)
        """
        with self._lock:
            existing = self._records.get(record.alarm_key)
            if existing is not None and existing.status == AlarmStatus.ACTIVE:
                return existing.alarm_key, False
            self._records[record.alarm_key] = record
            return record.alarm_key, True

    async def resolve(self, alarm_key: str, resolved_at: datetime) -> bool:
        """解除告警

        將指定告警的狀態從 ACTIVE 更新為 RESOLVED，並記錄解除時間。

        Args:
            alarm_key: 告警唯一鍵
            resolved_at: 解除時間

        Returns:
            是否成功解除
        """
        with self._lock:
            record = self._records.get(alarm_key)
            if record is None or record.status != AlarmStatus.ACTIVE:
                return False
            # AlarmRecord 非 frozen，可直接修改
            record.status = AlarmStatus.RESOLVED
            record.resolved_timestamp = resolved_at
            return True

    async def get_active_alarms(self) -> list[AlarmRecord]:
        """取得所有進行中的告警

        Returns:
            所有狀態為 ACTIVE 的告警清單
        """
        with self._lock:
            return [r for r in self._records.values() if r.status == AlarmStatus.ACTIVE]

    async def get_active_by_device(self, device_id: str) -> list[AlarmRecord]:
        """取得指定設備的進行中告警

        Args:
            device_id: 設備識別碼

        Returns:
            該設備所有狀態為 ACTIVE 的告警清單
        """
        with self._lock:
            return [r for r in self._records.values() if r.status == AlarmStatus.ACTIVE and r.device_id == device_id]

    # === 測試輔助方法 ===

    def get_all_records(self) -> dict[str, AlarmRecord]:
        """取得所有告警記錄

        Returns:
            alarm_key → AlarmRecord 的映射副本
        """
        with self._lock:
            return dict(self._records)

    def clear(self) -> None:
        """清除所有記錄"""
        with self._lock:
            self._records.clear()


__all__ = [
    "InMemoryAlarmRepository",
]
