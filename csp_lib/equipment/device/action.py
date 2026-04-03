# =============== Equipment Device - Action ===============
#
# DO 動作抽象
#
# DOMode: 動作模式（PULSE/SUSTAINED/TOGGLE）
# DOActionConfig: 動作配置 frozen dataclass
# Actionable: 統一動作介面 Protocol

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from csp_lib.equipment.transport import WriteResult


class DOMode(str, Enum):
    """DO 動作模式

    Attributes:
        PULSE: 寫 on -> 延遲 -> 寫 off
        SUSTAINED: 寫 on，直到手動 off
        TOGGLE: 讀取當前值，寫反向
    """

    PULSE = "pulse"
    SUSTAINED = "sustained"
    TOGGLE = "toggle"


@dataclass(frozen=True, slots=True)
class DOActionConfig:
    """DO 動作配置

    Attributes:
        point_name: 對應的 WritePoint 名稱
        label: 動作語義標籤（如 "trip", "reset", "contactor_on"）
        mode: 動作模式
        pulse_duration: PULSE 模式的持續時間（秒）
        on_value: 啟動值
        off_value: 關閉值
    """

    point_name: str
    label: str
    mode: DOMode = DOMode.SUSTAINED
    pulse_duration: float = 0.5
    on_value: int = 1
    off_value: int = 0

    def __post_init__(self) -> None:
        if self.mode == DOMode.PULSE and self.pulse_duration <= 0:
            raise ValueError("pulse_duration must be positive for PULSE mode")


@runtime_checkable
class Actionable(Protocol):
    """設備 DO 動作介面

    實作此 Protocol 的設備支援結構化的 DO 動作控制。
    GUI/API/SCADA 可透過 available_do_actions 發現可用動作，
    透過 execute_do_action 統一調用。
    """

    @property
    def available_do_actions(self) -> list[DOActionConfig]: ...

    async def execute_do_action(self, label: str, *, turn_off: bool = False) -> WriteResult: ...


__all__ = ["DOMode", "DOActionConfig", "Actionable"]
