# Architect Agent Memory

## Project Structure Confirmed (2026-03-05)
- See `patterns.md` for detailed module patterns and API surfaces

## Key Architectural Facts
- `ModbusDataType` ABC at `csp_lib/modbus/types/base.py` - encode/decode with ByteOrder + RegisterOrder
- `AsyncModbusDevice` at `csp_lib/equipment/device/base.py` - does NOT extend AsyncLifecycleMixin, has own `__aenter__`/`__aexit__`
- `DeviceConfig` at `csp_lib/equipment/device/config.py` - `@dataclass(frozen=True)` (no slots=True!)
- `SystemController` extends `AsyncLifecycleMixin` - 425 LOC, well-decomposed via delegation
- Repository protocols exist per-domain (Alarm, Command, Schedule) - not generic `Repository[T]`
- All repository protocols in `csp_lib/manager/` use `Protocol` but NOT `@runtime_checkable`
- `UnitCircuitBreaker` in `csp_lib/modbus/clients/queue.py` - only circuit breaker in codebase
- Error hierarchy: `DeviceError(Exception)` in core, `ModbusError(Exception)` in modbus - separate trees
- `DeviceEventSubscriber` at `csp_lib/manager/base.py` - base for event-subscribing managers

## Layer Boundary Notes
- Modbus exceptions (`ModbusError` tree) are separate from Core exceptions (`DeviceError` tree)
- Manager layer imports from Storage (mongo) for Mongo*Repository implementations
- Controller `Strategy` is an ABC, not a Protocol
