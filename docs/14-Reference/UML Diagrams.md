# UML Class Diagrams — csp_lib

## 1. Architecture Overview

High-level view of the layered architecture with key classes and their relationships.

```mermaid
classDiagram
    direction TB

    namespace Core {
        class AsyncLifecycleMixin {
            +start()
            +stop()
            +__aenter__()
            +__aexit__()
        }
        class HealthCheckable {
            <<protocol>>
            +health() HealthReport
        }
        class DeviceError
        class ConfigurationError
    }

    namespace Modbus {
        class ModbusDataType {
            <<abstract>>
            +register_count int
            +encode() list~int~
            +decode() Any
        }
        class AsyncModbusClientBase {
            <<abstract>>
            +connect()
            +disconnect()
            +read_holding_registers()
            +write_multiple_registers()
        }
        class ModbusCodec {
            +encode()
            +decode()
        }
    }

    namespace Equipment {
        class AsyncModbusDevice {
            +device_id str
            +is_connected bool
            +latest_values dict
            +start()
            +stop()
            +read_once()
            +write_point()
            +on()
        }
        class DeviceConfig
        class ReadPoint
        class WritePoint
        class ProcessingPipeline
        class AlarmStateManager
        class DeviceEventEmitter
        class GroupReader
        class ReadScheduler
        class ValidatedWriter
    }

    namespace Controller {
        class Strategy {
            <<abstract>>
            +execute(ctx) Command
            +on_activate()
            +on_deactivate()
        }
        class StrategyExecutor {
            +set_strategy()
            +run()
            +stop()
            +trigger()
        }
        class ModeManager {
            +register()
            +set_base_mode()
            +push_override()
            +pop_override()
            +get_active_strategy()
        }
        class ProtectionGuard {
            +apply(cmd, ctx) Command
        }
        class Command {
            +p_target float
            +q_target float
        }
        class StrategyContext {
            +soc float
            +last_command Command
            +system_base SystemBase
        }
    }

    namespace Manager {
        class UnifiedDeviceManager {
            +register_device()
            +register_group()
        }
        class DeviceManager {
            +register()
            +register_group()
        }
        class AlarmPersistenceManager
        class WriteCommandManager
        class DataUploadManager
        class StateSyncManager
    }

    namespace Integration {
        class SystemController {
            +register_mode()
            +set_base_mode()
            +push_override()
            +pop_override()
            +health()
        }
        class DeviceRegistry {
            +register()
            +get_device()
            +get_devices_by_trait()
        }
        class ContextBuilder {
            +build() StrategyContext
        }
        class CommandRouter {
            +route(cmd)
        }
    }

    namespace Storage {
        class MongoClient
        class MongoBatchUploader
        class RedisClient
    }

    %% Core inheritance
    AsyncModbusDevice ..|> HealthCheckable
    DeviceManager --|> AsyncLifecycleMixin
    UnifiedDeviceManager --|> AsyncLifecycleMixin
    SystemController --|> AsyncLifecycleMixin

    %% Equipment composition
    AsyncModbusDevice *-- DeviceConfig
    AsyncModbusDevice *-- AsyncModbusClientBase
    AsyncModbusDevice *-- GroupReader
    AsyncModbusDevice *-- ReadScheduler
    AsyncModbusDevice *-- ValidatedWriter
    AsyncModbusDevice *-- AlarmStateManager
    AsyncModbusDevice *-- DeviceEventEmitter
    AsyncModbusDevice o-- ReadPoint
    AsyncModbusDevice o-- WritePoint

    ReadPoint *-- ProcessingPipeline
    GroupReader --> AsyncModbusClientBase
    GroupReader --> ModbusCodec

    %% Controller composition
    StrategyExecutor o-- Strategy
    StrategyExecutor --> StrategyContext
    StrategyExecutor --> Command
    ModeManager o-- ModeDefinition
    ProtectionGuard o-- ProtectionRule

    %% Manager composition
    UnifiedDeviceManager *-- DeviceManager
    UnifiedDeviceManager o-- AlarmPersistenceManager
    UnifiedDeviceManager o-- WriteCommandManager
    UnifiedDeviceManager o-- DataUploadManager
    UnifiedDeviceManager o-- StateSyncManager
    DeviceManager o-- AsyncModbusDevice

    %% Integration composition
    SystemController *-- ModeManager
    SystemController *-- ProtectionGuard
    SystemController *-- ContextBuilder
    SystemController *-- CommandRouter
    SystemController *-- StrategyExecutor
    SystemController *-- DeviceRegistry
    ContextBuilder --> DeviceRegistry
    CommandRouter --> DeviceRegistry
    ContextBuilder ..> StrategyContext : creates
    CommandRouter ..> Command : consumes

    %% Storage usage
    AlarmPersistenceManager --> MongoClient
    DataUploadManager --> MongoBatchUploader
    StateSyncManager --> RedisClient
```

