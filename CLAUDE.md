# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**csp_lib** (package name: `csp0924_lib`) is a Python 3.13+ library for industrial equipment communication and energy management. It provides async Modbus device abstraction, control strategies, alarm management, and integrations with MongoDB and Redis. Supports optional Cython compilation for production builds.

## Commands

| Task | Command |
|------|---------|
| Install all deps | `uv sync --all-groups --all-extras` |
| Run all tests | `uv run pytest tests/ -v` |
| Run single test file | `uv run pytest tests/equipment/test_core_point.py` |
| Run tests by pattern | `uv run pytest -k "test_scale_transform"` |
| Lint | `uv run ruff check .` |
| Lint + auto-fix | `uv run ruff check --fix .` |
| Format | `uv run ruff format .` |
| Type check | `uv run mypy csp_lib/` |
| Build Cython wheel | `python build_wheel.py` |
| Clean build | `python build_wheel.py clean` |
| Editable install (no Cython) | `SKIP_CYTHON=1 pip install -e .` |

Async tests use `@pytest.mark.asyncio` decorator (no global asyncio mode configured).
Pre-commit hooks run `ruff --fix` and `ruff-format` automatically.

## Architecture

8-layer bottom-up architecture. **Dependency direction: lower layers MUST NOT import upper layers.**

```
Layer 8  Additional    cluster, monitor, notification, modbus_server, gui
Layer 7  Storage       mongo, redis
Layer 6  Integration   DeviceRegistry, ContextBuilder, CommandRouter, SystemController
Layer 5  Manager       DeviceManager, AlarmPersistenceManager, DataUploadManager, UnifiedDeviceManager
Layer 4  Controller    Strategies (PQ/QV/FP/Island/...), StrategyExecutor, ModeManager, ProtectionGuard
Layer 3  Equipment     AsyncModbusDevice, Points, Transforms, Alarms, ReadScheduler
Layer 2  Modbus        Data types, async clients (TCP/RTU/Shared), codec
Layer 1  Core          get_logger, AsyncLifecycleMixin, errors, HealthCheckable
```

### Module Boundary & Dependency Direction

| Module | Path | Depends On | Depended By |
|--------|------|------------|-------------|
| Core | `csp_lib/core/` | (none) | all |
| Modbus | `csp_lib/modbus/` | Core | Equipment |
| Equipment | `csp_lib/equipment/` | Core, Modbus | Controller, Manager, Integration |
| Controller | `csp_lib/controller/` | Core, Equipment | Manager, Integration |
| Manager | `csp_lib/manager/` | Core, Equipment, Controller, Storage | Integration |
| Integration | `csp_lib/integration/` | Core, Equipment, Controller, Manager | Additional |
| Storage | `csp_lib/mongo/`, `csp_lib/redis/` | Core | Manager, Additional |
| Additional | `csp_lib/cluster/`, `csp_lib/monitor/`, `csp_lib/notification/`, `csp_lib/modbus_server/`, `csp_lib/gui/`, `csp_lib/statistics/` | varies | (none) |

### Key Reference Files

| Pattern | File | Purpose |
|---------|------|---------|
| AsyncLifecycleMixin | `csp_lib/core/lifecycle.py` | Async context manager base for all lifecycle components |
| Frozen dataclass config | `csp_lib/integration/schema.py` | `@dataclass(frozen=True, slots=True)` config standard |
| Protocol definition | `csp_lib/controller/protocol.py` | `@runtime_checkable Protocol` pattern |
| Error hierarchy | `csp_lib/core/errors.py` | Exception class hierarchy |
| Device mock | `tests/integration/test_system_controller.py` | `_make_device()` mock pattern |
| FastAPI test client | `tests/gui/conftest.py` | Test client fixture pattern |

### Key Patterns

- **Async-first**: All device I/O and managers use asyncio. Lifecycle via `AsyncLifecycleMixin` (`async with`).
- **Event-driven**: `AsyncModbusDevice` emits events (`value_change`, `alarm_triggered`) via on/emit.
- **Frozen dataclass configs**: Immutable configuration objects throughout.
- **Optional dependencies**: `csp_lib[modbus]`, `csp_lib[mongo]`, `csp_lib[redis]`, `csp_lib[monitor]`, `csp_lib[cluster]`, `csp_lib[gui]`, `csp_lib[all]`.
- **Logging**: Centralized loguru with per-module level control via `get_logger(module_name)`.

## Code Style

| Rule | Value |
|------|-------|
| Line length | 120 |
| Quotes | Double |
| Ruff rules | E, W, F, I (isort), B (flake8-bugbear) |
| Ignored | E501 (formatter handles), B027 (empty abstract methods) |
| Target | Python 3.13 |
| Per-file | `setup.py`: E402; `csp_lib/gui/api/*.py`: B008 (FastAPI `Depends()`) |

## CI/CD

GitHub Actions (`.github/workflows/build-wheels.yml`):
- **PR**: lint + test (Ubuntu + Windows)
- **Tag (v\*)**: lint + test + build wheels (Windows/manylinux) + publish to PyPI
- `SKIP_CYTHON=1` to skip Cython in test environments


### Agent Roles

| Agent | File | Role | File Scope (R/W) |
|-------|------|------|-------------------|
| Feature Driver | [`.claude/agents/feature-driver.md`](.claude/agents/feature-driver.md) | 需求拆解、影響分析、版本規劃 | `CHANGELOG.md`, `project.md` |
| Architect | [`.claude/agents/architect.md`](.claude/agents/architect.md) | API 合約設計、層級邊界守衛 | Read-only all |
| Implementer | [`.claude/agents/implementer.md`](.claude/agents/implementer.md) | 遵循架構設計撰寫生產程式碼 | `csp_lib/**/*.py`, `examples/*.py` |
| Security Reviewer | [`.claude/agents/security-reviewer.md`](.claude/agents/security-reviewer.md) | ICS/SCADA 安全、OWASP 審計 | Read-only all |
| Test Planner | [`.claude/agents/test-planner.md`](.claude/agents/test-planner.md) | 測試策略、案例撰寫、覆蓋率 | `tests/**/*.py` |
| Doc Organizer | [`.claude/agents/doc-organizer.md`](.claude/agents/doc-organizer.md) | 文件維護、CHANGELOG、API docs | `docs/**/*.md`, `CHANGELOG.md`, `README.md` |
| Performance Optimizer | [`.claude/agents/performance-optimizer.md`](.claude/agents/performance-optimizer.md) | 效能剖析、基準測試、Cython 相容 | `csp_lib/**/*.py` (coordinated) |


### File Ownership Boundary (防衝突)

| Directory / File | Owner | Others |
|-----------------|-------|--------|
| `csp_lib/**/*.py` | implementer | read |
| `tests/**/*.py` | test-planner | read |
| `docs/**/*.md` | doc-organizer | read |
| `CHANGELOG.md` | doc-organizer | read (feature-driver drafts) |
| `README.md`, `BUILDING.md` | doc-organizer | read |
| `examples/*.py` | implementer | read |
| `project.md` | feature-driver | read |
| `pyproject.toml`, `.github/`, `build_wheel.py`, `setup.py` | human (manual) | read |
