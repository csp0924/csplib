# =============== Context Module ===============
#
# 策略執行時上下文
# - StrategyContext: 執行時上下文

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from .command import Command, SystemBase

if TYPE_CHECKING:
    from csp_lib.core.runtime_params import RuntimeParameters


@dataclass
class StrategyContext:
    """
    策略執行時上下文 (唯讀)

    提供策略執行所需的外部狀態，由 Executor 注入。
    策略不應直接修改此物件。

    Attributes:
        last_command: 上一次執行的命令
        soc: 儲能系統 SOC (%)
        current_time: 當前時間
        extra: 額外資料 — 設備讀值（frequency, meter_power 等，由 ContextMapping 注入）
        params: 系統參數 — RuntimeParameters 引用（EMS 指令、保護設定等，由 SystemController 注入）
    """

    last_command: Command = field(default_factory=Command)
    soc: Optional[float] = None
    system_base: Optional[SystemBase] = None
    current_time: Optional[datetime] = None
    extra: dict[str, Any] = field(default_factory=dict)
    params: RuntimeParameters | None = None

    def percent_to_kw(self, p_percent: float) -> float:
        """將百分比轉換為 kW"""
        if self.system_base is None:
            raise ValueError("system_base is not set in StrategyContext")
        return p_percent * self.system_base.p_base / 100

    def percent_to_kvar(self, q_percent: float) -> float:
        """將百分比轉換為 kVar"""
        if self.system_base is None:
            raise ValueError("system_base is not set in StrategyContext")
        return q_percent * self.system_base.q_base / 100