---

## 2. Core Layer

```mermaid
classDiagram
    direction TB

    class AsyncLifecycleMixin {
        -_started bool
        +start()
        +stop()
        #_on_start()*
        #_on_stop()*
        +__aenter__()
        +__aexit__()
    }

    class HealthStatus {
        <<enumeration>>
        HEALTHY
        DEGRADED
        UNHEALTHY
    }

    class HealthReport {
        <<frozen dataclass>>
        +status HealthStatus
        +component str
        +message str
        +details dict
        +children list~HealthReport~
    }

    class HealthCheckable {
        <<protocol>>
        +health() HealthReport
    }

    class DeviceError {
        +device_id str
        +message str
    }
    class DeviceConnectionError
    class CommunicationError
    class AlarmError {
        +alarm_code str
    }
    class ConfigurationError

    HealthReport --> HealthStatus
    HealthReport o-- HealthReport : children
    HealthCheckable ..> HealthReport : returns

    DeviceConnectionError --|> DeviceError
    CommunicationError --|> DeviceError
    AlarmError --|> DeviceError
    ConfigurationError --|> Exception
```

---

## 3. Modbus Layer

```mermaid
classDiagram
    direction TB

    class ByteOrder {
        <<enumeration>>
        BIG_ENDIAN
        LITTLE_ENDIAN
    }

    class RegisterOrder {
        <<enumeration>>
        HIGH_FIRST
        LOW_FIRST
    }

    class Parity {
        <<enumeration>>
        NONE
        EVEN
        ODD
    }

    class FunctionCode {
        <<IntEnum>>
        READ_COILS = 0x01
        READ_DISCRETE_INPUTS = 0x02
        READ_HOLDING_REGISTERS = 0x03
        READ_INPUT_REGISTERS = 0x04
        WRITE_SINGLE_COIL = 0x05
        WRITE_SINGLE_REGISTER = 0x06
        WRITE_MULTIPLE_COILS = 0x0F
        WRITE_MULTIPLE_REGISTERS = 0x10
    }

    class ModbusDataType {
        <<abstract>>
        +register_count* int
        +encode(value, byte_order, register_order)* list~int~
        +decode(registers, byte_order, register_order)* Any
    }
    class Int16
    class UInt16
    class Int32
    class UInt32
    class Int64
    class UInt64
    class Float32
    class Float64
    class ModbusString {
        +max_length int
    }
    class DynamicInt {
        +num_registers int
    }
    class DynamicUInt {
        +num_registers int
    }

    Int16 --|> ModbusDataType
    UInt16 --|> ModbusDataType
    Int32 --|> ModbusDataType
    UInt32 --|> ModbusDataType
    Int64 --|> ModbusDataType
    UInt64 --|> ModbusDataType
    Float32 --|> ModbusDataType
    Float64 --|> ModbusDataType
    ModbusString --|> ModbusDataType
    DynamicInt --|> ModbusDataType
    DynamicUInt --|> ModbusDataType

    class ModbusCodec {
        +encode(data_type, value, byte_order, register_order) list~int~
        +decode(data_type, registers, byte_order, register_order) Any
    }

    ModbusCodec --> ModbusDataType

    class AsyncModbusClientBase {
        <<abstract>>
        +connect()*
        +disconnect()*
        +is_connected()* bool
        +read_coils(address, count, unit)*
        +read_discrete_inputs(address, count, unit)*
        +read_holding_registers(address, count, unit)*
        +read_input_registers(address, count, unit)*
        +write_single_coil(address, value, unit)*
        +write_single_register(address, value, unit)*
        +write_multiple_coils(address, values, unit)*
        +write_multiple_registers(address, values, unit)*
    }

    class PymodbusTcpClient {
        -_config ModbusTcpConfig
        -_client AsyncModbusTcpClient
    }
    class PymodbusRtuClient {
        -_config ModbusRtuConfig
        -_client AsyncModbusSerialClient
    }
    class SharedPymodbusTcpClient {
        -_config ModbusTcpConfig
        -_lock asyncio.Lock
    }

    PymodbusTcpClient --|> AsyncModbusClientBase
    PymodbusRtuClient --|> AsyncModbusClientBase
    SharedPymodbusTcpClient --|> AsyncModbusClientBase

    class ModbusTcpConfig {
        <<frozen dataclass>>
        +host str
        +port int = 502
        +timeout float = 0.5
        +byte_order ByteOrder
        +register_order RegisterOrder
    }

    class ModbusRtuConfig {
        <<frozen dataclass>>
        +port str
        +baudrate int = 9600
        +parity Parity
        +stopbits int = 1
        +bytesize int = 8
        +timeout float = 0.5
        +byte_order ByteOrder
        +register_order RegisterOrder
    }

    PymodbusTcpClient --> ModbusTcpConfig
    PymodbusRtuClient --> ModbusRtuConfig
    SharedPymodbusTcpClient --> ModbusTcpConfig
    ModbusTcpConfig --> ByteOrder
    ModbusTcpConfig --> RegisterOrder
    ModbusRtuConfig --> ByteOrder
    ModbusRtuConfig --> RegisterOrder
    ModbusRtuConfig --> Parity

    class ModbusError
    class ModbusEncodeError
    class ModbusDecodeError
    class ModbusConfigError
    class ModbusCircuitBreakerError
    class ModbusQueueFullError

    ModbusEncodeError --|> ModbusError
    ModbusDecodeError --|> ModbusError
    ModbusConfigError --|> ModbusError
    ModbusCircuitBreakerError --|> ModbusError
    ModbusQueueFullError --|> ModbusError
```

