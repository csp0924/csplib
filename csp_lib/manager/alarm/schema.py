""" """

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from csp_lib.equipment.alarm import AlarmLevel


class AlarmType(str, Enum):
    """告警類型"""

    DISCONNECT = "disconnect"  # 設備斷線
    DEVICE_ALARM = "device_alarm"  # 設備內部告警


class AlarmStatus(str, Enum):
    """告警狀態"""

    ACTIVE = "active"
    RESOLVED = "resolved"


@dataclass
class AlarmRecord:
    """告警記錄 (MongoDB Document)"""

    # === 唯一識別 ===
    alarm_key: str  # 業務唯一鍵: "<device_id>:<alarm_type>:<alarm_code>"

    # === 告警來源 ===
    device_id: str  # 設備識別碼
    alarm_type: AlarmType  # 告警類型: DISCONNECT | DEVICE_ALARM
    alarm_code: str = ""  # 告警代碼 (e.g., "OVER_TEMP", "DISCONNECT")

    # === 告警資訊 ===
    name: str = ""  # 告警名稱
    level: AlarmLevel = AlarmLevel.INFO  # 告警等級
    description: str = ""  # 描述

    # === 時間戳記 ===
    occurred_at: datetime | None = None  # 發生時間
    resolved_at: datetime | None = None  # 解除時間 (None = 進行中)

    # === 狀態 ===
    status: AlarmStatus = AlarmStatus.ACTIVE  # ACTIVE | RESOLVED

    def to_document(self) -> dict[str, Any]:
        """轉換為 MongoDB document"""
        doc = asdict(self)
        doc["alarm_type"] = self.alarm_type.value
        doc["level"] = self.level.value
        doc["status"] = self.status.value
        return doc

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> AlarmRecord:
        """從 MongoDB document 建立"""
        doc = doc.copy()
        doc.pop("_id", None)  # 移除 MongoDB 自動產生的 _id
        doc["alarm_type"] = AlarmType(doc["alarm_type"])
        doc["level"] = AlarmLevel(doc["level"])
        doc["status"] = AlarmStatus(doc["status"])
        return cls(**doc)

    @staticmethod
    def make_key(device_id: str, alarm_type: AlarmType, alarm_code: str) -> str:
        """生成告警唯一鍵"""
        return f"{device_id}:{alarm_type.value}:{alarm_code}"
