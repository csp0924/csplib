# Changelog

本專案的所有重要變更皆記錄於此檔案。

格式基於 [Keep a Changelog](https://keepachangelog.com/)，版本號遵循 [Semantic Versioning](https://semver.org/)。

## [Unreleased]

## [0.5.1] - 2026-04-01
### Changed
- **錯誤階層擴充**: 新增 `StrategyExecutionError`、`ProtectionError`、`DeviceRegistryError` 結構化例外，取代裸 `RuntimeError` / `ValueError`
- **ModbusError 上下文**: `ModbusError` 子類別攜帶 `address`、`unit_id`、`function_code` 欄位，方便上層快速分類
- **Modbus 連線生命週期 log**: connect / disconnect / reconnect 事件統一以 INFO 等級記錄，含連線參數與耗時
- **Writer log 等級修正**: `ValidatedWriter` 寫入成功 log 從 DEBUG 降至 TRACE，減少正常運行時的 log 雜訊
- **靜默失敗修復**: `aggregator`、`base`、`scheduler` 捕獲例外後改為 `logger.error()` 並重新拋出或回傳預設值，不再靜默吞掉錯誤
- **Logger 命名統一**: 29 個檔案的 `get_logger()` 呼叫統一使用 `__name__`，確保 log 層級控制與過濾一致
- **WriteRejectedError 結構化 log** (`csp_lib.modbus_gateway.pipeline`): Validator 與 WriteRule 拒絕寫入時改用 `WriteRejectedError` 格式化訊息，log 等級從 DEBUG 升至 WARNING
- **Strategy Executor 錯誤上下文**: 策略執行失敗時 log 含 strategy name、SOC、context extra keys，修復潛在 UnboundLocalError
- **Device 事件處理 log**: `_process_values()` 和 alarm 評估例外不再靜默，加 warning log 含 device_id 和 point 上下文
- **ContextBuilder 映射失敗上下文**: transform/aggregate 失敗 log 含 mapping source、point_name、target field
- **Alarm Evaluator log**: `evaluator.py` 新增 logger，告警觸發/解除以 DEBUG 記錄；`mixins.py` 寫入成功 INFO → DEBUG
- **Cluster 例外鏈**: `sync.py`、`election.py` 所有 `except Exception` 加 `as e` 捕獲 + 重試/狀態上下文
- **loguru exception() 審計**: 可恢復錯誤從 `logger.exception()`（ERROR）改為 `logger.opt(exception=True).warning()`
- **DeviceRegistry 並發安全** (`csp_lib.integration.registry`): 加 `threading.Lock` 保護所有讀寫操作，防止並發修改崩潰
- **DeviceEventEmitter 優雅關閉** (`csp_lib.equipment.device.events`): stop() 改為 drain queue + handler 完成等待；emit() 未啟動時不入隊；handler 迭代前 copy 防並發修改
- **Device 重複註冊檢查** (`csp_lib.manager.device.manager`): register() 和 register_group() 檢查 duplicate device_id
- **DeviceConfig 驗證加強**: `reconnect_interval <= 0` 拒絕（防止 tight loop）
- **WriteRule 驗證加強**: `min_value > max_value` 拒絕
- **Redis Sentinel disconnect**: `disconnect()` 時釋放 `_sentinel` 引用，防止 Sentinel 連線洩漏
- **NotificationBatcher flush retry**: `_on_stop()` flush 失敗時重試一次，記錄 dropped notification 數量
- **CircuitBreaker 指數退避**: 加 `max_cooldown`、`backoff_factor` 參數，故障恢復時加 jitter 防止 thundering herd
- **ModbusRequestQueue 清理 log**: `stop()` 加 cancelled/done futures summary log
- **Device 狀態 asyncio.Lock** (`csp_lib.equipment.device.base`): `_status_lock` 保護 responsive/failure 狀態更新，防止並發競態
- **UnifiedDeviceManager 註冊 threading.Lock**: `_register_lock` 防止並發註冊重複訂閱
- **StatisticsEngine 去重**: `register_power_sum_devices()` 去重防止累計值翻倍
- **DataFeed attach 回滾**: `attach()` 部分失敗時回滾已訂閱的 handler，防止洩漏
- **Heartbeat point 驗證**: `_on_start()` 時驗證 heartbeat point 在目標設備上是否存在

### Added
- **WeakRef event listener** (`csp_lib.equipment.device.events`): `on(event, handler, weak=True)` 支援弱引用 handler，GC 後自動清理

## [0.5.0] - 2026-03-31
### Added
- **RuntimeParameters** (`csp_lib.core.runtime_params`): Thread-safe 即時參數容器
  - 支援 `get` / `set` / `update` / `snapshot` / `delete` / `setdefault` 操作
  - Observer pattern：`on_change(callback)` 在值變更時觸發通知（在鎖外同步呼叫）
  - 以 `threading.Lock` 保護，Modbus hook thread 與 asyncio event loop 之間安全存取
  - 適用於需從外部系統（EMS / Modbus / Redis）即時推送的參數（如 SOC 上下限、功率限制）
- **CommandProcessor Protocol** (`csp_lib.controller.core.processor`): Post-Protection 命令處理器
  - `@runtime_checkable Protocol`，定義 `async def process(command, context) -> Command` 介面
  - 插入於 `ProtectionGuard` 與 `CommandRouter` 之間，支援功率補償、命令日誌、審計追蹤
  - `SystemControllerConfig` 新增 `post_protection_processors` 欄位以組合多個處理器
- **DroopStrategy** (`csp_lib.controller.strategies.droop_strategy`): 標準下垂一次頻率響應策略
  - 根據頻率偏差透過下垂公式計算功率：`gain = 100 / (f_base × droop)`
  - `DroopConfig` 可配置下垂係數、死區寬度、基準頻率、最大 AFC 功率與執行週期
  - 支援 `schedule_p + dreg_power` 疊加，自動 clamp 於額定功率範圍
  - `context.extra` 無頻率資料時維持上一次命令（fail-safe hold）
- **PowerCompensator** (`csp_lib.controller.compensator`): 前饋 + 積分閉環功率補償器
  - 實作 `CommandProcessor` Protocol，可直接加入 `post_protection_processors`
  - 前饋表（FF table）按功率區間查表，補償 PCS 非線性與輔電損耗
  - 積分修正含 deadband、anti-windup、rate limiting
  - 穩態自動學習：I 項貢獻吸收進 FF 表，長期自適應
  - 暫態閘門：setpoint 變更後等 PCS 到位才啟動積分
  - FF 表持久化支援 `FFTableRepository` Protocol（可注入 JSON / MongoDB 等後端）
  - `PowerCompensator.async_init()` 支援 async repository（如 MongoDB）啟動後載入
  - `SystemController._on_start()` 自動呼叫 processors 的 `async_init()`
- **動態保護規則** (`csp_lib.controller.system.dynamic_protection`): 從 RuntimeParameters 讀取動態參數
  - `DynamicSOCProtection`：每次 `evaluate()` 從 `RuntimeParameters` 讀取 `soc_max` / `soc_min`，支援 EMS 即時更新
  - `GridLimitProtection`：外部功率限制保護（電力公司 / 排程上限）
  - `RampStopProtection`：故障 / 告警時斜坡降功率至 0（graceful ramp-down）；已標記 deprecated，建議改用 `RampStopStrategy`
- **RampStopStrategy** (`csp_lib.controller.strategies.ramp_stop`): 斜坡降功率策略
  - 替代 `RampStopProtection`，本質上是「接管控制」而非「修改數值」，更適合作為 Strategy
  - 使用實際 dt（monotonic clock）計算每步降幅，不依賴固定 interval
  - 搭配 `EventDrivenOverride` + `ModeManager(PROTECTION)` 使用
  - 不同停止原因可觸發不同策略：通訊中斷 → `RampStopStrategy`，告警 → `StopStrategy`
- **FFCalibrationStrategy** (`csp_lib.controller.calibration`): FF Table 步階校準策略
  - 維護型一次性操作（類似 SOC 校正），自動遍歷各功率 bin 量測 FF ratio
  - 狀態機：IDLE → STEPPING → DONE，完成後寫入 `PowerCompensator` FF Table
  - 支援 `on_complete` callback，可配合 `RuntimeParameters` 或 Redis 觸發
  - `FFCalibrationConfig` 可配置步幅、穩態門檻、settle wait 等
- **FFTableRepository Protocol** (`csp_lib.controller.compensator`): FF Table 持久化介面
  - `JsonFFTableRepository`：JSON 檔案持久化（預設，向後相容）
  - `MongoFFTableRepository`：MongoDB 持久化（async save + async_load）
  - `PowerCompensator` 新增 `repository` 參數，可注入任意後端
  - `PowerCompensator.load_ff_table(table)` 方法供外部校準或 async load 使用
- **StrategyContext.params** (`csp_lib.controller.core.context`): 系統參數直接引用
  - 新增 `params: RuntimeParameters | None` 欄位，區隔系統參數（EMS 指令）與設備讀值（extra）
  - `SystemControllerConfig` 新增 `runtime_params` 欄位，`ContextBuilder` 自動注入
  - 向後相容：`params=None` 為預設值，不影響現有使用 extra 的程式碼
- **ModbusGatewayServer** (`csp_lib.modbus_gateway`): 完整 Modbus TCP Gateway Server 模組
  - 宣告式暫存器映射（`GatewayRegisterDef`），支援 HR（Holding）/ IR（Input）分區
  - Write validation chain：`AddressWhitelistValidator`、composable `WriteRule` Protocol（見下方）
  - Write hooks：`RedisPublishHook`、`CallbackHook`、`StatePersistHook`
  - 資料同步來源：`RedisSubscriptionSource`、`PollingCallbackSource`
  - 通訊 watchdog：含 timeout / recovery 回呼（`CommunicationWatchdog`）
  - Thread-safe pymodbus 整合，含 asyncio bridge
  - `ModbusGatewayServer` 實作 `AsyncLifecycleMixin`，透過 `async with` 管理完整生命週期
- **WriteRule Protocol** (`csp_lib.modbus_gateway.protocol`): 可組合寫入規則介面
  - `apply(register_name, value) -> (value, rejected)` 簽名，支援值轉換與拒絕
  - **RangeRule**: 連續範圍驗證，支援 clamp / reject 模式（取代原 `WriteRule` dataclass）
  - **AllowedValuesRule**: 離散值白名單（如模式暫存器只接受 `{0, 1, 3, 7}`）
  - **StepRule**: 步進量化（如 `step=0.5` 對齊 0.5 kW 解析度），永不拒絕
  - **CompositeRule**: 串接多個 rule 依序套用，任一拒絕即短路
- **SystemControllerConfigBuilder** (`csp_lib.integration.system_controller`): Fluent builder
  - `SystemControllerConfig.builder()` 回傳 builder 物件，支援鏈式呼叫
  - `.map_context()` / `.map_command()` / `.protect()` / `.processor()` / `.params()` 等方法
  - 不破壞現有 dataclass 直接建構方式（純加法）

### Changed
- **DRegStrategy → DroopStrategy** (`csp_lib.controller.strategies.droop_strategy`): 重新命名
  - `DRegConfig` → `DroopConfig`，`DRegStrategy` → `DroopStrategy`
  - `max_dreg_power` → `max_droop_power`，檔案 `dreg_strategy.py` → `droop_strategy.py`
- **StrategyContext** (`csp_lib.controller.core.context`): 新增 `params` 欄位（`RuntimeParameters | None`）
  - 系統參數與設備讀值分離：`params` 放 EMS 指令/保護設定，`extra` 放頻率/功率等設備讀值
  - `ContextBuilder` 新增 `runtime_params` 參數，build 時自動注入
- **SOCBalancingDistributor** (`csp_lib.integration.distributor`): 新增個別設備功率上限參數
  - `per_device_max_p` 與 `per_device_max_q`：對各設備的輸出做硬體 clamp
  - 四次算法：clamp → 溢出重分配 → 再次 clamp → 二次溢出按剩餘 headroom 分配，確保總容量足夠時不會少分配
- **RedisClient** (`csp_lib.redis.client`): 功能擴充
  - `TLSConfig.ca_certs` 改為 Optional（`cert_reqs="none"` 時可不提供 CA 憑證）
  - 新增 `pubsub()` 方法，回傳 redis-py PubSub 實例以供 Pub/Sub 操作
  - 新增 `scan()` 方法，支援增量 key 掃描（cursor-based iteration）
- **WritePipeline** (`csp_lib.modbus_gateway.pipeline`): 寫入規則改用 `WriteRule` Protocol
  - `_apply_rule` 簡化為委派 `rule.apply()`，不再內建 min/max/clamp 邏輯
  - `write_rules` 參數型別從 `Sequence[WriteRule]` 改為 `Mapping[str, WriteRule]`（name → rule 映射）

### Fixed
- **SOCBalancingDistributor** (`csp_lib.integration.distributor`): 修復 clamp 溢出重分配後二次溢出被丟棄的問題
  - 當 Pass 2 重分配導致新設備超限時，Pass 3 re-clamp 產生的溢出未被分配，造成總功率不足
  - 新增 Pass 4：二次溢出按剩餘 headroom 分配給未飽和設備，確保總容量足夠時功率守恆

### Deprecated
- **RampStopProtection** (`csp_lib.controller.system.dynamic_protection`): 建議改用 `RampStopStrategy` + `EventDrivenOverride`
  - RampStop 本質上是「接管控制」而非「修改數值」，更適合作為 Strategy
  - `RampStopProtection` 保留但不再建議使用

## [0.4.3] - 2026-03-16

* fix: hot fix cluster dependency problem.

* feat: add wheel installation with extras and import verification

## [0.4.2] - 2026-03-13

### Changed
- **Build**: 移除 Cython build pipeline，改為純 Python 發佈 (#25)
- **CI/CD**: 新增版本自動化、品質門檻、release workflow (#22)
- **CI/CD**: 新增 pytest-xdist 平行測試執行與 asyncio auto mode (#24)

### Fixed
- **Modbus Request Queue**: 修復 worker 信號遺失（clear 後 re-check total_size）和 submit TOCTOU（size 檢查移入 lock 內）(#19, #20)
- **StrategyExecutor**: 修復 PopOverride bypass 後 executor 卡在 triggered mode 無法恢復的問題 (#18)
- **Type Safety**: 修復 11 個檔案共 45 個 mypy type errors (#23)

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