---

## 4. Equipment Layer

### 4a. Points & Transforms

```mermaid
classDiagram
    direction TB

    class PointDefinition {
        <<frozen dataclass>>
        +name str
        +address int
        +data_type ModbusDataType
        +function_code FunctionCode
        +byte_order ByteOrder
        +register_order RegisterOrder
    }

    class ReadPoint {
        <<frozen dataclass>>
        +pipeline ProcessingPipeline?
        +read_group str
        +metadata PointMetadata?
    }

    class WritePoint {
        <<frozen dataclass>>
        +validator ValueValidator?
        +metadata PointMetadata?
    }

    class PointMetadata {
        <<frozen dataclass>>
        +unit str?
        +description str?
        +value_map dict~int, str~?
    }

    ReadPoint --|> PointDefinition
    WritePoint --|> PointDefinition
    ReadPoint --> PointMetadata
    WritePoint --> PointMetadata

    class TransformStep {
        <<protocol>>
        +apply(value) Any
    }

    class ScaleTransform {
        +magnitude float
        +offset float
        +apply(value) float
    }

    class RoundTransform {
        +decimals int
        +apply(value) float
    }

    class EnumMapTransform {
        +mapping dict~int, str~
        +default str
        +apply(value) str
    }

    class ClampTransform {
        +min_value float
        +max_value float
        +apply(value) float
    }

    class BitExtractTransform {
        +bit int
        +apply(value) int
    }

    class MultiFieldExtractTransform {
        +fields list
        +apply(value) dict
    }

    ScaleTransform ..|> TransformStep
    RoundTransform ..|> TransformStep
    EnumMapTransform ..|> TransformStep
    ClampTransform ..|> TransformStep
    BitExtractTransform ..|> TransformStep
    MultiFieldExtractTransform ..|> TransformStep

    class ProcessingPipeline {
        <<frozen dataclass>>
        +steps tuple~TransformStep~
        +process(raw_value) Any
    }

    ProcessingPipeline o-- TransformStep
    ReadPoint *-- ProcessingPipeline
```

### 4b. Alarm System

