---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
updated: 2026-04-05
version: ">=0.7.0"
---

# 版本歷史

本專案的所有重要變更皆記錄於此。格式基於 [Keep a Changelog](https://keepachangelog.com/)，版本號遵循 [Semantic Versioning](https://semver.org/)。

---

## [0.7.0] - 2026-04-05

### Added

- **`LogFilter`** (`csp_lib.core`): 模組等級過濾器，最長前綴匹配，可直接作為 loguru `filter` 參數
- **`SinkManager`** (`csp_lib.core`): 全域 Sink 生命週期管理單例，支援 `add_sink()` / `remove_sink()` / `set_level()` / `add_file_sink()` / `add_async_sink()` / `attach_remote_source()`
- **`SinkInfo`** (`csp_lib.core`): Sink 資訊 frozen dataclass（`sink_id`、`name`、`sink_type`、`level`、`is_active`）
- **`FileSinkConfig`** (`csp_lib.core`): 檔案 Sink 配置 frozen dataclass，`@dataclass(frozen=True, slots=True)`
- **`LogContext`** (`csp_lib.core`): Async-safe 結構化日誌上下文，支援 context manager / decorator / `bind()` / `unbind()`
- **`LogCapture`** / **`CapturedRecord`** (`csp_lib.core`): 測試用日誌捕獲工具，`contains()` / `filter()` 查詢 API
- **`RemoteLevelSource`** (`csp_lib.core`): 遠端 log 等級來源 `@runtime_checkable` Protocol
- **`AsyncSinkAdapter`** (`csp_lib.core`): 非同步 Sink 轉接器，thread-safe queue 橋接 async handler
- **`RedisLogLevelSource`** (`csp_lib.redis`): `RemoteLevelSource` 的 Redis 實作，Hash + Pub/Sub
- **`add_file_sink(config)`** (`csp_lib.core`): 模組層便利函式，委派全域 SinkManager
- **`DEFAULT_FORMAT`** (`csp_lib.core`): 帶 ANSI 色彩的預設格式字串常數
- **環境變數覆蓋**: `configure_logging(env_prefix=...)` 支援 `{PREFIX}_LOG_LEVEL` / `_LOG_FORMAT` / `_LOG_ENQUEUE` / `_LOG_JSON` / `_LOG_DIAGNOSE`

### Changed

- **`configure_logging()` 新增 keyword-only 參數**: `enqueue`、`json_output`、`diagnose`、`env_prefix`；委派給 `SinkManager` 管理 sink 生命週期
- **`diagnose=False` 為生產預設**: 防止 exception traceback 洩漏 Modbus 位址、Redis 密碼等敏感資訊
- **`set_level()` 不再重建 Sink**: 改更新 `LogFilter` dict，即時生效無 I/O 開銷
- **`csp_lib/core/logging/` 子套件**: 日誌邏輯拆分至子套件，`csp_lib.core` 頂層 `__all__` 保持向後相容

詳細 API 文件：[[Logging]]

---

## [0.6.0] - 2026-04-03

### Added

- **`BatchUploader` Protocol** (`csp_lib.manager.base`): `@runtime_checkable` Protocol，提供 `register_collection()` + `enqueue()` 介面，解耦 [[DataUploadManager]] 與 `StatisticsManager` 對具體 [[MongoBatchUploader]] 的直接依賴
- **`DOMode` 列舉** (`csp_lib.equipment.device.action`): `PULSE`、`SUSTAINED`、`TOGGLE` — 三種離散輸出動作模式
- **`DOActionConfig` frozen dataclass**: 宣告式 DO 動作配置
- **`Actionable` Protocol**: `@runtime_checkable`，統一 ET7050/ET7051 與 PCS/BMS 設備的 DO 控制介面
- **[[AsyncModbusDevice]] DO action 方法**: `configure_do_actions()`、`execute_do_action()`、`available_do_actions`、`cancel_pending_pulses()`
- **`CapabilityRequirement` dataclass** (`csp_lib.integration.schema`): `capability`、`min_count`、`trait_filter` — 供 preflight validation 使用
- **`AggregationResult` dataclass**: `value`、`device_count`、`expected_count`、`quality_ratio` — 聚合品質元資料
- **[[CapabilityContextMapping]]`.min_device_ratio`**: 可選比例門檻
- **[[DeviceRegistry]]`.validate_capabilities(requirements)`**: 回傳未滿足需求的可讀訊息列表
- **[[SystemController]]`.preflight_check()`**: 驗證已註冊的能力需求
- **`SystemControllerConfigBuilder`**: `require_capability()` 和 `strict_capability()` fluent 方法
- **Repository Protocol 拆分**: [[AlarmPersistenceManager|AlarmRepository]]、`CommandRepository`、`ScheduleRepository` Protocol 無需安裝 `motor` 即可匯入

### Changed

- **`AlarmRecord.occurred_at` → `timestamp`**: 統一時間戳欄位命名
- **`AlarmRecord.resolved_at` → `resolved_timestamp`**: 對稱重新命名
- **`WriteCommand.created_at` → `timestamp`**: 統一指令類型時間戳
- **`ActionCommand.created_at` → `timestamp`**: 與 WriteCommand 一致
- **`CommandRecord.created_at` → `timestamp`**: 與告警 schema 統一
- **[[DataUploadManager]] 建構子型別**: 接受 `BatchUploader`（Protocol）取代 `MongoBatchUploader`
- **`UnifiedConfig.mongo_uploader`**: 型別從 `MongoBatchUploader` 放寬為 `BatchUploader`

### Fixed

- **靜默低容量聚合**: 設定 `min_device_ratio` 的 [[CapabilityContextMapping]] 現在會在響應設備不足時發出警告並回傳 `default`

> [!info] 遷移指南
> 時間戳欄位更名需要 MongoDB 遷移，詳見 [[v0.6.0_timestamp_rename|v0.6.0 遷移指南]]

---

## [0.5.2] - 2026-04-02

### Added

- **DroopStrategy 測試**: 38 test cases
- **RampStopStrategy 測試**: 11 test cases
- **CommandProcessor pipeline 測試**: 3 test cases
- **SystemControllerConfigBuilder 測試**: 11 test cases
- **WriteRule (Gateway) 測試**: 15 test cases
- **FFTableRepository 測試**: 17 test cases
- **PowerCompensator 補充測試**: 10 test cases
- **Root conftest.py 共用 fixture**: `make_mock_device`、`mock_strategy`、`mock_registry`
- **pytest-xdist 平行測試**: 啟用 `addopts = "-n auto"`，測試時間從 120s 降至 ~48s

### Fixed

- **AlarmRecord.alarm_code 未寫入 MongoDB**: `_on_alarm_triggered` 和 `_on_disconnected` 建立 AlarmRecord 時漏設 `alarm_code`

### Changed

- **DeviceStateSubscriber log 等級修正**: Redis 讀取失敗 log 從 `debug` 升至 `warning`
- **DeprecationWarning 過濾收窄**: 只過濾已知第三方（pymodbus、motor、redis）

---

## [0.5.1] - 2026-04-01

### Changed

- **錯誤階層擴充**: 新增 `StrategyExecutionError`、`ProtectionError`、`DeviceRegistryError` 結構化例外
- **ModbusError 上下文**: 子類別攜帶 `address`、`unit_id`、`function_code` 欄位
- **Modbus 連線生命週期 log**: connect / disconnect / reconnect 以 INFO 記錄
- **靜默失敗修復**: `aggregator`、`base`、`scheduler` 不再靜默吞掉錯誤
- **Logger 命名統一**: 29 個檔案統一使用 `__name__`
- **[[DeviceRegistry]] 並發安全**: 加 `threading.Lock` 保護讀寫操作
- **[[DeviceEventEmitter]] 優雅關閉**: stop() drain queue + handler 完成等待
- **Device 重複註冊檢查**: register() 和 register_group() 檢查 duplicate device_id
- **[[CircuitBreaker]] 指數退避**: 加 `max_cooldown`、`backoff_factor` 參數

### Added

- **WeakRef event listener**: `on(event, handler, weak=True)` 支援弱引用 handler，GC 後自動清理

---

## [0.5.0] - 2026-03-31

### Added

- **[[RuntimeParameters]]** (`csp_lib.core.runtime_params`): Thread-safe 即時參數容器
  - 支援 `get` / `set` / `update` / `snapshot` / `delete` / `setdefault` 操作
  - Observer pattern：`on_change(callback)` 在值變更時觸發通知
  - 以 `threading.Lock` 保護，Modbus hook thread 與 asyncio event loop 之間安全存取
- **CommandProcessor Protocol** (`csp_lib.controller.core.processor`): Post-Protection 命令處理器
  - `@runtime_checkable Protocol`，定義 `async def process(command, context) -> Command`
  - `SystemControllerConfig` 新增 `post_protection_processors` 欄位
- **DroopStrategy** (`csp_lib.controller.strategies`): 標準下垂一次頻率響應策略
  - `DroopConfig` 可配置下垂係數、死區寬度、基準頻率、最大 AFC 功率
  - `context.extra` 無頻率資料時維持上一次命令（fail-safe hold）
- **PowerCompensator** (`csp_lib.controller.compensator`): 前饋 + 積分閉環功率補償器
  - 實作 `CommandProcessor` Protocol
  - FF table 查表 + 積分修正（deadband、anti-windup、rate limiting）
  - 穩態自動學習：I 項貢獻吸收進 FF 表
  - FF 表持久化支援 `FFTableRepository` Protocol（JSON / MongoDB）
- **FFCalibrationStrategy** (`csp_lib.controller.calibration`): FF Table 步階校準策略
  - 狀態機：IDLE → STEPPING → DONE
  - 支援 `on_complete` callback
- **動態保護規則** (`csp_lib.controller.system`):
  - `DynamicSOCProtection`：從 [[RuntimeParameters]] 讀取動態 SOC 參數
  - `GridLimitProtection`：外部功率限制保護
  - `RampStopProtection`：故障/告警時斜坡降功率（已標記 deprecated，建議改用 `RampStopStrategy`）
- **RampStopStrategy** (`csp_lib.controller.strategies`): 斜坡降功率策略，替代 `RampStopProtection`
- **[[StrategyContext]]`.params`**: 新增 `params: RuntimeParameters | None` 欄位
- **ModbusGatewayServer** (`csp_lib.modbus_gateway`): 完整 Modbus TCP Gateway Server 模組
  - 宣告式 register map、write validation chain、data sync sources、watchdog

---

## [0.4.2] - 2026-03-06

### Added

- **CAN 層** (`csp_lib.can`): CAN Bus 通訊層，與 Modbus 層並列
  - [[CANBusConfig]]: CAN Bus 連線配置（interface, channel, bitrate）
  - [[CANFrame]]: CAN 幀資料結構
  - [[AsyncCANClientBase]]: CAN 客戶端 ABC
  - [[PythonCANClient]]: 基於 `python-can>=4.0` 的非同步實作
  - 例外：`CANError`, `CANConnectionError`, `CANTimeoutError`, `CANSendError`
  - 新增 optional dependency: `csp_lib[can]`
- **CAN 設備支援** (`csp_lib.equipment.device`):
  - [[AsyncCANDevice]]: CAN 設備類別，與 [[AsyncModbusDevice]] 共用事件系統
  - [[CANRxFrameDefinition]]: 宣告式 RX 幀映射定義
  - [[CANEncoder]]: CAN 幀編碼器（`csp_lib.equipment.processing`）
  - [[PeriodicSendScheduler]]: 週期 CAN 幀發送排程（`csp_lib.equipment.transport`）
  - [[DeviceProtocol]]: `@runtime_checkable` 通用設備介面，統一 Modbus 與 CAN 設備的存取
- **Core 韌性模組** (`csp_lib.core`): 通用韌性元件從 Modbus 層提升至 Core
  - [[CircuitBreaker]]: 通用斷路器（CLOSED → OPEN → HALF_OPEN 狀態轉換）
  - [[CircuitState]]: 斷路器狀態列舉（`CLOSED`, `OPEN`, `HALF_OPEN`）
  - [[RetryPolicy]]: 指數退避重試策略配置
- **Controller 新策略** (`csp_lib.controller.strategies`):
  - [[LoadSheddingStrategy]]: 階段性負載卸載策略（適用離網/孤島場景）
  - [[LoadSheddingConfig]]: 負載卸載策略配置
  - `LoadCircuitProtocol`: 負載迴路控制 Protocol
  - `ShedCondition`: 卸載觸發條件 Protocol
  - `ShedStage`: 卸載階段定義
  - `ThresholdCondition`: 閾值條件（內建）
  - `RemainingTimeCondition`: 剩餘時間條件（內建）
- **Controller 事件驅動覆蓋** (`csp_lib.controller.system`):
  - [[EventDrivenOverride]]: `@runtime_checkable Protocol`，條件驅動的自動 push/pop override
  - [[AlarmStopOverride]]: 告警自動停機（取代硬編碼的 `_handle_auto_stop()`）
  - [[ContextKeyOverride]]: 通用 context key 觸發的 override
  - [[SwitchSource]]: 模式切換來源列舉（`MANUAL`, `SCHEDULE`, `EVENT`, `INTERNAL`）
- **Controller 策略發現** (`csp_lib.controller.discovery`):
  - `discover_strategies()`: 透過 Python entry_points 動態發現外部策略
  - `StrategyDescriptor`: 策略描述符
  - `ENTRY_POINT_GROUP`: entry point 群組常數
- **Integration 功率分配器** (`csp_lib.integration.distributor`):
  - [[PowerDistributor]]: 功率分配器抽象基類
  - [[EqualDistributor]]: 均等分配策略
  - [[ProportionalDistributor]]: 按比例分配策略
  - [[SOCBalancingDistributor]]: 依 SOC 平衡分配策略
  - [[DeviceSnapshot]]: 設備快照資料類別
- **Integration 心跳服務** (`csp_lib.integration.heartbeat`):
  - [[HeartbeatService]]: 心跳寫入服務，支援 [[HeartbeatMode]]（TOGGLE/INCREMENT/CONSTANT）
- **Integration Schema 新增** (`csp_lib.integration.schema`):
  - [[CapabilityContextMapping]]: Capability-driven context mapping
  - [[CapabilityCommandMapping]]: Capability-driven command mapping
  - [[HeartbeatMapping]]: 心跳映射定義
  - [[HeartbeatMode]]: 心跳模式列舉
- **Integration 分散式控制** (`csp_lib.integration.distributed`):
  - `DistributedConfig`, `RemoteSiteConfig`: 分散式配置
  - `DeviceStateSubscriber`, `RemoteCommandRouter`: 跨站點通訊
  - `DistributedController`, `RemoteSiteRunner`: 分散式控制器
- **Equipment Capability 系統** (`csp_lib.equipment.device.capability`):
  - `Capability`, `CapabilityBinding`: 設備能力定義與綁定
  - 內建能力常數：`HEARTBEAT`, `ACTIVE_POWER_CONTROL`, `REACTIVE_POWER_CONTROL`, `SWITCHABLE`, `LOAD_SHEDDABLE`, `MEASURABLE`, `FREQUENCY_MEASURABLE`, `VOLTAGE_MEASURABLE`, `SOC_READABLE`
- **Equipment EventBridge** (`csp_lib.equipment.device.event_bridge`):
  - `AggregateCondition`, `EventBridge`: 設備事件橋接，條件觸發跨設備事件
- **Modbus 請求佇列增強** (`csp_lib.modbus.clients`):
  - [[ModbusRequestQueue]]: 優先序非同步請求佇列，內建斷路器防護
  - `RequestQueueConfig`: 佇列配置
  - `RequestPriority`: 請求優先等級列舉
  - `CircuitBreakerState`: Modbus 客戶端斷路器狀態
  - 新例外：`ModbusCircuitBreakerError`, `ModbusQueueFullError`
- **Manager 排程服務** (`csp_lib.manager.schedule`):
  - [[ScheduleService]], `ScheduleServiceConfig`: 排程服務（透過 [[ScheduleModeController]] 驅動模式切換）
  - `ScheduleRepository`, `MongoScheduleRepository`: 排程儲存
  - `ScheduleRule`, `ScheduleType`: 排程規則定義
  - `StrategyFactory`, `StrategyType`: 策略工廠
- **Controller 排程模式協定** (`csp_lib.controller.system`):
  - [[ScheduleModeController]]: `@runtime_checkable Protocol`，橋接 ScheduleService (L5) 與 SystemController (L6)，定義 `activate_schedule_mode()` / `deactivate_schedule_mode()` 介面

- **動態點位管理** (`csp_lib.equipment.device`):
  - `ReconfigureSpec`: frozen dataclass，指定要替換的組件（`always_points`、`rotating_points`、`write_points`、`alarm_evaluators`、`capability_bindings`）
  - `PointInfo`: frozen dataclass，點位詳細資訊（name、address、data_type、direction、enabled、read_group、metadata）
  - [[AsyncModbusDevice]]`.reconfigure(spec)`: 執行期動態重新配置，保留告警狀態，自動清理失效的停用點位
  - [[AsyncModbusDevice]]`.restart()`: 重啟讀取迴圈，發出 `restarted` 事件
  - 點位開關：`disable_point()`、`enable_point()`、`is_point_enabled()`、`disabled_points` property
  - 點位查詢：`read_points`、`rotating_read_points`、`write_point_names`、`all_point_names`、`get_point_info()`
  - 3 個新事件：`reconfigured` / `restarted` / `point_toggled`（含對應 Payload 類別）
- **ReadScheduler 動態更新** (`csp_lib.equipment.transport`):
  - [[ReadScheduler]]`.update_groups()`: 動態更新分組，更新輪替組時自動重置索引
- **AlarmStateManager 狀態遷移** (`csp_lib.equipment.alarm`):
  - [[AlarmStateManager]]`.export_states()` / `.import_states()`: 重配置時跨管理器遷移告警狀態

### Changed

- **Integration DeviceRegistry** (`csp_lib.integration.registry`): 加入 Capability-based 查詢，支援以 Capability 查找設備
- **Integration ContextBuilder** (`csp_lib.integration.context_builder`): 支援 [[CapabilityContextMapping]]，自動解析設備 capability slot
- **Integration CommandRouter** (`csp_lib.integration.command_router`): 支援 [[CapabilityCommandMapping]]，per-device 路由模式
- **Integration SystemController** (`csp_lib.integration.system_controller`): 支援 [[EventDrivenOverride]] 清單，替代硬編碼的 auto-stop 邏輯
- **Controller ModeManager** (`csp_lib.controller.system.mode`): 加入 `SwitchSource` 審計欄位；新增 `update_mode_strategy()`（原子策略替換）、`async_unregister()`（含生命週期的非同步移除）；`add_base_mode()` / `remove_base_mode()` 新增 `source` 參數
- **Integration SystemController** 實作 [[ScheduleModeController]] Protocol：新增 `activate_schedule_mode()` 與 `deactivate_schedule_mode()` 方法
- **Modbus DynamicInt/DynamicUInt** (`csp_lib.modbus.types.dynamic`): 型別驗證強化
- **Modbus ModbusString** (`csp_lib.modbus.types.numeric`): 解碼錯誤處理改善
- **Manager AlarmRepository** (`csp_lib.manager.alarm.repository`): 介面更新
- **Manager CommandRepository** (`csp_lib.manager.command.repository`): 新增 `ActionCommand` 支援
- **Manager ScheduleRepository** (`csp_lib.manager.schedule.repository`): 新增排程查詢方法

### Breaking Changes

> [!warning] Breaking Change
> v0.4.2 為 minor 版本，允許破壞性變更（pre-1.0 語義）。

- **ScheduleService 建構子** (`csp_lib.manager.schedule.service`): `schedule_strategy: ScheduleStrategy` 參數改為 `mode_controller: ScheduleModeController`。原本直接傳入排程策略實例；新版傳入實作 [[ScheduleModeController]] Protocol 的控制器（通常為 `SystemController`）。策略的建立與切換現由服務內部透過 `ScheduleModeController` 介面完成，走 `ModeManager` 正規生命週期路徑。

  ```python
  # 舊版（v0.3.x）
  service = ScheduleService(
      config=..., repository=..., factory=...,
      schedule_strategy=schedule_strategy,
  )

  # 新版（v0.4.2）
  service = ScheduleService(
      config=..., repository=..., factory=...,
      mode_controller=system_controller,   # 實作 ScheduleModeController
  )
  ```

### Tests

- 新增動態點位管理測試（49 tests）：`test_scheduler_update.py`（9）、`test_point_toggle.py`（17）、`test_device_reconfigure.py`（23）
- 新增 CAN 設備測試（`tests/can/`, `tests/equipment/test_can_device.py`）
- 新增 Controller 測試：`test_event_override.py`, `test_load_shedding.py`
- 新增 Integration 測試：`test_command_router_per_device.py`, `test_distributor.py`, `test_event_override_integration.py`, `test_registry_metadata.py`
- 新增 Modbus 佇列測試（`tests/modbus/test_queue.py`）

---

## [0.3.3] - 2026-02-16

### Added
- **integration 模組** (`csp_lib.integration`): Equipment-Controller 整合層
  - [[DeviceRegistry]]: Trait-based 設備查詢索引
  - [[ContextBuilder]]: 設備值 -> [[StrategyContext]] 映射（支援多設備聚合）
  - [[CommandRouter]]: [[Command]] -> 設備寫入路由（支援廣播寫入）
  - [[DeviceDataFeed]]: 設備 read_complete 事件 -> [[PVDataService]] 餵入
  - [[GridControlLoop]]: 完整控制迴圈編排器（[[AsyncLifecycleMixin]]）
  - [[AggregateFunc]] / [[ContextMapping]] / [[CommandMapping]] / [[DataFeedMapping]] 宣告式映射 schema
- [[AsyncLifecycleMixin]] (`csp_lib.core`): 通用 async 生命週期管理
- [[DeviceEventSubscriber]] (`csp_lib.manager`): 設備事件訂閱基底類別

### Changed
- 重構管理器使用新基底類別（[[AlarmPersistenceManager]]、[[DataUploadManager]]、[[StateSyncManager]] -> [[DeviceEventSubscriber]]；[[DeviceManager]]、[[UnifiedDeviceManager]]、[[RedisCommandAdapter]] -> [[AsyncLifecycleMixin]]）

### Tests
- 新增 integration 模組測試（94 個測試）
- 新增 [[AsyncLifecycleMixin]] 單元測試
- 新增 core transform 綜合測試

---

## [0.3.2] - 2026-01-18

（版本號碼遞增，無功能變更）

---

## [0.3.1] - 2026-01-18

### Added
- **manager 模組** (`csp_lib.manager`): 系統整合管理層
  - [[AlarmPersistenceManager]] / [[MongoAlarmRepository]]
  - [[DeviceManager]] / [[DeviceGroup]]
  - [[DataUploadManager]]
  - [[WriteCommandManager]] / [[MongoCommandRepository]]
  - [[StateSyncManager]]
  - [[UnifiedDeviceManager]] / [[UnifiedConfig]]
- **redis 模組** (`csp_lib.redis`): Async Redis 客戶端（含 TLS / Sentinel）
- Equipment 增強: [[PowerFactorTransform]]、read_once、自動重連、[[GroupReader]] 並行讀取、CAN frame 解析器、高階 action 支援、模擬模組
- Controller 增強: [[GridControllerProtocol]]、新控制策略、ActionCommand schema

### Changed
- Modbus: unit_id 從連線設定移至請求方法
- 全面使用 UTC 時區感知 datetime
- 策略生命週期 hooks 改為 async

### Fixed
- [[PointGrouper]] 狀態重置問題
- [[AlarmLevel]] 使用修正

---

## [0.3.0] - 2026-01-13

### Added
- **equipment 模組** (`csp_lib.equipment`): 設備抽象層
  - 資料轉換: [[ScaleTransform]]、[[RoundTransform]]、[[EnumMapTransform]]、[[ClampTransform]]、[[BoolTransform]]、[[InverseTransform]]、[[BitExtractTransform]]、[[ByteExtractTransform]]、[[MultiFieldExtractTransform]]
  - [[ProcessingPipeline]]: 轉換鏈管線
  - [[ReadPoint]] / [[WritePoint]] 定義
  - 告警系統: [[AlarmDefinition]]、[[BitMaskAlarmEvaluator]]、[[ThresholdAlarmEvaluator]]、[[TableAlarmEvaluator]]、[[AlarmStateManager]]（含遲滯邏輯）
  - 傳輸層: [[PointGrouper]]、[[GroupReader]]、[[ReadScheduler]]、[[ValidatedWriter]]
  - [[AsyncModbusDevice]]: 核心設備類別（週期讀取、連線管理、事件、告警）
  - [[DeviceConfig]] / [[DeviceEventEmitter]]
- CI/CD: trusted publishing + attestations

---

## [0.2.1] - 2026-01-11

### Fixed
- Modbus 共用客戶端資源引用計數修正（防止 connect() 重複呼叫時的計數錯誤）

---

## [0.2.0] - 2026-01-11

### Added
- **modbus 模組** (`csp_lib.modbus`): Modbus 通訊層
  - 資料型別: [[Int16]] / [[UInt16]] / [[Int32]] / [[UInt32]] / [[Int64]] / [[UInt64]] / [[Float32]] / [[Float64]] / [[ModbusString]]
  - [[ModbusCodec]]: 編解碼 API（支援 byte order / register order）
  - Async 客戶端: [[PymodbusTcpClient]]、[[PymodbusRtuClient]]、[[SharedPymodbusTcpClient]]
  - [[ModbusTcpConfig]] / [[ModbusRtuConfig]]
  - 自訂例外階層

---

## [0.1.1] - 2026-01-10

### Added
- Cython 編譯模組的 .pyi stub 自動產生
- GitHub Release 產物附加
- 二進位發佈的程式碼保護

---

## [0.1.0] - 2026-01-10

### Added
- **core 模組** (`csp_lib.core`): loguru 集中式 logging（get_logger / set_level / configure_logging）
- **mongo 模組** (`csp_lib.mongo`): Async MongoDB 批次上傳（[[MongoConfig]] / 批次佇列 / 上傳器）
- **controller 模組** (`csp_lib.controller`): 控制策略框架（[[Strategy]] / [[StrategyExecutor]] / [[PVDataService]]）
- CI/CD: GitHub Actions（PR lint+test / tag build+publish）
- Cython 二進位 wheel 建置（build_wheel.py）
- 套件更名為 csp0924_lib

---

## 相關頁面

- [[_MOC Reference]] - 參考索引
- [[CI-CD Pipeline]] - CI/CD 流程
