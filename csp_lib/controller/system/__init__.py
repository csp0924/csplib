# =============== System Controller Module ===============
#
# 系統控制器模組
#
# 模式管理與保護機制：
#   - ModeManager: 模式註冊、優先權切換
#   - ProtectionGuard: 保護規則鏈式套用

from .cascading import CapacityConfig, CascadingStrategy
from .dynamic_protection import DynamicSOCProtection, GridLimitProtection, RampStopProtection
from .event_override import AlarmStopOverride, ContextKeyOverride, EventDrivenOverride
from .mode import ModeDefinition, ModeManager, ModePriority, SwitchSource
from .protection import (
    ProtectionGuard,
    ProtectionResult,
    ProtectionRule,
    ReversePowerProtection,
    SOCProtection,
    SOCProtectionConfig,
    SystemAlarmProtection,
)
from .schedule_mode import ScheduleModeController

__all__ = [
    # Cascading
    "CapacityConfig",
    "CascadingStrategy",
    # Dynamic Protection
    "DynamicSOCProtection",
    "GridLimitProtection",
    "RampStopProtection",
    # Event Override
    "EventDrivenOverride",
    "AlarmStopOverride",
    "ContextKeyOverride",
    # Mode
    "SwitchSource",
    "ModePriority",
    "ModeDefinition",
    "ModeManager",
    # Schedule Mode
    "ScheduleModeController",
    # Protection
    "ProtectionRule",
    "SOCProtection",
    "SOCProtectionConfig",
    "ReversePowerProtection",
    "SystemAlarmProtection",
    "ProtectionResult",
    "ProtectionGuard",
]