```mermaid
classDiagram
    direction TB

    class AlarmLevel {
        <<IntEnum>>
        INFO = 1
        WARNING = 2
        ALARM = 3
    }

    class HysteresisConfig {
        <<frozen dataclass>>
        +activate_threshold int = 1
        +clear_threshold int = 1
    }

    class AlarmDefinition {
        <<frozen dataclass>>
        +code str
        +name str
        +level AlarmLevel
        +hysteresis HysteresisConfig
        +description str
    }

    AlarmDefinition --> AlarmLevel
    AlarmDefinition --> HysteresisConfig

    class AlarmEvaluator {
        <<abstract>>
        +point_name str
        +evaluate(value) dict~str, bool~
        +get_alarms() list~AlarmDefinition~
    }

    class BitMaskAlarmEvaluator {
        +bit_alarms dict~int, AlarmDefinition~
    }
    class ThresholdAlarmEvaluator {
        +threshold float
        +above bool
    }
    class TableAlarmEvaluator {
        +table dict~int, AlarmDefinition~
    }

    BitMaskAlarmEvaluator --|> AlarmEvaluator
    ThresholdAlarmEvaluator --|> AlarmEvaluator
    TableAlarmEvaluator --|> AlarmEvaluator

    AlarmEvaluator o-- AlarmDefinition

    class AlarmEventType {
        <<enumeration>>
        TRIGGERED
        CLEARED
    }

    class AlarmEvent {
        +event_type AlarmEventType
        +alarm AlarmDefinition
        +timestamp datetime
    }

    AlarmEvent --> AlarmEventType
    AlarmEvent --> AlarmDefinition

    class AlarmState {
        +definition AlarmDefinition
        +is_active bool
        +activate_count int
        +clear_count int
        +activated_at datetime?
        +cleared_at datetime?
        +duration float?
        +update(is_triggered) AlarmEvent?
    }

    AlarmState --> AlarmDefinition
    AlarmState ..> AlarmEvent : creates

    class AlarmStateManager {
        -_states dict~str, AlarmState~
        +register_alarms(list~AlarmDefinition~)
        +evaluate(evaluator) list~AlarmEvent~
        +get_alarm_state(code) AlarmState
        +active_alarms list~AlarmState~
        +has_active_alarms bool
    }

    AlarmStateManager o-- AlarmState
    AlarmStateManager --> AlarmEvaluator
```

### 4c. Transport & Device

```mermaid
classDiagram
    direction TB

    class ReadGroup {
        <<frozen dataclass>>
        +function_code int
        +start_address int
        +count int
        +points tuple~ReadPoint~
    }

    class PointGrouper {
        +group(points) list~ReadGroup~
    }

    class ReadScheduler {
        +always_groups list~ReadGroup~
        +rotating_groups list~list~ReadGroup~~
        +get_next_groups() list~ReadGroup~
    }

    class GroupReader {
        -_client AsyncModbusClientBase
        -_codec ModbusCodec
        +read(group) dict~str, Any~
        +read_many(groups) dict~str, Any~
    }

    class WriteStatus {
        <<enumeration>>
        SUCCESS
        VALIDATION_FAILED
        WRITE_FAILED
        VERIFICATION_FAILED
    }

    class WriteResult {
        <<frozen dataclass>>
        +status WriteStatus
        +point_name str
        +value Any
        +error_message str
    }

    class ValidatedWriter {
        -_client AsyncModbusClientBase
        -_codec ModbusCodec
        +write(point, value, verify) WriteResult
    }

    WriteResult --> WriteStatus
    ValidatedWriter ..> WriteResult : creates

    PointGrouper ..> ReadGroup : creates
    ReadScheduler o-- ReadGroup
    GroupReader --> ReadGroup

    class DeviceConfig {
        <<frozen dataclass>>
        +device_id str
        +unit_id int = 1
        +address_offset int = 0
        +read_interval float = 1.0
        +reconnect_interval float = 5.0
        +disconnect_threshold int = 5
        +max_concurrent_reads int = 1
    }

    class Capability {
        <<frozen dataclass>>
        +name str
        +write_slots tuple~str~
        +read_slots tuple~str~
        +description str
    }

    class CapabilityBinding {
        <<frozen dataclass>>
        +capability Capability
        +point_map dict~str, str~
    }

    CapabilityBinding --> Capability

    class DeviceEventEmitter {
        -_handlers dict
        +on(event, handler) Callable
        +emit(event, payload)
    }

    class AsyncModbusDevice {
        -_config DeviceConfig
        -_client AsyncModbusClientBase
        -_scheduler ReadScheduler
        -_reader GroupReader
        -_writer ValidatedWriter
        -_alarm_manager AlarmStateManager
        -_evaluators list~AlarmEvaluator~
        -_capability_bindings dict~str, CapabilityBinding~
        -_emitter DeviceEventEmitter
        -_latest_values dict~str, Any~
        -_consecutive_failures int
        +device_id str
        +is_connected bool
        +is_responsive bool
        +is_protected bool
        +latest_values dict
        +start()
        +stop()
        +connect()
        +disconnect()
        +read_once() dict
        +read_loop()
        +write_point(name, value, verify) WriteResult
        +write_points(writes, verify) list~WriteResult~
        +on(event, handler)
        +action(action_name) Any
        +resolve_point(capability, slot) str
        +health() HealthReport
    }

    AsyncModbusDevice *-- DeviceConfig
    AsyncModbusDevice *-- ReadScheduler
    AsyncModbusDevice *-- GroupReader
    AsyncModbusDevice *-- ValidatedWriter
    AsyncModbusDevice *-- AlarmStateManager
    AsyncModbusDevice o-- AlarmEvaluator
    AsyncModbusDevice o-- CapabilityBinding
    AsyncModbusDevice *-- DeviceEventEmitter
    AsyncModbusDevice ..> WriteResult
```

