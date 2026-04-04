---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
---

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
        class CircuitState {
            <<enumeration>>
            CLOSED
            OPEN
            HALF_OPEN
        }
        class CircuitBreaker {
            +state CircuitState
            +record_success()
            +record_failure()
            +reset()
            +allows_request() bool
        }
        class RetryPolicy {
            <<frozen dataclass>>
            +max_retries int
            +base_delay float
            +exponential_base float
        }
        class RuntimeParameters {
            +get(key) Any
            +set(key, value)
            +snapshot() dict
        }
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

    namespace CAN {
        class CANBusConfig {
            <<frozen dataclass>>
            +interface str
            +channel str
            +bitrate int
        }
        class AsyncCANClientBase {
            <<abstract>>
            +connect()
            +disconnect()
            +send()
            +subscribe()
            +request()
        }
        class PythonCANClient
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
        class AsyncCANDevice
        class DeviceProtocol {
            <<protocol>>
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
        class EventDrivenOverride {
            <<protocol>>
            +name str
            +cooldown_seconds float
            +should_activate(ctx) bool
        }
        class CommandProcessor {
            <<protocol>>
            +process(cmd, ctx) Command
        }
        class DroopStrategy
        class RampStopStrategy
        class PowerCompensator {
            +process(cmd, ctx) Command
        }
        class FFCalibrationStrategy
        class DynamicSOCProtection
        class GridLimitProtection
        class RampStopProtection
        class LoadSheddingStrategy
        class SwitchSource {
            <<enumeration>>
            MANUAL
            SCHEDULE
            EVENT
            INTERNAL
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
            +route_per_device()
            +register_event_override()
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
            +route_per_device(cmd, per_device)
        }
        class PowerDistributor {
            <<protocol>>
            +distribute(cmd, devices) dict
        }
        class HeartbeatService
    }

    namespace Storage {
        class MongoClient
        class MongoBatchUploader
        class RedisClient
    }

    namespace ModbusGateway {
        class ModbusGatewayServer {
            +start()
            +stop()
            +update_register(address, value)
        }
        class GatewayRegisterMap
        class CommunicationWatchdog
    }

    namespace Statistics {
        class StatisticsEngine
        class DeviceEnergyTracker
        class StatisticsManager
    }

    %% Core inheritance
    AsyncModbusDevice ..|> HealthCheckable
    DeviceManager --|> AsyncLifecycleMixin
    UnifiedDeviceManager --|> AsyncLifecycleMixin
    SystemController --|> AsyncLifecycleMixin

    %% CircuitBreaker
    CircuitBreaker --> CircuitState

    %% CAN
    PythonCANClient --|> AsyncCANClientBase

    %% Equipment
    AsyncModbusDevice ..|> DeviceProtocol
    AsyncCANDevice ..|> DeviceProtocol
    AsyncCANDevice *-- AsyncCANClientBase

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

    %% Controller
    LoadSheddingStrategy --|> Strategy
    DroopStrategy --|> Strategy
    RampStopStrategy --|> Strategy
    FFCalibrationStrategy --|> Strategy
    PowerCompensator ..|> CommandProcessor
    DynamicSOCProtection --|> ProtectionRule
    GridLimitProtection --|> ProtectionRule
    RampStopProtection --|> ProtectionRule
    ModeManager --> SwitchSource

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
    SystemController o-- PowerDistributor
    SystemController o-- EventDrivenOverride
    SystemController o-- HeartbeatService
    ContextBuilder --> DeviceRegistry
    CommandRouter --> DeviceRegistry
    ContextBuilder ..> StrategyContext : creates
    CommandRouter ..> Command : consumes

    %% Storage usage
    AlarmPersistenceManager --> MongoClient
    DataUploadManager --> MongoBatchUploader
    StateSyncManager --> RedisClient

    %% Modbus Gateway
    ModbusGatewayServer --|> AsyncLifecycleMixin
    ModbusGatewayServer *-- GatewayRegisterMap
    ModbusGatewayServer o-- CommunicationWatchdog

    %% Statistics
    StatisticsManager --|> DeviceEventSubscriber
    StatisticsManager *-- StatisticsEngine
    StatisticsEngine o-- DeviceEnergyTracker
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

    class CircuitState {
        <<enumeration>>
        CLOSED
        OPEN
        HALF_OPEN
    }

    class CircuitBreaker {
        -_threshold int
        -_cooldown float
        -_state CircuitState
        -_failure_count int
        -_last_failure_time float
        +state CircuitState
        +failure_count int
        +record_success()
        +record_failure()
        +reset()
        +allows_request() bool
    }

    class RetryPolicy {
        <<frozen dataclass>>
        +max_retries int = 3
        +base_delay float = 1.0
        +exponential_base float = 2.0
        +get_delay(attempt) float
    }

    HealthReport --> HealthStatus
    HealthReport o-- HealthReport : children
    HealthCheckable ..> HealthReport : returns

    DeviceConnectionError --|> DeviceError
    CommunicationError --|> DeviceError
    AlarmError --|> DeviceError
    ConfigurationError --|> Exception

    CircuitBreaker --> CircuitState
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

## 3b. CAN Layer

```mermaid
classDiagram
    direction TB

    class CANBusConfig {
        <<frozen dataclass>>
        +interface str
        +channel str
        +bitrate int = 500_000
        +receive_own_messages bool = False
    }

    class CANFrame {
        <<frozen dataclass>>
        +can_id int
        +data bytes
        +timestamp float = 0.0
        +is_remote bool = False
    }

    class AsyncCANClientBase {
        <<abstract>>
        +connect()*
        +disconnect()*
        +is_connected()* bool
        +start_listener()*
        +stop_listener()*
        +subscribe(can_id, handler)* Callable
        +send(can_id, data)*
        +request(can_id, data, response_id, timeout)* CANFrame
    }

    class PythonCANClient {
        -_config CANBusConfig
        -_bus Any
        -_connected bool
        -_listener_task Task
        -_handlers dict
        -_pending_responses dict
        +connect()
        +disconnect()
        +is_connected() bool
        +start_listener()
        +stop_listener()
        +subscribe(can_id, handler) Callable
        +send(can_id, data)
        +request(can_id, data, response_id, timeout) CANFrame
    }

    PythonCANClient --|> AsyncCANClientBase
    PythonCANClient --> CANBusConfig
    AsyncCANClientBase ..> CANFrame : uses

    class CANError
    class CANConnectionError
    class CANTimeoutError
    class CANSendError

    CANConnectionError --|> CANError
    CANTimeoutError --|> CANError
    CANSendError --|> CANError
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

    class DeviceProtocol {
        <<protocol>>
        +device_id str
        +is_connected bool
        +is_responsive bool
        +latest_values dict
        +is_protected bool
        +active_alarms list~AlarmState~
        +read_once() dict
        +write(name, value) WriteResult
        +on(event, handler) Callable
        +health() HealthReport
    }

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

    class AsyncCANDevice {
        -_config DeviceConfig
        -_client AsyncCANClientBase
        -_emitter DeviceEventEmitter
        +device_id str
        +is_connected bool
        +is_responsive bool
        +is_protected bool
        +latest_values dict
        +active_alarms list~AlarmState~
        +start()
        +stop()
        +read_once() dict
        +write(name, value) WriteResult
        +on(event, handler) Callable
        +health() HealthReport
    }

    AsyncModbusDevice ..|> DeviceProtocol
    AsyncCANDevice ..|> DeviceProtocol

    AsyncModbusDevice *-- DeviceConfig
    AsyncModbusDevice *-- ReadScheduler
    AsyncModbusDevice *-- GroupReader
    AsyncModbusDevice *-- ValidatedWriter
    AsyncModbusDevice *-- AlarmStateManager
    AsyncModbusDevice o-- AlarmEvaluator
    AsyncModbusDevice o-- CapabilityBinding
    AsyncModbusDevice *-- DeviceEventEmitter
    AsyncModbusDevice ..> WriteResult

    AsyncCANDevice *-- AsyncCANClientBase
    AsyncCANDevice *-- DeviceEventEmitter
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
        +required_capabilities list~Capability~
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
    class DroopStrategy {
        -_config DroopConfig
        +execute(context) Command
    }
    class RampStopStrategy {
        +execute(context) Command
    }
    class LoadSheddingStrategy {
        -_config LoadSheddingConfig
        +config LoadSheddingConfig
        +shed_stage_names list~str~
        +execute(context) Command
        +on_activate()
        +on_deactivate()
    }
    class FFCalibrationStrategy {
        -_config FFCalibrationConfig
        +execute(context) Command
    }

    PQModeStrategy --|> Strategy
    PVSmoothStrategy --|> Strategy
    QVStrategy --|> Strategy
    FPStrategy --|> Strategy
    DroopStrategy --|> Strategy
    RampStopStrategy --|> Strategy
    IslandStrategy --|> Strategy
    BypassStrategy --|> Strategy
    StopStrategy --|> Strategy
    ScheduleStrategy --|> Strategy
    LoadSheddingStrategy --|> Strategy
    FFCalibrationStrategy --|> Strategy
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

    class SwitchSource {
        <<enumeration>>
        MANUAL
        SCHEDULE
        EVENT
        INTERNAL
    }

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
        +last_switch_source SwitchSource?
        +register(name, strategy, priority, description)
        +unregister(name)
        +set_base_mode(name, source)
        +add_base_mode(name, source)
        +remove_base_mode(name, source)
        +get_base_mode() ModeDefinition?
        +push_override(name, source)
        +pop_override(name, source)
        +clear_overrides()
        +get_active_strategy() Strategy?
        +get_active_mode() ModeDefinition?
    }

    ModeManager o-- ModeDefinition
    ModeManager --> SwitchSource

    class EventDrivenOverride {
        <<protocol>>
        +name str
        +cooldown_seconds float
        +should_activate(context) bool
    }

    class AlarmStopOverride {
        -_name str
        -_alarm_key str
        +name str
        +cooldown_seconds float
        +should_activate(context) bool
    }

    class ContextKeyOverride {
        -_name str
        -_context_key str
        -_activate_when Callable
        -_cooldown_seconds float
        +name str
        +cooldown_seconds float
        +should_activate(context) bool
    }

    AlarmStopOverride ..|> EventDrivenOverride
    ContextKeyOverride ..|> EventDrivenOverride
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

    class DynamicSOCProtection {
        +name str
        +evaluate(command, context) Command
        +is_triggered bool
    }

    class GridLimitProtection {
        +name str
        +evaluate(command, context) Command
        +is_triggered bool
    }

    class RampStopProtection {
        +name str
        +evaluate(command, context) Command
        +is_triggered bool
    }

    SOCProtection --|> ProtectionRule
    ReversePowerProtection --|> ProtectionRule
    SystemAlarmProtection --|> ProtectionRule
    DynamicSOCProtection --|> ProtectionRule
    GridLimitProtection --|> ProtectionRule
    RampStopProtection --|> ProtectionRule

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

### 5d. CommandProcessor Pipeline（v0.5.1）

```mermaid
classDiagram
    direction TB

    class CommandProcessor {
        <<protocol>>
        +process(command, context) Command
    }

    class PowerCompensator {
        -_config PowerCompensatorConfig
        -_ff_table dict
        -_integral float
        +process(command, context) Command
        +reset()
    }

    class PowerCompensatorConfig {
        <<frozen dataclass>>
        +ki float
        +integral_limit float
        +ff_table_path str?
    }

    class FFCalibrationConfig {
        <<frozen dataclass>>
        +step_kw float
        +settle_seconds float
        +measure_seconds float
    }

    PowerCompensator ..|> CommandProcessor
    PowerCompensator --> PowerCompensatorConfig
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
        +route_per_device(command, per_device_commands)
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

    class DeviceSnapshot {
        <<frozen dataclass>>
        +device_id str
        +metadata dict
        +latest_values dict
        +capabilities dict
        +get_capability_value(capability, slot) Any
    }

    class PowerDistributor {
        <<protocol>>
        +distribute(cmd, devices) dict~str, Command~
    }

    class EqualDistributor {
        +distribute(cmd, devices) dict~str, Command~
    }

    class ProportionalDistributor {
        -_rated_key str
        +distribute(cmd, devices) dict~str, Command~
    }

    class SOCBalancingDistributor {
        -_rated_key str
        -_soc_capability str
        -_soc_slot str
        -_gain float
        +distribute(cmd, devices) dict~str, Command~
    }

    EqualDistributor ..|> PowerDistributor
    ProportionalDistributor ..|> PowerDistributor
    SOCBalancingDistributor ..|> PowerDistributor
    PowerDistributor ..> DeviceSnapshot : uses
    PowerDistributor ..> Command : produces

    class SystemControllerConfig {
        <<dataclass>>
        +context_mappings list~ContextMapping~
        +command_mappings list~CommandMapping~
        +system_base SystemBase?
        +protection_rules list~ProtectionRule~
        +auto_stop_on_alarm bool = True
        +capacity_kva float?
        +heartbeat_mappings list~HeartbeatMapping~
        +power_distributor PowerDistributor?
    }

    class SystemController {
        -_registry DeviceRegistry
        -_mode_manager ModeManager
        -_guard ProtectionGuard
        -_context_builder ContextBuilder
        -_command_router CommandRouter
        -_executor StrategyExecutor
        -_heartbeat HeartbeatService?
        -_power_distributor PowerDistributor?
        -_event_overrides list~EventDrivenOverride~
        +register_mode(name, strategy, priority)
        +set_base_mode(name)
        +push_override(name)
        +pop_override(name)
        +route_per_device(cmd, per_device)
        +register_event_override(override)
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
    SystemController o-- PowerDistributor
    SystemController o-- EventDrivenOverride
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

---

## 10. Data Flow — PQ Control with PowerDistributor

帶有 `PowerDistributor` 的多設備功率分配控制流程，展示 `EventDrivenOverride` 評估和 per-device 路由。

```mermaid
sequenceDiagram
    participant SC as SystemController
    participant CB as ContextBuilder
    participant SE as StrategyExecutor
    participant STR as PQModeStrategy
    participant PG as ProtectionGuard
    participant EO as EventDrivenOverride
    participant PD as PowerDistributor
    participant CR as CommandRouter
    participant D1 as Device_1
    participant D2 as Device_2

    SC->>SE: run()
    loop Every interval
        SE->>CB: build()
        CB-->>SE: StrategyContext

        SE->>STR: execute(context)
        STR-->>SE: Command(p=1000)

        SE->>SC: _on_command(cmd)
        SC->>PG: apply(cmd, ctx)
        PG-->>SC: Command(p=950)

        SC->>EO: should_activate(ctx)
        EO-->>SC: false

        SC->>SC: _build_device_snapshots()
        SC->>PD: distribute(cmd, snapshots)
        PD-->>SC: {d1: Cmd(p=300), d2: Cmd(p=650)}

        SC->>CR: route_per_device(cmd, per_device)
        CR->>D1: write("power", 300)
        CR->>D2: write("power", 650)
    end
```

---

## 11. Modbus Gateway Layer（v0.6.0）

```mermaid
classDiagram
    direction TB

    class GatewayServerConfig {
        <<frozen dataclass>>
        +host str
        +port int
        +register_defs list~GatewayRegisterDef~
        +watchdog WatchdogConfig?
    }

    class GatewayRegisterDef {
        <<frozen dataclass>>
        +address int
        +count int
        +register_type RegisterType
        +description str
    }

    class RegisterType {
        <<enumeration>>
        HOLDING
        INPUT
        COIL
        DISCRETE
    }

    class WatchdogConfig {
        <<frozen dataclass>>
        +timeout_seconds float
        +action str
    }

    class WriteRule {
        <<protocol>>
        +validate(address, value) bool
    }

    class WriteValidator {
        <<protocol>>
        +validate(address, values) bool
    }

    class WriteHook {
        <<protocol>>
        +on_write(address, values)
    }

    class DataSyncSource {
        <<protocol>>
        +start(callback)
        +stop()
    }

    class GatewayRegisterMap {
        -_registers dict
        +get(address) int
        +set(address, value)
        +bulk_update(updates)
    }

    class ModbusGatewayServer {
        -_config GatewayServerConfig
        -_register_map GatewayRegisterMap
        -_watchdog CommunicationWatchdog?
        -_validators list~WriteValidator~
        -_hooks list~WriteHook~
        -_sync_sources list~DataSyncSource~
        +start()
        +stop()
        +update_register(address, value)
    }

    class CommunicationWatchdog {
        -_config WatchdogConfig
        +start()
        +stop()
        +feed()
    }

    class AddressWhitelistValidator {
        -_allowed set~int~
        +validate(address, values) bool
    }

    ModbusGatewayServer --|> AsyncLifecycleMixin
    ModbusGatewayServer *-- GatewayRegisterMap
    ModbusGatewayServer --> GatewayServerConfig
    ModbusGatewayServer o-- CommunicationWatchdog
    ModbusGatewayServer o-- WriteValidator
    ModbusGatewayServer o-- WriteHook
    ModbusGatewayServer o-- DataSyncSource
    GatewayServerConfig o-- GatewayRegisterDef
    GatewayServerConfig --> WatchdogConfig
    GatewayRegisterDef --> RegisterType
    AddressWhitelistValidator ..|> WriteValidator
    CommunicationWatchdog --> WatchdogConfig
```

---

## 12. Statistics Layer（v0.6.0）

```mermaid
classDiagram
    direction TB

    class StatisticsConfig {
        <<frozen dataclass>>
        +metrics list~MetricDefinition~
        +power_sums list~PowerSumDefinition~
        +interval_seconds float
    }

    class MetricDefinition {
        <<frozen dataclass>>
        +name str
        +point_name str
        +device_meter_type DeviceMeterType
    }

    class PowerSumDefinition {
        <<frozen dataclass>>
        +name str
        +device_ids list~str~
        +point_name str
    }

    class DeviceMeterType {
        <<frozen dataclass>>
        +device_id str
        +meter_type str
    }

    class IntervalRecord {
        <<frozen dataclass>>
        +start datetime
        +end datetime
        +energy_kwh float
    }

    class IntervalAccumulator {
        +add_sample(power_kw, timestamp)
        +close_interval() IntervalRecord
    }

    class DeviceEnergyTracker {
        -_accumulators dict
        +on_read_complete(payload)
        +close_all() list~IntervalRecord~
    }

    class PowerSumRecord {
        <<frozen dataclass>>
        +name str
        +total_kw float
        +timestamp datetime
    }

    class StatisticsEngine {
        -_config StatisticsConfig
        -_trackers dict~str, DeviceEnergyTracker~
        +process(device_id, values)
        +compute_power_sums(registry) list~PowerSumRecord~
    }

    class StatisticsManager {
        -_engine StatisticsEngine
        +subscribe(device)
        +start()
        +stop()
    }

    StatisticsConfig o-- MetricDefinition
    StatisticsConfig o-- PowerSumDefinition
    MetricDefinition --> DeviceMeterType
    StatisticsEngine --> StatisticsConfig
    StatisticsEngine o-- DeviceEnergyTracker
    DeviceEnergyTracker o-- IntervalAccumulator
    IntervalAccumulator ..> IntervalRecord : creates
    StatisticsEngine ..> PowerSumRecord : creates
    StatisticsManager *-- StatisticsEngine
    StatisticsManager --|> DeviceEventSubscriber
```
