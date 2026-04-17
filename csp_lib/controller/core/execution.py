# =============== Execution Module ===============
#
# 策略執行模式與配置
# - ExecutionMode: 執行模式 (週期/觸發/混合)
# - ExecutionConfig: 執行配置

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class ExecutionMode(Enum):
    """
    策略執行模式

    - PERIODIC: 固定週期執行
    - TRIGGERED: 僅在外部觸發時執行
    - HYBRID: 週期執行，但可被提前觸發
    """

    PERIODIC = auto()
    TRIGGERED = auto()
    HYBRID = auto()


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    """
    策略執行配置

    Attributes:
        mode: 執行模式
        interval_seconds: 週期秒數（適用於 PERIODIC 和 HYBRID 模式）

            v0.8.0 起型別由 ``int`` 擴寬為 ``float``，支援次秒級週期（如 0.5s、0.1s）。
            既有傳整數字面值（如 ``interval_seconds=1``）完全相容，無需修改。
    """

    mode: ExecutionMode
    interval_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.mode != ExecutionMode.TRIGGERED and self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive for PERIODIC/HYBRID mode")


__all__ = ["ExecutionConfig", "ExecutionMode"]
