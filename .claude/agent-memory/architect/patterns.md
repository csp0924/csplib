# Codebase Patterns Reference

## Module Public API Surfaces (confirmed 2026-03-05)

### Core (`csp_lib/core/__init__.py`)
Exports: get_logger, set_level, configure_logging, logger, AsyncLifecycleMixin,
DeviceError, DeviceConnectionError, CommunicationError, AlarmError, ConfigurationError,
HealthStatus, HealthReport, HealthCheckable

### Modbus (`csp_lib/modbus/__init__.py`)
Types: Int16, UInt16, Int32, UInt32, Int64, UInt64, Float32, Float64, DynamicInt, DynamicUInt, ModbusString, ModbusDataType
Clients: AsyncModbusClientBase, PymodbusTcpClient, PymodbusRtuClient, SharedPymodbusTcpClient
Queue: RequestQueueConfig, RequestPriority, CircuitBreakerState, ModbusRequestQueue
Others: ModbusCodec, ModbusTcpConfig, ModbusRtuConfig, ByteOrder, RegisterOrder, Parity, FunctionCode
Exceptions: ModbusError, ModbusEncodeError, ModbusDecodeError, ModbusConfigError, ModbusCircuitBreakerError, ModbusQueueFullError

### Manager (`csp_lib/manager/__init__.py`)
Exports include: AlarmRepository, MongoAlarmRepository, CommandRepository, MongoCommandRepository,
ScheduleRepository, MongoScheduleRepository, DeviceEventSubscriber, plus managers and schemas

## Dataclass Conventions
- Config objects: `@dataclass(frozen=True)` (note: NOT all use `slots=True`)
- `DeviceConfig`: frozen=True only
- `RequestQueueConfig`: frozen=True only
- `integration/schema.py` mappings: `@dataclass(frozen=True)` only
- Non-frozen: `SystemControllerConfig` uses plain `@dataclass`

## Strategy Pattern
- `Strategy` is an ABC at `csp_lib/controller/core/strategy.py`
- Concrete: PQModeStrategy, QVStrategy, FPStrategy, IslandModeStrategy, PVSmoothStrategy, StopStrategy, BypassStrategy, ScheduleStrategy
- Registration: `ModeManager.register(name, strategy, priority, description)` at `csp_lib/controller/system/mode.py`
- CascadingStrategy wraps multiple base strategies

## Repository Pattern
- Each domain has own Protocol + MongoImpl in same file
- AlarmRepository: upsert, resolve, get_active_alarms, get_active_by_device
- CommandRepository: create, update_status, get, list_by_device
- ScheduleRepository: find_active_rules, get_all_enabled, upsert
- MongoAlarmRepository and MongoScheduleRepository have ensure_indexes(); MongoCommandRepository does NOT
