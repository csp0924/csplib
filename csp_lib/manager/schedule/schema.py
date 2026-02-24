# =============== Manager Schedule - Schema ===============
#
# 排程規則資料結構定義
#
# 提供排程系統的核心資料模型：
#   - ScheduleType: 排程類型枚舉（單次/每日/每週）
#   - StrategyType: 策略類型枚舉
#   - ScheduleRule: 排程規則資料類別（MongoDB Document）

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class ScheduleType(str, Enum):
    """
    排程類型枚舉

    Values:
        ONCE: 單次排程（指定日期範圍）
        DAILY: 每日排程（每天重複）
        WEEKLY: 每週排程（指定星期幾）
    """

    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


class StrategyType(str, Enum):
    """
    策略類型枚舉

    Values:
        PQ: 固定功率模式
        PV_SMOOTH: PV 平滑模式
        QV: 電壓無功控制
        FP: 頻率功率控制
        ISLAND: 離網模式
        BYPASS: 旁路模式
        STOP: 停止模式
    """

    PQ = "pq"
    PV_SMOOTH = "pv_smooth"
    QV = "qv"
    FP = "fp"
    ISLAND = "island"
    BYPASS = "bypass"
    STOP = "stop"


@dataclass
class ScheduleRule:
    """
    排程規則資料類別

    對應 MongoDB Document，用於儲存單筆排程規則的完整資訊。

    Attributes:
        name: 規則名稱
        site_id: 站點識別碼
        schedule_type: 排程類型（ONCE/DAILY/WEEKLY）
        strategy_type: 策略類型
        strategy_config: 策略配置字典
        start_time: 開始時間（"HH:MM" 格式）
        end_time: 結束時間（"HH:MM" 格式）
        priority: 優先順序（數字越大優先級越高）
        enabled: 是否啟用
        days_of_week: 每週排程的星期幾列表（0=Mon..6=Sun）
        start_date: 單次排程的開始日期
        end_date: 單次排程的結束日期
    """

    name: str
    site_id: str
    schedule_type: ScheduleType
    strategy_type: StrategyType
    strategy_config: dict[str, Any] = field(default_factory=dict)
    start_time: str = "00:00"
    end_time: str = "23:59"
    priority: int = 0
    enabled: bool = True
    days_of_week: list[int] = field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None

    def to_document(self) -> dict[str, Any]:
        """
        轉換為 MongoDB document

        Enum 欄位轉換為 value 字串，date 欄位轉換為 ISO 字串。

        Returns:
            dict[str, Any]: MongoDB document
        """
        doc: dict[str, Any] = {
            "name": self.name,
            "site_id": self.site_id,
            "type": self.schedule_type.value,
            "strategy_type": self.strategy_type.value,
            "strategy_config": self.strategy_config,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "priority": self.priority,
            "enabled": self.enabled,
            "days_of_week": self.days_of_week,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
        }
        return doc

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> ScheduleRule:
        """
        從 MongoDB document 建立 ScheduleRule

        自動處理 _id 移除、Enum 轉換、日期解析。

        Args:
            doc: MongoDB document

        Returns:
            ScheduleRule: 排程規則物件
        """
        doc = doc.copy()
        doc.pop("_id", None)

        # DB field "type" -> Python field "schedule_type"
        schedule_type_value = doc.pop("type")

        # 解析 date 欄位
        start_date = None
        if doc.get("start_date"):
            start_date = date.fromisoformat(doc["start_date"])

        end_date = None
        if doc.get("end_date"):
            end_date = date.fromisoformat(doc["end_date"])

        return cls(
            name=doc["name"],
            site_id=doc["site_id"],
            schedule_type=ScheduleType(schedule_type_value),
            strategy_type=StrategyType(doc["strategy_type"]),
            strategy_config=doc.get("strategy_config", {}),
            start_time=doc.get("start_time", "00:00"),
            end_time=doc.get("end_time", "23:59"),
            priority=doc.get("priority", 0),
            enabled=doc.get("enabled", True),
            days_of_week=doc.get("days_of_week", []),
            start_date=start_date,
            end_date=end_date,
        )


__all__ = [
    "ScheduleRule",
    "ScheduleType",
    "StrategyType",
]
