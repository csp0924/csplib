---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
---

# Import 路徑

各模組的主要 import 路徑總覽，依模組分類整理。

---

## Core (`csp_lib.core`)

```python
from csp_lib.core import (
    # Logging
    get_logger,
    set_level,
    configure_logging,
    logger,
    # Lifecycle
    AsyncLifecycleMixin,
    # Errors
    DeviceError,
    DeviceConnectionError,
    CommunicationError,
    AlarmError,
    ConfigurationError,
    # Health
    HealthStatus,
    HealthReport,
    HealthCheckable,
)
```

---

## Modbus (`csp_lib.modbus`)

需安裝：`pip install csp0924_lib[modbus]`

```python
from csp_lib.modbus import (
    # 資料型別
    Int16, UInt16, Int32, UInt32, Int64, UInt64,
    Float32, Float64,
    DynamicInt, DynamicUInt,
    ModbusString,
    ModbusDataType,
    # 列舉
    ByteOrder, RegisterOrder, Parity, FunctionCode,
    # 配置
    ModbusTcpConfig, ModbusRtuConfig,
    # 編解碼
    ModbusCodec,
    # 客戶端
    AsyncModbusClientBase,
    PymodbusTcpClient,
    PymodbusRtuClient,
    SharedPymodbusTcpClient,
    # 例外
    ModbusError, ModbusEncodeError, ModbusDecodeError, ModbusConfigError,
)
```

---

## Equipment (`csp_lib.equipment`)

### Core

```python
from csp_lib.equipment.core import (
    ReadPoint, WritePoint, PointMetadata,
    ProcessingPipeline, pipeline,
    ScaleTransform, RoundTransform, EnumMapTransform, ClampTransform,
    BoolTransform, BitExtractTransform, ByteExtractTransform,
    MultiFieldExtractTransform, InverseTransform, PowerFactorTransform,
    RangeValidator, EnumValidator, CompositeValidator,
)
```

### Device

```python
from csp_lib.equipment.device import (
    AsyncModbusDevice,
    DeviceConfig,
    DeviceEventEmitter,
)
```

### Alarm

```python
from csp_lib.equipment.alarm import (
    AlarmDefinition, AlarmLevel, HysteresisConfig,
    AlarmStateManager,
    BitMaskAlarmEvaluator, ThresholdAlarmEvaluator, TableAlarmEvaluator,
    ThresholdCondition, Operator,
)
```

### Transport

```python
from csp_lib.equipment.transport import (
    PointGrouper, GroupReader, ReadScheduler, ValidatedWriter,
    WriteStatus,
)
```

### Processing

```python
from csp_lib.equipment.processing import (
    CoilToBitmaskAggregator,
    ComputedValueAggregator,
    AggregatorPipeline,
)
```

### Simulation

```python
from csp_lib.equipment.simulation import (
    VirtualMeter, MeterReading, CurveRegistry,
)
```

---

## Controller (`csp_lib.controller`)

```python
from csp_lib.controller import (
    # 核心
    Command, SystemBase, StrategyContext,
    Strategy, ExecutionConfig, ExecutionMode, ConfigMixin,
    # 執行器
    StrategyExecutor,
    # 服務
    PVDataService,
    # 協議
    GridControllerProtocol, GridControllerBase,
    # 策略
    PQModeStrategy, PQModeConfig,
    PVSmoothStrategy, PVSmoothConfig,
    QVStrategy, QVConfig,
    FPStrategy, FPConfig,
    IslandModeStrategy, IslandModeConfig, RelayProtocol,
    BypassStrategy, StopStrategy, ScheduleStrategy,
    # 系統管理
    ModeManager, ModeDefinition, ModePriority,
    ProtectionGuard, ProtectionRule, ProtectionResult,
    SOCProtection, SOCProtectionConfig,
    ReversePowerProtection, SystemAlarmProtection,
    CascadingStrategy, CapacityConfig,
)
```

---

## Manager (`csp_lib.manager`)

```python
from csp_lib.manager import (
    # 基底
    DeviceEventSubscriber,
    # 告警
    AlarmPersistenceManager, AlarmRepository, MongoAlarmRepository,
    AlarmRecord, AlarmStatus, AlarmType,
    # 命令
    WriteCommandManager, CommandRepository, MongoCommandRepository,
    WriteCommand, CommandRecord, CommandSource, CommandStatus,
    RedisCommandAdapter,
    # 資料
    DataUploadManager,
    # 設備
    DeviceManager, DeviceGroup,
    # 狀態
    StateSyncManager,
    # 統一
    UnifiedDeviceManager, UnifiedConfig,
)
```

---

## Integration (`csp_lib.integration`)

```python
from csp_lib.integration import (
    # 註冊
    DeviceRegistry,
    # Schema
    ContextMapping, CommandMapping, DataFeedMapping, AggregateFunc,
    # 建構器
    ContextBuilder, CommandRouter, DeviceDataFeed,
    # 控制迴圈
    GridControlLoop, GridControlLoopConfig,
    # 系統控制器
    SystemController, SystemControllerConfig,
    # 編排器
    SystemCommandOrchestrator, SystemCommand, CommandStep,
    StepCheck, StepResult, SystemCommandResult,
)
```

---

## MongoDB (`csp_lib.mongo`)

需安裝：`pip install csp0924_lib[mongo]`

```python
from csp_lib.mongo import (
    MongoConfig,
    create_mongo_client,
    MongoBatchUploader,
    UploaderConfig,
    WriteResult,
)
```

---

## Redis (`csp_lib.redis`)

需安裝：`pip install csp0924_lib[redis]`

```python
from csp_lib.redis import (
    RedisClient,
    RedisConfig,
    TLSConfig,
)
```

---

## Cluster (`csp_lib.cluster`)

需安裝：`pip install csp0924_lib[cluster]`

```python
from csp_lib.cluster import (
    ClusterConfig, EtcdConfig,
    ClusterController,
    LeaderElector,
    ClusterStatePublisher,
    ClusterStateSubscriber,
    VirtualContextBuilder,
)
```

---

## Monitor (`csp_lib.monitor`)

需安裝：`pip install csp0924_lib[monitor]`

```python
from csp_lib.monitor import (
    MonitorConfig, MetricThresholds,
    SystemMonitor,
    SystemMetricsCollector, SystemMetrics,
    SystemAlarmEvaluator,
    ModuleHealthCollector,
    RedisMonitorPublisher,
)
```

---

## Notification (`csp_lib.notification`)

```python
from csp_lib.notification import (
    Notification,
    NotificationEvent,
    NotificationChannel,
    NotificationDispatcher,
)
```

---

## 相關頁面

- [[_MOC Reference]] - 參考索引
- [[Quick Start]] - 快速入門
