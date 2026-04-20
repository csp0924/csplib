---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
updated: 2026-04-20
version: ">=0.9.0"

---

# Import 路徑

各模組的主要 import 路徑總覽，依模組分類整理。

---

## Core (`csp_lib.core`)

```python
from csp_lib.core import (
    # Logging（基本 API）
    get_logger,
    set_level,
    configure_logging,
    add_file_sink,                # v0.7.0
    logger,
    DEFAULT_FORMAT,               # v0.7.0
    # Logging（進階元件，v0.7.0）
    LogFilter,
    SinkManager,
    SinkInfo,
    FileSinkConfig,
    LogContext,
    LogCapture,
    CapturedRecord,
    RemoteLevelSource,
    AsyncSinkAdapter,
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
    # NO_CHANGE sentinel（v0.8.0）
    NoChange, NO_CHANGE, is_no_change,
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
    # 心跳配置與 Protocol（v0.8.1）
    HeartbeatConfig,                          # v0.8.1 — 結構化心跳配置
    HeartbeatValueGenerator,                  # v0.8.1 — 值產生器 Protocol
    ToggleGenerator,                          # v0.8.1
    IncrementGenerator,                       # v0.8.1
    ConstantGenerator,                        # v0.8.1
    HeartbeatTarget,                          # v0.8.1 — 寫入目標 Protocol
    DeviceHeartbeatTarget,                    # v0.8.1
    # 命令刷新（v0.8.1）
    CommandRefreshService,                    # v0.8.1 — reconciler 服務
    CommandRefreshConfig,                     # v0.8.1 — reconciler 配置
    # Reconciler Protocol（v0.9.0）
    Reconciler,                               # v0.9.0 — @runtime_checkable Reconciler Protocol
    ReconcilerStatus,                         # v0.9.0 — reconcile 執行狀態 frozen dataclass
    # TypeRegistry（v0.9.0）
    TypeRegistry,                             # v0.9.0 — Generic[T] kind → class 映射表
    device_type_registry,                     # v0.9.0 — 全域設備型別 singleton
    strategy_type_registry,                   # v0.9.0 — 全域策略型別 singleton
    register_device_type,                     # v0.9.0 — @register_device_type("kind") decorator
    register_strategy_type,                   # v0.9.0 — @register_strategy_type("kind") decorator
    # Site Manifest（v0.9.0）
    SiteManifest,                             # v0.9.0 — 站點宣告式配置 frozen dataclass
    ManifestMetadata,                         # v0.9.0 — metadata 段落 frozen dataclass
    SiteSpec,                                 # v0.9.0 — spec 段落 frozen dataclass
    DeviceSpec,                               # v0.9.0 — 單一設備規格 frozen dataclass
    StrategySpec,                             # v0.9.0 — 單一策略規格 frozen dataclass
    ReconcilerSpec,                           # v0.9.0 — 單一 reconciler 規格 frozen dataclass
    load_manifest,                            # v0.9.0 — 載入 YAML/dict 回傳 SiteManifest
    # ManifestBinder（v0.9.0）
    BoundDeviceSpec,                          # v0.9.0 — 繫結後的設備規格 frozen dataclass
    BoundStrategySpec,                        # v0.9.0 — 繫結後的策略規格 frozen dataclass
    BoundReconcilerSpec,                      # v0.9.0 — 繫結後的 reconciler 規格 frozen dataclass
    ManifestBindResult,                       # v0.9.0 — apply_manifest_to_builder 回傳結果
    apply_manifest_to_builder,                # v0.9.0 — 把 SiteManifest 繫結到 Builder
    # SetpointDriftReconciler（v0.9.0）
    DriftTolerance,                           # v0.9.0 — setpoint drift 容忍範圍 frozen dataclass
    SetpointDriftReconciler,                  # v0.9.0 — 偵測並修正 setpoint drift 的 Reconciler
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

### 型別別名（直接從子模組 import）

```python
# v0.8.2 — 型別別名未包含在頂層 csp_lib.integration 的 __all__
from csp_lib.integration.registry import StatusChangeCallback   # Callable[[str, bool], None]
from csp_lib.integration.distributor import SOCSource           # Callable[[DeviceSnapshot], float | None]
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
    # 本地緩衝（v0.8.2）
    LocalBufferedUploader,
    LocalBufferConfig,
    LocalBufferStore,          # v0.8.2 — backend-agnostic Protocol（@runtime_checkable）
    BufferedRow,               # v0.8.2 — fetch_pending 回傳的 frozen dataclass
    SqliteBufferStore,         # v0.8.2 — aiosqlite 實作，需 csp_lib[local-buffer]
    MongoBufferStore,          # v0.8.2 — 本地 mongod 實作，已含於 csp_lib[mongo]
)
```

### 本地緩衝（Local Buffer，v0.8.2）

`LocalBufferedUploader` 本身只需 `csp_lib[mongo]`；backend 視部署場景選擇：

```bash
uv pip install 'csp0924_lib[mongo]'               # MongoBufferStore（本地 mongod backend）
uv pip install 'csp0924_lib[local-buffer]'        # SqliteBufferStore（aiosqlite）
uv pip install 'csp0924_lib[mongo,local-buffer]'  # 兩種 backend 都可用
```

```python
# 完整用法（SqliteBufferStore backend）
from csp_lib.mongo import (
    LocalBufferedUploader,     # v0.8.2 — 本地緩衝 + 背景 replay
    LocalBufferConfig,         # v0.8.2 — replay / cleanup 行為配置（不含 db_path）
    LocalBufferStore,          # v0.8.2 — @runtime_checkable Protocol
    BufferedRow,               # v0.8.2 — 單筆資料快照 frozen dataclass
    SqliteBufferStore,         # v0.8.2 — aiosqlite WAL 實作，需 csp_lib[local-buffer]
    MongoBufferStore,          # v0.8.2 — 本地 mongod 實作，已含於 csp_lib[mongo]
)