### 4d. Device Events

```mermaid
classDiagram
    direction TB

    class ConnectedPayload {
        <<frozen dataclass>>
        +device_id str
        +timestamp datetime
    }

    class DisconnectPayload {
        <<frozen dataclass>>
        +device_id str
        +reason str
        +consecutive_failures int
        +timestamp datetime
    }

    class ReadCompletePayload {
        <<frozen dataclass>>
        +device_id str
        +values dict~str, Any~
        +timestamp datetime
    }

    class ReadErrorPayload {
        <<frozen dataclass>>
        +device_id str
        +error str
        +consecutive_failures int
        +timestamp datetime
    }

    class ValueChangePayload {
        <<frozen dataclass>>
        +device_id str
        +point_name str
        +old_value Any
        +new_value Any
        +timestamp datetime
    }

    class DeviceAlarmPayload {
        <<frozen dataclass>>
        +device_id str
        +alarm_event AlarmEvent
    }

    class WriteCompletePayload {
        <<frozen dataclass>>
        +device_id str
        +point_name str
        +value Any
        +timestamp datetime
    }

    class WriteErrorPayload {
        <<frozen dataclass>>
        +device_id str
        +point_name str
        +value Any
        +error str
        +timestamp datetime
    }

    DeviceAlarmPayload --> AlarmEvent

    note for ConnectedPayload "EVENT_CONNECTED"
    note for DisconnectPayload "EVENT_DISCONNECTED"
    note for ReadCompletePayload "EVENT_READ_COMPLETE"
    note for ReadErrorPayload "EVENT_READ_ERROR"
    note for ValueChangePayload "EVENT_VALUE_CHANGE"
    note for DeviceAlarmPayload "EVENT_ALARM_TRIGGERED\nEVENT_ALARM_CLEARED"
    note for WriteCompletePayload "EVENT_WRITE_COMPLETE"
    note for WriteErrorPayload "EVENT_WRITE_ERROR"
```

---

## 5. Controller Layer

### 5a. Command & Strategy

```mermaid
classDiagram
    direction TB

    class Command {
        <<frozen dataclass>>
        +p_target float = 0.0
        +q_target float = 0.0
        +with_p(p) Command
        +with_q(q) Command
    }

    class SystemBase {
        <<frozen dataclass>>
        +p_base float = 0.0
        +q_base float = 0.0
        +percent_to_kw(pct) float
        +percent_to_kvar(pct) float
    }

    class StrategyContext {
        <<dataclass>>
        +last_command Command
        +soc float?
        +system_base SystemBase?
        +current_time datetime?
        +extra dict~str, Any~
        +percent_to_kw(pct) float
        +percent_to_kvar(pct) float
    }

    StrategyContext --> Command
    StrategyContext --> SystemBase

    class ExecutionMode {
        <<enumeration>>
        PERIODIC
        TRIGGERED
        HYBRID
    }

    class ExecutionConfig {
        <<frozen dataclass>>
        +mode ExecutionMode
        +interval_seconds int = 1
    }

    ExecutionConfig --> ExecutionMode

    class Strategy {
        <<abstract>>
        +execution_config* ExecutionConfig
        +suppress_heartbeat bool
        +execute(context)* Command
        +on_activate()
        +on_deactivate()
    }

    Strategy --> ExecutionConfig
    Strategy ..> Command : returns
    Strategy --> StrategyContext : uses

    class PQModeStrategy {
        +p float
        +q float
    }
    class PVSmoothStrategy
    class QVStrategy
    class FPStrategy
    class IslandStrategy
    class BypassStrategy
    class StopStrategy
    class ScheduleStrategy

    PQModeStrategy --|> Strategy
    PVSmoothStrategy --|> Strategy
    QVStrategy --|> Strategy
    FPStrategy --|> Strategy
    IslandStrategy --|> Strategy
    BypassStrategy --|> Strategy
    StopStrategy --|> Strategy
    ScheduleStrategy --|> Strategy
```

