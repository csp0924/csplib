# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**csp_lib** (package name: `csp0924_lib`) is a Python 3.13+ library for industrial equipment communication and energy management. It provides async Modbus device abstraction, control strategies, alarm management, and integrations with MongoDB and Redis. Supports optional Cython compilation for production builds.

## Common Commands

### Development Setup
```bash
uv sync --all-groups --all-extras    # Install all deps including dev
```

### Testing
```bash
uv run pytest tests/ -v                           # Run all tests
uv run pytest tests/equipment/test_core_point.py   # Run a single test file
uv run pytest -k "test_scale_transform"            # Run tests matching pattern
```
Async tests use `@pytest.mark.asyncio` decorator (no global asyncio mode configured).

### Linting & Formatting
```bash
uv run ruff check .          # Lint
uv run ruff check --fix .    # Lint with auto-fix
uv run ruff format .         # Format
uv run mypy csp_lib/         # Type check
```
Pre-commit hooks run `ruff --fix` and `ruff-format` automatically.

### Building
```bash
python build_wheel.py              # Build Cython-compiled wheel
python build_wheel.py clean        # Clean build artifacts
SKIP_CYTHON=1 pip install -e .     # Editable install without Cython
```

## Architecture

The library follows a layered architecture, bottom-up:

1. **Core Layer** (`csp_lib.core`) — Logging (loguru-based `get_logger`), `AsyncLifecycleMixin` (async context manager base), error hierarchy (`DeviceError`, `CommunicationError`, `AlarmError`, `ConfigurationError`), health checking (`HealthCheckable`/`HealthReport`).

2. **Modbus Layer** (`csp_lib.modbus`) — Low-level register I/O: data types (Int16, Float32, ModbusString...), async clients (TCP/RTU/Shared), codec with endianness support.

3. **Equipment Layer** (`csp_lib.equipment`) — Device abstraction built on Modbus:
   - `AsyncModbusDevice`: Central class managing periodic reads, connection state, events, and alarms.
   - Points (`ReadPoint`/`WritePoint`), transforms (`ScaleTransform`, `BitExtractTransform`), and `ProcessingPipeline` for data transformation chains.
   - Alarm system with `AlarmDefinition`, evaluators (BitMask/Threshold/Table), and `AlarmStateManager` with hysteresis.
   - Transport: `PointGrouper` merges adjacent registers, `GroupReader` for batch reads, `ReadScheduler` for fixed + rotating modes.

4. **Controller Layer** (`csp_lib.controller`) — Control strategies (PVSmooth, PQ, QV, FP, Island, Bypass, Stop, Schedule) using the Command pattern, orchestrated by `StrategyExecutor`. System management via `ModeManager` (priority-based mode switching), `ProtectionGuard` (SOC/reverse-power/alarm rules), `CascadingStrategy` (multi-strategy power allocation).

5. **Manager Layer** (`csp_lib.manager`) — System integration: `DeviceManager` (lifecycle), `AlarmPersistenceManager` (MongoDB + Redis pub/sub), `DataUploadManager` (batch uploads), `WriteCommandManager` (command routing), `StateSyncManager` (Redis sync). `UnifiedDeviceManager` combines them all.

6. **Integration Layer** (`csp_lib.integration`) — Bridges Equipment and Controller: `DeviceRegistry` (trait-based device lookup), `ContextBuilder` (device values → `StrategyContext`), `CommandRouter` (commands → device writes), `GridControlLoop` (simple orchestrator), `SystemController` (full orchestrator with ModeManager + ProtectionGuard).

7. **Storage** (`csp_lib.mongo`, `csp_lib.redis`) — Async MongoDB (motor) and Redis clients with batch upload and pub/sub.

8. **Additional Modules**: `csp_lib.cluster` (etcd leader election HA), `csp_lib.monitor` (system metrics + alerts), `csp_lib.notification` (multi-channel alarm dispatch), `csp_lib.modbus_server` (Modbus TCP simulation server), `csp_lib.gui` (FastAPI dashboard).

### Key Patterns
- **Async-first**: All device I/O and managers use asyncio. Lifecycle managed via `AsyncLifecycleMixin` (`async with`).
- **Event-driven**: `AsyncModbusDevice` emits events (`value_change`, `alarm_triggered`, etc.) via on/emit.
- **Frozen dataclass configs**: Immutable configuration objects throughout.
- **Optional dependencies**: `csp_lib[modbus]`, `csp_lib[mongo]`, `csp_lib[redis]`, `csp_lib[monitor]`, `csp_lib[cluster]`, `csp_lib[gui]`, `csp_lib[all]`.
- **Logging**: Centralized loguru with per-module level control via `get_logger(module_name)`.
- **Per-file lint ignores**: `setup.py` allows E402; `csp_lib/gui/api/*.py` allows B008 (FastAPI `Depends()` pattern).

## Code Style

- Line length: 120
- Double quotes
- Ruff rules: E, W, F, I (isort), B (flake8-bugbear)
- E501 ignored (formatter handles line length); B027 ignored (intentional empty abstract methods)
- Target: Python 3.13

## CI/CD

GitHub Actions workflow (`.github/workflows/build-wheels.yml`):
- **PR**: lint + test only (Ubuntu + Windows)
- **Tag (v\*)**: lint + test + build wheels (Windows/manylinux) + publish to PyPI
- Set `SKIP_CYTHON=1` to skip Cython compilation in test environments