# 或從子模組 import（等價）
from csp_lib.mongo.local_buffer import (
    LocalBufferedUploader,
    LocalBufferConfig,
    LocalBufferStore,
    BufferedRow,
    SqliteBufferStore,
    MongoBufferStore,          # v0.8.2
)
```

> [!note] v0.8.2 extras 異動
> `[mongo]` 已瘦身為純 `motor>=3.3.0`；`aiosqlite` 移至獨立 `[local-buffer]` extra。
> 詳見 [[LocalBufferedUploader#安裝需求]]。

---

## Redis (`csp_lib.redis`)

需安裝：`pip install csp0924_lib[redis]`

```python
from csp_lib.redis import (
    RedisClient,
    RedisConfig,
    TLSConfig,
    RedisLogLevelSource,          # v0.7.0 — RemoteLevelSource 的 Redis 實作
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

## Alarm (`csp_lib.alarm`，v0.8.2)

```python
from csp_lib.alarm import (
    AlarmAggregator,            # OR 聚合器
    WatchdogProtocol,           # Watchdog 結構化協定（@runtime_checkable）
    AlarmChangeCallback,        # Callable[[bool], None] 型別別名
)

# 需安裝：pip install "csp0924_lib[redis]"
from csp_lib.alarm import (
    RedisAlarmPublisher,        # aggregator.on_change → Redis publish
    RedisAlarmSource,           # Redis subscribe → aggregator.mark_source
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
    RegisterNotWritableError,          # v0.7.3 SEC-006
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
    # Registry 聚合同步（v0.8.2）
    RegistryAggregatingSource,         # v0.8.2 — DeviceRegistry trait 聚合寫入 register
    RegisterAggregateMapping,          # v0.8.2 — 聚合映射 frozen dataclass
    AggregateFunc,                     # v0.8.2 — AVERAGE / SUM / MIN / MAX
    AggregateCallable,                 # v0.8.2 — Callable[[list[float]], float] 型別別名
    # HeartbeatTarget 實作（v0.8.1）
    GatewayRegisterHeartbeatTarget,    # v0.8.1 — 對 ModbusGatewayServer register 寫心跳值
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
