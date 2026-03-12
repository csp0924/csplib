# Changelog

本專案的所有重要變更皆記錄於此檔案。

格式基於 [Keep a Changelog](https://keepachangelog.com/)，版本號遵循 [Semantic Versioning](https://semver.org/)。

## [Unreleased]

## [0.4.2] - 2026-03-13

### Fixed
- **Modbus Request Queue**: 修復 worker 信號遺失（clear 後 re-check total_size）和 submit TOCTOU（size 檢查移入 lock 內）(#19, #20)
- **StrategyExecutor**: 修復 PopOverride bypass 後 executor 卡在 triggered mode 無法恢復的問題 (#18)

## [0.4.1] - 2026-03-10

### Fixed
- **Installation**: 修復安裝失敗問題 (#15)

## [0.4.0] - 2026-03-09

### Added
- **動態點位管理** (`csp_lib.equipment.device`):
  - `ReconfigureSpec`: frozen dataclass，指定要替換的組件（`always_points`、`rotating_points`、`write_points`、`alarm_evaluators`、`capability_bindings`），`None` 表示保持不變
  - `AsyncModbusDevice.reconfigure(spec)`: 執行期動態重新配置點位，自動停止/恢復讀取迴圈，透過 `AlarmStateManager.export_states()` / `import_states()` 保留告警狀態，發出 `reconfigured` 事件
  - `AsyncModbusDevice.restart()`: 重啟讀取迴圈（stop + start），發出 `restarted` 事件
  - 點位開關 API：`disable_point(name)`、`enable_point(name)`、`is_point_enabled(name)`、`disabled_points` property（`frozenset`）
  - 點位查詢 API：`read_points`、`rotating_read_points`、`write_point_names`、`all_point_names`、`get_point_info()` → `list[PointInfo]`
  - `PointInfo`: frozen dataclass，點位詳細資訊（name、address、data_type、direction、enabled、read_group、metadata）
- **新事件** (`csp_lib.equipment.device.events`):
  - `EVENT_RECONFIGURED` / `ReconfiguredPayload(device_id, changed_sections)`: 動態重新配置完成
  - `EVENT_RESTARTED` / `RestartedPayload(device_id)`: 讀取迴圈重啟
  - `EVENT_POINT_TOGGLED` / `PointToggledPayload(device_id, point_name, enabled)`: 點位啟用/停用
- **ReadScheduler 動態更新** (`csp_lib.equipment.transport`):
  - `ReadScheduler.update_groups(always_groups, rotating_groups)`: 動態更新分組，`None` 表示保持不變，更新 `rotating_groups` 時自動重置輪替索引
- **AlarmStateManager 狀態遷移** (`csp_lib.equipment.alarm`):
  - `AlarmStateManager.export_states()`: 匯出所有告警狀態的 shallow copy
  - `AlarmStateManager.import_states(states)`: 匯入告警狀態，對已存在的代碼覆蓋計數與時間欄位
- **Hierarchical Control Protocols** (`csp_lib.integration.hierarchical`):
  - `SubExecutorAgent`: runtime_checkable Protocol for remote sub-executor coordination (SCADA -> Area -> Site -> Device)
  - `TransportAdapter`: runtime_checkable Protocol for pluggable transport backends (Redis / gRPC / HTTP)
  - `DispatchCommand`: frozen dataclass for hierarchical command dispatch with priority, timestamp, and source tracing
  - `ExecutorStatus` / `StatusReport`: frozen dataclasses for upward status reporting
  - `DispatchPriority`: IntEnum for command priority levels (NORMAL / SCHEDULE / MANUAL / PROTECTION)
- **gRPC Service Definitions** (`csp_lib/grpc/control.proto`):
  - `ControlDispatchService`: command dispatch, override management, health check
  - `StatusReportService`: status reporting and streaming subscription
- **Demo**: `examples/11_cascading_strategy.py` — CascadingStrategy deep dive showing delta-based clamping, multi-layer allocation, capacity constraints, edge cases, and hierarchical control preview
- **Demo**: `examples/demo_full_system.py` — full end-to-end system integration demo covering device creation, registry, control loop, mode switching, and protection
- **Architecture Doc**: `docs/architecture/hierarchical-control.md` — Mermaid diagrams, protocol reference, extension point mapping
- +49 new tests: 動態點位管理（`test_scheduler_update.py` 9 tests、`test_point_toggle.py` 17 tests、`test_device_reconfigure.py` 23 tests）
- +258 new tests: frozen dataclass configs, ReadScheduler, DeviceEventSubscriber, NaN/Inf propagation, Modbus exception handling, Protocol runtime checks
- +50 new tests: SubExecutorAgent Protocol compliance, TransportAdapter Protocol compliance, CascadingStrategy extended scenarios (delta clamping, context propagation, hierarchical integration, edge cases)

### Fixed
- **Integration re-exports**: Promoted `_apply_builtin_aggregate` to public API (`apply_builtin_aggregate`), added missing re-exports (`ComputeOffloader`, `ActionCommand`, `CommandResult`, `create_system_alarm_evaluators`), wrapped statistics import in try/except for optional dependency safety
- **Safety (fail-safe)**: Protection chain now outputs fail-safe (P=0, Q=0) instead of fail-open when a rule raises an exception
- **Safety (resource cleanup)**: `AsyncModbusDevice.__aexit__` and `SystemController._on_stop` now use try/finally to guarantee cleanup on error

## [0.3.3] - 2026-02-16

### Added
- **GroupControllerManager** (`csp_lib.integration`): 多群組控制器管理
  - GroupDefinition: 群組定義（ID、設備列表、配置）
  - GroupControllerManager: 管理多個獨立 SystemController 實例，每組擁有獨立的模式管理、保護機制與策略執行
- **integration 模組** (`csp_lib.integration`): Equipment-Controller 整合層
  - DeviceRegistry: Trait-based 設備查詢索引
  - ContextBuilder: 設備值 → StrategyContext 映射（支援多設備聚合）
  - CommandRouter: Command → 設備寫入路由（支援廣播寫入）
  - DeviceDataFeed: 設備 read_complete 事件 → PVDataService 餵入
  - GridControlLoop: 完整控制迴圈編排器（AsyncLifecycleMixin）
  - AggregateFunc / ContextMapping / CommandMapping / DataFeedMapping 宣告式映射 schema
- AsyncLifecycleMixin (`csp_lib.core`): 通用 async 生命週期管理
- DeviceEventSubscriber (`csp_lib.manager`): 設備事件訂閱基底類別
- 新增 GroupControllerManager 測試（26 個測試：驗證、查詢、模式管理、獨立性、生命週期、健康檢查）
- 新增 integration 模組測試（94 個測試）
- 新增 AsyncLifecycleMixin 單元測試
- 新增 core transform 綜合測試

### Changed
- 重構管理器使用新基底類別（AlarmPersistenceManager、DataUploadManager、
  StateSyncManager → DeviceEventSubscriber；DeviceManager、UnifiedDeviceManager、
  RedisCommandAdapter → AsyncLifecycleMixin）

## [0.3.2] - 2026-01-18

（版本號碼遞增，無功能變更）

## [0.3.1] - 2026-01-18

### Added
- **manager 模組** (`csp_lib.manager`): 系統整合管理層
  - AlarmPersistenceManager / MongoAlarmRepository
  - DeviceManager / DeviceGroup
  - DataUploadManager
  - WriteCommandManager / MongoCommandRepository
  - StateSyncManager
  - UnifiedDeviceManager / UnifiedConfig
- **redis 模組** (`csp_lib.redis`): Async Redis 客戶端（含 TLS / Sentinel）
- Equipment 增強: PowerFactorTransform、read_once、自動重連、GroupReader 並行讀取、
  CAN frame 解析器、高階 action 支援、模擬模組
- Controller 增強: GridController protocol、新控制策略、ActionCommand schema

### Changed
- Modbus: unit_id 從連線設定移至請求方法
- 全面使用 UTC 時區感知 datetime
- 策略生命週期 hooks 改為 async

### Fixed
- PointGrouper 狀態重置問題
- AlarmLevel 使用修正

## [0.3.0] - 2026-01-13

### Added
- **equipment 模組** (`csp_lib.equipment`): 設備抽象層
  - 資料轉換: ScaleTransform、RoundTransform、EnumMapTransform、ClampTransform、
    BoolTransform、InverseTransform、BitExtractTransform、ByteExtractTransform、
    MultiFieldExtractTransform
  - ProcessingPipeline: 轉換鏈管線
  - ReadPoint / WritePoint 定義
  - 告警系統: AlarmDefinition、BitMaskEvaluator、ThresholdEvaluator、TableEvaluator、
    AlarmStateManager（含遲滯邏輯）
  - 傳輸層: PointGrouper、GroupReader、ReadScheduler、ValidatedWriter
  - AsyncModbusDevice: 核心設備類別（週期讀取、連線管理、事件、告警）
  - DeviceConfig / DeviceEventEmitter
- CI/CD: trusted publishing + attestations

## [0.2.1] - 2026-01-11

### Fixed
- Modbus 共用客戶端資源引用計數修正（防止 connect() 重複呼叫時的計數錯誤）

## [0.2.0] - 2026-01-11

### Added
- **modbus 模組** (`csp_lib.modbus`): Modbus 通訊層
  - 資料型別: Int16/UInt16/Int32/UInt32/Int64/UInt64/Float32/Float64/ModbusString
  - ModbusCodec: 編解碼 API（支援 byte order / register order）
  - Async 客戶端: AsyncModbusTcpClient、AsyncModbusRtuClient、SharedPymodbusTcpClient
  - ModbusTcpConfig / ModbusRtuConfig
  - 自訂例外階層

## [0.1.1] - 2026-01-10

### Added
- Cython 編譯模組的 .pyi stub 自動產生
- GitHub Release 產物附加
- 二進位發佈的程式碼保護

## [0.1.0] - 2026-01-10

### Added
- **core 模組** (`csp_lib.core`): loguru 集中式 logging（get_logger / set_level / configure_logging）
- **mongo 模組** (`csp_lib.mongo`): Async MongoDB 批次上傳（MongoConfig / 批次佇列 / 上傳器）
- **controller 模組** (`csp_lib.controller`): 控制策略框架（Strategy / StrategyExecutor / PVDataService）
- CI/CD: GitHub Actions（PR lint+test / tag build+publish）
- Cython 二進位 wheel 建置（build_wheel.py）
- 套件更名為 csp0924_lib
