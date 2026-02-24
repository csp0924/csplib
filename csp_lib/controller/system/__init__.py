# =============== System Controller Module ===============
#
# 系統控制器模組
#
# 模式管理與保護機制：
#   - ModeManager: 模式註冊、優先權切換
#   - ProtectionGuard: 保護規則鏈式套用

from .cascading import CapacityConfig, CascadingStrategy
from .mode import ModeDefinition, ModeManager, ModePriority
from .protection import (
    ProtectionGuard,
    ProtectionResult,
    ProtectionRule,
    ReversePowerProtection,
    SOCProtection,
    SOCProtectionConfig,
    SystemAlarmProtection,
)

__all__ = [
    # Cascading
    "CapacityConfig",
    "CascadingStrategy",
    # Mode
    "ModePriority",
    "ModeDefinition",
    "ModeManager",
    # Protection
    "ProtectionRule",
    "SOCProtection",
    "SOCProtectionConfig",
    "ReversePowerProtection",
    "SystemAlarmProtection",
    "ProtectionResult",
    "ProtectionGuard",
]