### 5b. Executor & Mode Management

```mermaid
classDiagram
    direction TB

    class StrategyExecutor {
        -_strategy Strategy?
        -_context_provider Callable
        -_on_command Callable?
        -_last_command Command
        -_is_running bool
        -_trigger_event asyncio.Event
        -_stop_event asyncio.Event
        +last_command Command
        +current_strategy Strategy?
        +is_running bool
        +set_context_provider(provider)
        +set_on_command(callback)
        +set_strategy(strategy)
        +run()
        +stop()
        +trigger()
    }

    StrategyExecutor o-- Strategy
    StrategyExecutor ..> Command

    class ModePriority {
        <<IntEnum>>
        SCHEDULE = 10
        MANUAL = 50
        PROTECTION = 100
    }

    class ModeDefinition {
        <<frozen dataclass>>
        +name str
        +strategy Strategy
        +priority int
        +description str
    }

    ModeDefinition --> Strategy
    ModeDefinition --> ModePriority

    class ModeManager {
        -_modes dict~str, ModeDefinition~
        -_base_mode_names list~str~
        -_override_names list~str~
        +on_strategy_change Callable?
        +register(name, strategy, priority, description)
        +unregister(name)
        +set_base_mode(name?)
        +get_base_mode() ModeDefinition?
        +push_override(name)
        +pop_override(name)
        +get_active_strategy() Strategy?
        +get_active_mode() ModeDefinition?
    }

    ModeManager o-- ModeDefinition
```

### 5c. Protection & Cascading

```mermaid
classDiagram
    direction TB

    class ProtectionRule {
        <<abstract>>
        +name* str
        +evaluate(command, context)* Command
        +is_triggered* bool
    }

    class SOCProtection {
        +soc_high float
        +soc_low float
        +warning_band float
        +name str
        +evaluate(command, context) Command
        +is_triggered bool
    }

    class ReversePowerProtection {
        +name str
        +evaluate(command, context) Command
        +is_triggered bool
    }

    class SystemAlarmProtection {
        +name str
        +evaluate(command, context) Command
        +is_triggered bool
    }

    SOCProtection --|> ProtectionRule
    ReversePowerProtection --|> ProtectionRule
    SystemAlarmProtection --|> ProtectionRule

    class ProtectionGuard {
        -_rules list~ProtectionRule~
        +apply(command, context) Command
        +health() HealthReport
    }

    ProtectionGuard o-- ProtectionRule

    class CapacityConfig {
        <<frozen dataclass>>
        +s_max_kva float
    }

    class CascadingStrategy {
        +layers list~Strategy~
        +capacity CapacityConfig
        +execute(context) Command
    }

    CascadingStrategy --|> Strategy
    CascadingStrategy o-- Strategy : layers
    CascadingStrategy --> CapacityConfig
```

---

## 6. Manager Layer

