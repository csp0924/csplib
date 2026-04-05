---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
updated: 2026-04-05
version: ">=0.6.2"
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
    StrategyExecutionError,       # v0.5.0
    ProtectionError,              # v0.5.0
    DeviceRegistryError,          # v0.5.0
    # Health
    HealthStatus,
    HealthReport,
    HealthCheckable,
    # Resilience (v0.4.2)
    CircuitState,
    CircuitBreaker,
    RetryPolicy,
    # Runtime Parameters (v0.5.0)
    RuntimeParameters,
)
```

---

## CAN (`csp_lib.can`)

需安裝：`pip install csp0924_lib[can]`

```python
from csp_lib.can import (
    # 配置
    CANBusConfig,
    CANFrame,
    # 客戶端
    AsyncCANClientBase,
    PythonCANClient,
    # 例外
    CANError,
    CANConnectionError,
    CANTimeoutError,
    CANSendError,
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
    # 請求佇列（v0.4.2）
    RequestQueueConfig,
    RequestPriority,
    CircuitBreakerState,
    ModbusRequestQueue,
    # 客戶端
    AsyncModbusClientBase,
    PymodbusTcpClient,
    PymodbusRtuClient,
    SharedPymodbusTcpClient,
    # 例外
    ModbusError, ModbusEncodeError, ModbusDecodeError, ModbusConfigError,
    ModbusCircuitBreakerError, ModbusQueueFullError,
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
    # Modbus 設備
    AsyncModbusDevice,
    # CAN 設備（v0.4.2）
    AsyncCANDevice,
    CANRxFrameDefinition,
    # 協定（v0.4.2）
    DeviceProtocol,
    # 配置
    DeviceConfig,
    # DO 動作（v0.5.0）
    DOMode,
    DOActionConfig,
    Actionable,
    # Capability（v0.4.2 能力綁定系統）
    Capability,
    CapabilityBinding,
    HEARTBEAT,
    ACTIVE_POWER_CONTROL,
    REACTIVE_POWER_CONTROL,
    SWITCHABLE,
    LOAD_SHEDDABLE,
    MEASURABLE,
    FREQUENCY_MEASURABLE,
    VOLTAGE_MEASURABLE,
    SOC_READABLE,
    # Mixins
    AlarmMixin,
    WriteMixin,
    # EventBridge（v0.4.2）
    AggregateCondition,
    EventBridge,
    # 事件
    DeviceEventEmitter,
    AsyncHandler,
    ConnectedPayload,
    ValueChangePayload,
    DisconnectPayload,
    ReadCompletePayload,
    ReadErrorPayload,
    WriteCompletePayload,
    WriteErrorPayload,
    DeviceAlarmPayload,
    # 事件（v0.4.2 新增）
    ReconfiguredPayload,
    RestartedPayload,
    PointToggledPayload,
    # 動態點位管理（v0.4.2）
    PointInfo,
    ReconfigureSpec,
    # 事件常數
    EVENT_CONNECTED, EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE, EVENT_READ_ERROR,
    EVENT_VALUE_CHANGE,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CLEARED,
    EVENT_WRITE_COMPLETE, EVENT_WRITE_ERROR,
    EVENT_RECONFIGURED, EVENT_RESTARTED, EVENT_POINT_TOGGLED,
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

### Template（v0.5.2）

```python
from csp_lib.equipment.template import (
    EquipmentTemplate,
    PointOverride,
    DeviceFactory,
)
```

---

## Controller (`csp_lib.controller`)

```python
from csp_lib.controller import (
    # 核心
    Command, SystemBase, StrategyContext,
    Strategy, ExecutionConfig, ExecutionMode, ConfigMixin,
    # 命令處理管線（v0.5.1）
    CommandProcessor,
    # 校準（v0.5.1）
    FFCalibrationStrategy, FFCalibrationConfig,
    # 補償器（v0.5.1）
    PowerCompensator, PowerCompensatorConfig,
    # 執行器
    StrategyExecutor, ComputeOffloader,
    # 服務
    PVDataService,
    # 協議
    GridControllerProtocol, GridControllerBase,
    # 策略
    PQModeStrategy, PQModeConfig,
    PVSmoothStrategy, PVSmoothConfig,
    QVStrategy, QVConfig,
    FPStrategy, FPConfig,
    DroopStrategy, DroopConfig,              # v0.5.0
    RampStopStrategy,                         # v0.5.0
    IslandModeStrategy, IslandModeConfig, RelayProtocol,
    BypassStrategy, StopStrategy, ScheduleStrategy,
    # 負載卸載策略（v0.4.2）
    LoadSheddingStrategy, LoadSheddingConfig,
    LoadCircuitProtocol, ShedCondition,
    ShedStage, ThresholdCondition, RemainingTimeCondition,
    # 系統管理
    ModeManager, ModeDefinition, ModePriority, SwitchSource,
    ProtectionGuard, ProtectionRule, ProtectionResult,
    SOCProtection, SOCProtectionConfig,
    DynamicSOCProtection,                     # v0.5.0
    GridLimitProtection,                      # v0.5.0
    RampStopProtection,                       # v0.5.0
    ReversePowerProtection, SystemAlarmProtection,
    CascadingStrategy, CapacityConfig,
    # 事件驅動覆蓋（v0.4.2）
    EventDrivenOverride, AlarmStopOverride, ContextKeyOverride,
    # 排程模式控制協定（v0.4.2）
    ScheduleModeController,
    # 策略發現（v0.4.2）
    ENTRY_POINT_GROUP, StrategyDescriptor, discover_strategies,
)
```

---

## Manager (`csp_lib.manager`)

```python
from csp_lib.manager import (
    # 基底
    AsyncRepository,
    BatchUploader,                            # v0.5.0
    DeviceEventSubscriber,
    # 告警
    AlarmPersistenceManager, AlarmPersistenceConfig,
    AlarmRepository, MongoAlarmRepository,
    AlarmRecord, AlarmStatus, AlarmType,
    # 命令
    WriteCommandManager,
    ActionCommand, CommandAdapterConfig,
    CommandRepository, MongoCommandRepository,
    WriteCommand, CommandRecord, CommandSource, CommandStatus,
    CommandResult, RedisCommandAdapter,
    # 資料
    DataUploadManager,
    # 設備
    DeviceManager, DeviceGroup,
    # 排程（v0.4.2）
    ScheduleService, ScheduleServiceConfig,
    ScheduleRepository, MongoScheduleRepository,
    ScheduleRule, ScheduleType,
    StrategyFactory, StrategyType,
    # 狀態
    StateSyncManager, StateSyncConfig,
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
    AggregateFunc,
    AggregationResult,                        # v0.5.0
    ContextMapping, CommandMapping, DataFeedMapping,
    HeartbeatMapping, HeartbeatMode,
    CapabilityContextMapping, CapabilityCommandMapping,
    CapabilityRequirement,                    # v0.5.0
    # 建構器
    ContextBuilder, apply_builtin_aggregate,
    CommandRouter,
    DeviceDataFeed,
    # 心跳服務（v0.4.2）
    HeartbeatService,
    # 功率分配器（v0.4.2）
    DeviceSnapshot,
    PowerDistributor,
    EqualDistributor,
    ProportionalDistributor,
    SOCBalancingDistributor,
    # 控制迴圈
    GridControlLoop, GridControlLoopConfig,
    # 系統控制器
    SystemController, SystemControllerConfig,
    # 群組管理
    GroupDefinition, GroupControllerManager,
    # 編排器
    SystemCommandOrchestrator, SystemCommand, CommandStep,
    StepCheck, StepResult, SystemCommandResult,
    # 分散式控制（v0.4.2）
    DistributedConfig, RemoteSiteConfig,
    DeviceStateSubscriber, RemoteCommandRouter,
    DistributedController, RemoteSiteRunner,
)
```

### Hierarchical Control（v0.6.0）

```python
from csp_lib.integration.hierarchical import (
    SubExecutorAgent,
    TransportAdapter,
    DispatchCommand,
    ExecutorStatus,
    StatusReport,
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

## Modbus Gateway（v0.6.0）

```python
from csp_lib.modbus_gateway import (
    # Errors
    GatewayError,
    RegisterConflictError,
    WriteRejectedError,
    # Config
    RegisterType,
    GatewayRegisterDef,
    WatchdogConfig,
    GatewayServerConfig,
    WriteRule,
    # Protocol
    WriteValidator,
    WriteHook,
    DataSyncSource,
    UpdateRegisterCallback,
    # Core
    GatewayRegisterMap,
    ModbusGatewayServer,
    # Watchdog
    CommunicationWatchdog,
    # Validators
    AddressWhitelistValidator,
    # Hooks
    RedisPublishHook,
    CallbackHook,
    StatePersistHook,
    # Sync Sources
    RedisSubscriptionSource,
    PollingCallbackSource,
)
```

---

## Modbus Server（v0.5.2）

```python
from csp_lib.modbus_server import (
    # Config
    ServerConfig,
    SimulatedDeviceConfig,
    SimulatedPoint,
    AlarmPointConfig,
    AlarmResetMode,
    ControllabilityMode,
    PCSSimConfig,
    PowerMeterSimConfig,
    SolarSimConfig,
    GeneratorSimConfig,
    LoadSimConfig,
    MicrogridConfig,
    DeviceLinkConfig,          # v0.6.2
    MeterAggregationConfig,    # v0.6.2
    BMSSimConfig,              # v0.6.2
    # Register
    RegisterBlock,
    # Server
    SimulationServer,
    SimulatorDataBlock,
    # Microgrid
    MicrogridSimulator,
    # Simulators
    BaseDeviceSimulator,
    PCSSimulator,
    PowerMeterSimulator,
    SolarSimulator,
    GeneratorSimulator,
    LoadSimulator,
    BMSSimulator,              # v0.6.2
    # Behaviors
    AlarmBehavior,
    CurveBehavior,
    NoiseBehavior,
    RampBehavior,
)

# default_bms_config 輔助函式（子模組 import）
from csp_lib.modbus_server.simulator.bms import default_bms_config
```

---

## Statistics（v0.6.0）

```python
from csp_lib.statistics import (
    # Config
    DeviceMeterType,
    MetricDefinition,
    PowerSumDefinition,
    StatisticsConfig,
    # Tracker
    IntervalRecord,
    IntervalAccumulator,
    DeviceEnergyTracker,
    # Engine
    PowerSumRecord,
    StatisticsEngine,
    # Manager（需要 csp_lib[mongo]）
    StatisticsManager,
)
```

---

## GUI（v0.5.2）

需安裝：`pip install csp0924_lib[gui]`

```python
from csp_lib.gui import (
    create_app,
    GUIConfig,
)
```

---

## 相關頁面

- [[_MOC Reference]] - 參考索引
- [[Quick Start]] - 快速入門
