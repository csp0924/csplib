# =============== Equipment Alarm - Definition ===============
#
# 告警定義
#
# 提供告警的基礎定義與等級

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class AlarmLevel(IntEnum):
    """
    告警等級

    Attributes:
        INFO: 信息告警
        WARNING: 警告告警 (不影響系統運作)
        ALARM: 重大告警 (影響系統運作)
    """

    INFO = 1
    WARNING = 2
    ALARM = 3


@dataclass(frozen=True)
class HysteresisConfig:
    """
    遲滯設定 - 避免邊緣觸發

    Attributes:
        activate_threshold: 連續 N 次觸發才啟用告警
        clear_threshold: 連續 N 次解除才清除告警
    """

    activate_threshold: int = 1
    clear_threshold: int = 1

    def __post_init__(self) -> None:
        if self.activate_threshold < 1:
            raise ValueError(f"activate_threshold 必須 >= 1，收到: {self.activate_threshold}")
        if self.clear_threshold < 1:
            raise ValueError(f"clear_threshold 必須 >= 1，收到: {self.clear_threshold}")


# 預設無遲滯
NO_HYSTERESIS = HysteresisConfig(activate_threshold=1, clear_threshold=1)


@dataclass(frozen=True)
class AlarmDefinition:
    """
    告警定義

    Attributes:
        code: 告警代碼（唯一識別）
        name: 告警名稱
        level: 告警等級
        hysteresis: 遲滯設定
        description: 詳細描述

    使用範例：
        AlarmDefinition(
            code="OVER_TEMP",
            name="溫度過高",
            level=AlarmLevel.WARNING,
            hysteresis=HysteresisConfig(activate_threshold=3, clear_threshold=5),
        )
    """

    code: str
    name: str
    level: AlarmLevel = AlarmLevel.ALARM
    hysteresis: HysteresisConfig = NO_HYSTERESIS
    description: str = ""

    def __hash__(self) -> int:
        return hash(self.code)


__all__ = [
    "AlarmDefinition",
    "AlarmLevel",
    "HysteresisConfig",
    "NO_HYSTERESIS",
]
