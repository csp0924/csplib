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
    InMemoryAlarmRepository,
    MongoAlarmRepository,
)
from .base import AsyncRepository, BatchUploader, DeviceEventSubscriber
from .command import (
    ActionCommand,
    CommandAdapterConfig,
    CommandRecord,
    CommandRepository,
    CommandResult,
    CommandSource,
    CommandStatus,
    InMemoryCommandRepository,
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
from .in_memory_uploader import InMemoryBatchUploader, NullBatchUploader
from .schedule import (
    InMemoryScheduleRepository,
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
    "AsyncRepository",
    "BatchUploader",
    "DeviceEventSubscriber",
    # Alarm
    "AlarmPersistenceConfig",
    "AlarmPersistenceManager",
    "AlarmRepository",
    "InMemoryAlarmRepository",
    "MongoAlarmRepository",
    "AlarmRecord",
    "AlarmStatus",
    "AlarmType",
    # Command
    "ActionCommand",
    "CommandAdapterConfig",
    "CommandResult",
    "WriteCommandManager",
    "CommandRepository",
    "InMemoryCommandRepository",
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
    # In-Memory Uploader
    "InMemoryBatchUploader",
    "NullBatchUploader",
    # Schedule
    "InMemoryScheduleRepository",
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
