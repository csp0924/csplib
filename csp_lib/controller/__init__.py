# =============== Controller Module ===============
#
# 控制器模組頂層匯出
#
# 提供便捷的 import 路徑：
#   from csp_lib.controller import Strategy, Command, StrategyExecutor

from .calibration import FFCalibrationConfig, FFCalibrationStrategy
from .compensator import PowerCompensator, PowerCompensatorConfig
from .core import (
    Command,
    CommandProcessor,
    ConfigMixin,
    ExecutionConfig,
    ExecutionMode,
    Strategy,
    StrategyContext,
    SystemBase,
)
from .discovery import ENTRY_POINT_GROUP, StrategyDescriptor, discover_strategies
from .executor import ComputeOffloader, StrategyExecutor
from .protocol import GridControllerBase, GridControllerProtocol
from .services import PVDataService
from .strategies import (
    BypassStrategy,
    DroopConfig,
    DroopStrategy,
    FPConfig,
    FPStrategy,
    IslandModeConfig,
    IslandModeStrategy,
    LoadCircuitProtocol,
    LoadSheddingConfig,
    LoadSheddingStrategy,
    PQModeConfig,
    PQModeStrategy,
    PVSmoothConfig,
    PVSmoothStrategy,
    QVConfig,
    QVStrategy,
    RampStopStrategy,
    RelayProtocol,
    RemainingTimeCondition,
    ScheduleStrategy,
    ShedCondition,
    ShedStage,
    StopStrategy,
    ThresholdCondition,
)
from .system import (
    AlarmStopOverride,
    CapacityConfig,
    CascadingStrategy,
    ContextKeyOverride,
    DynamicSOCProtection,
    EventDrivenOverride,
    GridLimitProtection,
    ModeDefinition,
    ModeManager,
    ModePriority,
    ProtectionGuard,
    ProtectionResult,
    ProtectionRule,
    RampStopProtection,
    ReversePowerProtection,
    ScheduleModeController,
    SOCProtection,
    SOCProtectionConfig,
    SwitchSource,
    SystemAlarmProtection,
)

__all__ = [
    # Calibration
    "FFCalibrationConfig",
    "FFCalibrationStrategy",
    # Compensator
    "PowerCompensator",
    "PowerCompensatorConfig",
    # Discovery
    "ENTRY_POINT_GROUP",
    "StrategyDescriptor",
    "discover_strategies",
    # Protocol
    "GridControllerBase",
    "GridControllerProtocol",
    # Core
    "Command",
    "CommandProcessor",
    "SystemBase",
    "ConfigMixin",
    "StrategyContext",
    "ExecutionMode",
    "ExecutionConfig",
    "Strategy",
    # Executor
    "ComputeOffloader",
    "StrategyExecutor",
    # Services
    "PVDataService",
    # Strategies
    "BypassStrategy",
    "DroopConfig",
    "DroopStrategy",
    "FPConfig",
    "FPStrategy",
    "IslandModeConfig",
    "IslandModeStrategy",
    "LoadCircuitProtocol",
    "LoadSheddingConfig",
    "LoadSheddingStrategy",
    "PQModeConfig",
    "PQModeStrategy",
    "PVSmoothConfig",
    "PVSmoothStrategy",
    "QVConfig",
    "QVStrategy",
    "RelayProtocol",
    "RampStopStrategy",
    "RemainingTimeCondition",
    "ScheduleStrategy",
    "ShedCondition",
    "ShedStage",
    "StopStrategy",
    "ThresholdCondition",
    # System
    "AlarmStopOverride",
    "CapacityConfig",
    "CascadingStrategy",
    "ContextKeyOverride",
    "DynamicSOCProtection",
    "EventDrivenOverride",
    "GridLimitProtection",
    "RampStopProtection",
    "ScheduleModeController",
    "SwitchSource",
    "ModePriority",
    "ModeDefinition",
    "ModeManager",
    "ProtectionRule",
    "SOCProtection",
    "SOCProtectionConfig",
    "ReversePowerProtection",
    "SystemAlarmProtection",
    "ProtectionResult",
    "ProtectionGuard",
]
