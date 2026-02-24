# =============== Manager Alarm - Schema ===============
#
# 告警資料結構定義
#
# 提供告警系統的核心資料模型：
#   - AlarmType: 告警類型枚舉（斷線/設備告警）
#   - AlarmStatus: 告警狀態枚舉（進行中/已解除）
#   - AlarmRecord: 告警記錄資料類別（MongoDB Document）

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from csp_lib.equipment.alarm import AlarmLevel


class AlarmType(str, Enum):
    """
    告警類型枚舉

    Values:
        DISCONNECT: 設備斷線告警（通訊中斷）
        DEVICE_ALARM: 設備內部告警（如過溫、過載等）
    """

    DISCONNECT = "disconnect"
    DEVICE_ALARM = "device_alarm"


class AlarmStatus(str, Enum):
    """
    告警狀態枚舉

    Values:
        ACTIVE: 進行中（尚未解除）
        RESOLVED: 已解除（恢復正常）
    """

    ACTIVE = "active"
    RESOLVED = "resolved"


@dataclass
class AlarmRecord:
    """
    告警記錄資料類別

    對應 MongoDB Document，用於儲存單筆告警的完整資訊。
    使用 alarm_key 作為業務唯一鍵，支援 upsert 與狀態更新。

    Attributes:
        alarm_key: 業務唯一鍵，格式為 "<device_id>:<alarm_type>:<alarm_code>"
        device_id: 設備識別碼
        alarm_type: 告警類型（DISCONNECT | DEVICE_ALARM）
        alarm_code: 告警代碼（如 "OVER_TEMP", "DISCONNECT"）
        name: 告警名稱（用於顯示）
        level: 告警等級（INFO, WARNING, ERROR, CRITICAL）
        description: 告警描述（詳細說明）
        occurred_at: 發生時間
        resolved_at: 解除時間（None 表示進行中）
        status: 告警狀態（ACTIVE | RESOLVED）
    """

    # === 唯一識別 ===
    alarm_key: str

    # === 告警來源 ===
    device_id: str
    alarm_type: AlarmType
    alarm_code: str = ""

    # === 告警資訊 ===
    name: str = ""
    level: AlarmLevel = AlarmLevel.INFO
    description: str = ""

    # === 時間戳記 ===
    occurred_at: datetime | None = None
    resolved_at: datetime | None = None

    # === 狀態 ===
    status: AlarmStatus = AlarmStatus.ACTIVE

    def to_document(self) -> dict[str, Any]:
        """
        轉換為 MongoDB document

        將 dataclass 轉換為可直接寫入 MongoDB 的 dict 格式。
        Enum 欄位會自動轉換為其 value 字串。

        Returns:
            dict[str, Any]: MongoDB document
        """
        doc = asdict(self)
        doc["alarm_type"] = self.alarm_type.value
        doc["level"] = self.level.value
        doc["status"] = self.status.value
        return doc

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> AlarmRecord:
        """
        從 MongoDB document 建立 AlarmRecord

        將 MongoDB document 反序列化為 AlarmRecord 物件。
        自動處理 _id 移除與 Enum 欄位的轉換。

        Args:
            doc: MongoDB document

        Returns:
            AlarmRecord: 告警記錄物件
        """
        doc = doc.copy()
        doc.pop("_id", None)
        doc["alarm_type"] = AlarmType(doc["alarm_type"])
        doc["level"] = AlarmLevel(doc["level"])
        doc["status"] = AlarmStatus(doc["status"])
        return cls(**doc)

    @staticmethod
    def make_key(device_id: str, alarm_type: AlarmType, alarm_code: str) -> str:
        """
        生成告警業務唯一鍵

        用於識別同一設備的同一類型告警，避免重複寫入。
        格式："<device_id>:<alarm_type>:<alarm_code>"

        Args:
            device_id: 設備識別碼
            alarm_type: 告警類型
            alarm_code: 告警代碼

        Returns:
            str: 告警唯一鍵
        """
        return f"{device_id}:{alarm_type.value}:{alarm_code}"