```mermaid
classDiagram
    direction TB

    class DeviceEventSubscriber {
        <<abstract>>
        -_unsubscribes dict~str, list~Callable~~
        +subscribe(device)
        +unsubscribe(device)
        #_register_events(device)* list~Callable~
        #_on_unsubscribe(device_id)
    }

    class DeviceGroup {
        +devices list~AsyncModbusDevice~
        +shared_client SharedPymodbusTcpClient
        +interval float
        +start()
        +stop()
    }

    class DeviceManager {
        -_standalone list~AsyncModbusDevice~
        -_groups list~DeviceGroup~
        +register(device)
        +register_group(devices, interval)
        +standalone_count int
        +group_count int
    }

    DeviceManager --|> AsyncLifecycleMixin
    DeviceManager o-- AsyncModbusDevice
    DeviceManager o-- DeviceGroup

    class AlarmRecord {
        <<dataclass>>
        +device_id str
        +code str
        +name str
        +level str
        +message str
        +created_at datetime
        +resolved_at datetime?
        +extra dict
    }

    class AlarmRepository {
        <<protocol>>
        +save(record) str
        +get_active(device_id) list~AlarmRecord~
        +clear_alarm(code, device_id)
    }

    class AlarmPersistenceManager {
        -_repository AlarmRepository
        -_dispatcher NotificationSender?
    }

    AlarmPersistenceManager --|> DeviceEventSubscriber
    AlarmPersistenceManager --> AlarmRepository
    AlarmRepository ..> AlarmRecord

    class WriteCommand {
        +device_id str
        +point_name str
        +value Any
        +source CommandSource
        +timestamp datetime
    }

    class CommandRepository {
        <<protocol>>
        +save(command) str
        +get_by_id(id) WriteCommand?
        +update_result(id, status, error)
    }

    class WriteCommandManager {
        -_repository CommandRepository
        -_devices dict~str, AsyncModbusDevice~
        +register_device(device)
        +unregister_device(device_id)
        +execute(command) WriteResult
    }

    WriteCommandManager --> CommandRepository
    WriteCommandManager --> AsyncModbusDevice

    class DataUploadManager {
        -_mongo_uploader MongoBatchUploader?
    }

    DataUploadManager --|> DeviceEventSubscriber
    DataUploadManager --> MongoBatchUploader

    class StateSyncManager {
        -_redis RedisClient
    }

    StateSyncManager --|> DeviceEventSubscriber
    StateSyncManager --> RedisClient

    class UnifiedConfig {
        +alarm_repository AlarmRepository?
        +command_repository CommandRepository?
        +mongo_uploader MongoBatchUploader?
        +redis_client RedisClient?
        +device_registry DeviceRegistry?
    }

    class UnifiedDeviceManager {
        +device_manager DeviceManager
        +alarm_manager AlarmPersistenceManager?
        +command_manager WriteCommandManager?
        +data_manager DataUploadManager?
        +state_manager StateSyncManager?
        +register_device(device)
        +register_group(devices, interval)
    }

    UnifiedDeviceManager --|> AsyncLifecycleMixin
    UnifiedDeviceManager *-- DeviceManager
    UnifiedDeviceManager o-- AlarmPersistenceManager
    UnifiedDeviceManager o-- WriteCommandManager
    UnifiedDeviceManager o-- DataUploadManager
    UnifiedDeviceManager o-- StateSyncManager
    UnifiedDeviceManager --> UnifiedConfig
```

---

## 7. Integration Layer

```mermaid
classDiagram
    direction TB

    class DeviceRegistry {
        -_devices dict~str, AsyncModbusDevice~
        -_device_traits dict~str, set~str~~
        -_trait_devices dict~str, set~str~~
        +register(device, traits)
        +unregister(device_id)
        +add_trait(device_id, trait)
        +remove_trait(device_id, trait)
        +get_device(device_id) AsyncModbusDevice?
        +get_devices_by_trait(trait) list~AsyncModbusDevice~
        +get_responsive_devices_by_trait(trait) list~AsyncModbusDevice~
    }

    DeviceRegistry o-- AsyncModbusDevice

    class AggregateFunc {
        <<enumeration>>
        AVERAGE
        SUM
        MIN
        MAX
        FIRST
    }

    class ContextMapping {
        <<frozen dataclass>>
        +point_name str
        +context_field str
        +device_id str?
        +trait str?
        +aggregate AggregateFunc
        +custom_aggregate Callable?
        +default Any
        +transform Callable?
    }

    ContextMapping --> AggregateFunc

    class CommandMapping {
        <<frozen dataclass>>
        +command_field str
        +point_name str
        +device_id str?
        +trait str?
        +transform Callable?
    }

    class HeartbeatMode {
        <<enumeration>>
        TOGGLE
        INCREMENT
        CONSTANT
    }

    class HeartbeatMapping {
        <<frozen dataclass>>
        +device_id str?
        +trait str?
        +point_name str
        +mode HeartbeatMode
        +value int = 0
        +max_value int = 1
    }

    HeartbeatMapping --> HeartbeatMode

    class ContextBuilder {
        -_registry DeviceRegistry
        -_mappings list~ContextMapping~
        -_system_base SystemBase?
        +build() StrategyContext
    }

    ContextBuilder --> DeviceRegistry
    ContextBuilder o-- ContextMapping
    ContextBuilder ..> StrategyContext : creates

    class CommandRouter {
        -_registry DeviceRegistry
        -_mappings list~CommandMapping~
        +route(command)
    }

    CommandRouter --> DeviceRegistry
    CommandRouter o-- CommandMapping
    CommandRouter --> Command

    class HeartbeatService {
        -_registry DeviceRegistry
        -_mappings list~HeartbeatMapping~
        +start()
        +stop()
        +pause()
        +resume()
    }

    HeartbeatService --> DeviceRegistry
    HeartbeatService o-- HeartbeatMapping

    class SystemControllerConfig {
        <<dataclass>>
        +context_mappings list~ContextMapping~
        +command_mappings list~CommandMapping~
        +system_base SystemBase?
        +protection_rules list~ProtectionRule~
        +auto_stop_on_alarm bool = True
        +capacity_kva float?
        +heartbeat_mappings list~HeartbeatMapping~
    }

    class SystemController {
        -_registry DeviceRegistry
        -_mode_manager ModeManager
        -_guard ProtectionGuard
        -_context_builder ContextBuilder
        -_command_router CommandRouter
        -_executor StrategyExecutor
        -_heartbeat HeartbeatService?
        +register_mode(name, strategy, priority)
        +set_base_mode(name)
        +push_override(name)
        +pop_override(name)
        +health() HealthReport
    }

    SystemController --|> AsyncLifecycleMixin
    SystemController *-- DeviceRegistry
    SystemController *-- ModeManager
    SystemController *-- ProtectionGuard
    SystemController *-- ContextBuilder
    SystemController *-- CommandRouter
    SystemController *-- StrategyExecutor
    SystemController o-- HeartbeatService
    SystemController --> SystemControllerConfig
```

