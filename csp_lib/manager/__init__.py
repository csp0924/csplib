# =============== Manager ===============
#
# 管理器模組
#
# 提供各類管理器功能：
#   - alarm: 告警持久化管理
#   - command: 寫入指令管理
#   - data: 資料上傳管理
#   - device: 設備讀取管理
#   - state: 狀態同步管理
#   - unified: 統一設備管理器

from .alarm import (
    AlarmPersistenceConfig,
    AlarmPersistenceManager,
    AlarmRecord,
    AlarmRepository,
    AlarmStatus,
    AlarmType,
    MongoAlarmRepository,
)
from .base import DeviceEventSubscriber
from .command import (
    CommandAdapterConfig,
    CommandRecord,
    CommandRepository,
    CommandSource,
    CommandStatus,
    MongoCommandRepository,
    RedisCommandAdapter,
    WriteCommand,
    WriteCommandManager,
)
from .data import DataUploadManager
from .device import (
    DeviceGroup,
    DeviceManager,
)
from .schedule import (
    MongoScheduleRepository,
    ScheduleRepository,
    ScheduleRule,
    ScheduleService,
    ScheduleServiceConfig,
    ScheduleType,
    StrategyFactory,
    StrategyType,
)
from .state import StateSyncConfig, StateSyncManager
from .unified import UnifiedConfig, UnifiedDeviceManager

__all__ = [
    # Base
    "DeviceEventSubscriber",
    # Alarm
    "AlarmPersistenceConfig",
    "AlarmPersistenceManager",
    "AlarmRepository",
    "MongoAlarmRepository",
    "AlarmRecord",
    "AlarmStatus",
    "AlarmType",
    # Command
    "CommandAdapterConfig",
    "WriteCommandManager",
    "CommandRepository",
    "MongoCommandRepository",
    "WriteCommand",
    "CommandRecord",
    "CommandSource",
    "CommandStatus",
    "RedisCommandAdapter",
    # Data
    "DataUploadManager",
    # Device
    "DeviceGroup",
    "DeviceManager",
    # Schedule
    "MongoScheduleRepository",
    "ScheduleRepository",
    "ScheduleRule",
    "ScheduleService",
    "ScheduleServiceConfig",
    "ScheduleType",
    "StrategyFactory",
    "StrategyType",
    # State
    "StateSyncConfig",
    "StateSyncManager",
    # Unified
    "UnifiedConfig",
    "UnifiedDeviceManager",
]