---

## 8. Storage Layer

```mermaid
classDiagram
    direction TB

    class MongoConfig {
        <<frozen dataclass>>
        +host str = "localhost"
        +port int = 27017
        +database str
        +replica_hosts tuple~str~?
        +replica_set str?
        +username str?
        +password str?
        +auth_source str?
        +auth_mechanism str?
        +tls bool = False
        +tls_cert_key_file str?
        +tls_ca_file str?
        +tls_allow_invalid_hostnames bool
        +server_selection_timeout_ms int
        +connect_timeout_ms int
        +socket_timeout_ms int
    }

    class MongoClient {
        +create_client(config) AsyncIOMotorClient
    }

    MongoClient --> MongoConfig

    class MongoBatchUploader {
        -_client AsyncIOMotorClient
        -_database str
        -_collection str
        -_batch list
        -_batch_size int
        +add(record)
        +upload_batch()
        +flush()
    }

    class MongoQueueWriter {
        -_client AsyncIOMotorClient
        +enqueue(record)
        +start()
        +stop()
    }

    class TLSConfig {
        <<frozen dataclass>>
        +ca_certs str
        +certfile str?
        +keyfile str?
        +cert_reqs str
        +to_ssl_context() SSLContext
    }

    class RedisConfig {
        <<frozen dataclass>>
        +host str = "localhost"
        +port int = 6379
        +username str?
        +password str?
        +db int = 0
        +sentinel_hosts list~tuple~?
        +sentinel_password str?
        +service_name str?
        +tls TLSConfig?
        +socket_timeout float
        +connection_pool_size int
    }

    RedisConfig --> TLSConfig

    class RedisClient {
        -_config RedisConfig
        -_client Redis?
        +connect()
        +disconnect()
        +is_connected() bool
        +get(key) str?
        +set(key, value, ex)
        +hget(key, field) str?
        +hset(key, field, value)
        +hgetall(key) dict
        +hincrby(key, field, amount)
        +sadd(key, members)
        +srem(key, members)
        +smembers(key) set
        +publish(channel, message)
        +subscribe(channel) AsyncIterator
    }

    RedisClient --> RedisConfig
```

---

## 9. Data Flow — PQ Control Sequence

```mermaid
sequenceDiagram
    participant SC as SystemController
    participant CB as ContextBuilder
    participant DR as DeviceRegistry
    participant DEV as AsyncModbusDevice
    participant SE as StrategyExecutor
    participant STR as PQModeStrategy
    participant PG as ProtectionGuard
    participant CR as CommandRouter

    SC->>SE: run()
    loop Every interval
        SE->>CB: build()
        CB->>DR: get_devices_by_trait("ess")
        DR-->>CB: [battery_device]
        CB->>DEV: latest_values
        DEV-->>CB: {soc: 75, ...}
        CB-->>SE: StrategyContext(soc=75)

        SE->>STR: execute(context)
        STR-->>SE: Command(p=100, q=50)

        SE->>PG: apply(command, context)
        PG-->>SE: Command(p=95, q=50)

        SE->>CR: route(command)
        CR->>DR: get_responsive_devices_by_trait("pcs")
        DR-->>CR: [pcs_device]
        CR->>DEV: write_point("power_setpoint", 95)
        CR->>DEV: write_point("reactive_setpoint", 50)
    end
```
