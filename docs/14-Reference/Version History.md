---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: ">=0.4.2"
---

# 版本歷史

本專案的所有重要變更皆記錄於此。格式基於 [Keep a Changelog](https://keepachangelog.com/)，版本號遵循 [Semantic Versioning](https://semver.org/)。

---

## [0.6.0] - 2026-04-03

### Added

- **`BatchUploader` Protocol** (`csp_lib.manager.base`): `@runtime_checkable` Protocol，提供 `register_collection()` + `enqueue()` 介面，解耦 [[DataUploadManager]] 與 `StatisticsManager` 對具體 `MongoBatchUploader` 的直接依賴
- **`DOMode` 列舉** (`csp_lib.equipment.device.action`): `PULSE`、`SUSTAINED`、`TOGGLE` — 三種離散輸出動作模式
- **`DOActionConfig` frozen dataclass** (`csp_lib.equipment.device.action`): 宣告式 DO 動作配置，含 `point_name`、`label`、`mode`、`pulse_duration`、`on_value`、`off_value`
- **`Actionable` Protocol** (`csp_lib.equipment.device.action`): `@runtime_checkable` Protocol，公開 `available_do_actions` + `execute_do_action(label)` — 統一 ET7050/ET7051 與 PCS/BMS 設備的 DO 控制介面
- **[[AsyncModbusDevice]] DO 動作支援**:
  - `configure_do_actions()`: 載入 `list[DOActionConfig]` 以啟用宣告式 PULSE/SUSTAINED/TOGGLE 執行
  - `execute_do_action(label)`: 執行指定 DO 動作；PULSE 模式在 `pulse_duration` 後自動取消
  - `available_do_actions`: 屬性，回傳目前已配置的 `list[DOActionConfig]`
  - `cancel_pending_pulses()`: 取消所有排程中的 pulse-off 任務（設備關機時自動呼叫）
- **`CapabilityRequirement` dataclass** (`csp_lib.integration.schema`): `capability`、`min_count`、`trait_filter` — 供 preflight validation 使用
- **`AggregationResult` dataclass** (`csp_lib.integration.schema`): `value`、`device_count`、`expected_count`、`quality_ratio` — 聚合品質元資料，供策略層判斷資料可信度
- **[[CapabilityContextMapping]]`.min_device_ratio`**: 可選比例門檻；當響應設備少於此比例時，聚合回傳 `default` 並發出警告
- **[[DeviceRegistry]]`.validate_capabilities(requirements)`**: 回傳未滿足 `CapabilityRequirement` 的可讀訊息列表
- **[[SystemControllerConfig]] 能力驗證**:
  - `capability_requirements`: `CapabilityRequirement` 列表，在 `preflight_check()` 時驗證
  - `strict_capability_check`: 設為 `True` 時，`preflight_check()` 在需求未滿足時 raise `ConfigurationError`
- **`SystemController.preflight_check()`**: 執行 `validate_capabilities` 驗證已註冊的能力需求；可在 `async with` 前呼叫，提前發現部署不匹配
- **[[SystemControllerConfigBuilder]] 擴充**:
  - `require_capability(requirement)`: fluent 方法，新增 `CapabilityRequirement`
  - `strict_capability(enabled?)`: fluent 方法，設定 `strict_capability_check`
- **Repository Protocol 拆分**: [[AlarmRepository]]、[[CommandRepository]]、`ScheduleRepository` Protocol 現在無需安裝 `motor` 即可匯入 — 具體 `MongoXxxRepository` 實作透過 `TYPE_CHECKING` 延遲匯入 motor

### Changed

- **`AlarmRecord.occurred_at` → `timestamp`**: 統一時間戳欄位命名，與 [[DataUploadManager]]、[[StateSyncManager]] 的 document 一致
- **`AlarmRecord.resolved_at` → `resolved_timestamp`**: 對稱重新命名
- **`WriteCommand.created_at` → `timestamp`**: 統一所有指令類型的時間戳欄位命名
- **`ActionCommand.created_at` → `timestamp`**: 與 WriteCommand 一致
- **`CommandRecord.created_at` → `timestamp`**: 與告警 schema 統一
- **[[MongoAlarmRepository]] 索引**: `ensure_indexes()` 改為索引 `timestamp` 和 `resolved_timestamp`
- **[[MongoCommandRepository]] 索引與排序**: `list_by_device()` 改依 `timestamp` 排序；`ensure_indexes()` 改索引 `timestamp`
- **[[DataUploadManager]] 建構子型別**: 接受 `BatchUploader`（Protocol）取代 `MongoBatchUploader`
- **`StatisticsManager` 建構子型別**: 同 [[DataUploadManager]] 變更
- **[[UnifiedConfig]]`.mongo_uploader`**: 型別從 `MongoBatchUploader` 放寬為 `BatchUploader`

### Fixed

- **靜默低容量聚合**: 設定 `min_device_ratio` 的 [[CapabilityContextMapping]] 現在會在響應設備不足時發出警告並回傳 `default`，而非靜默計算不完整的聚合結果

---

## [0.5.2] - 2026-04-02

### Added

- **DroopStrategy 測試** (`tests/controller/test_droop_strategy.py`): 38 test cases 涵蓋正常執行、死區、邊界、無頻率資料 fail-safe、config 驗證
- **RampStopStrategy 測試** (`tests/controller/test_ramp_stop_strategy.py`): 11 test cases 涵蓋斜坡降功率、到零停止、中途恢復、lifecycle
- **[[CommandProcessor]] pipeline 測試**: 3 test cases 驗證 pipeline 串接、多 processor 順序、空 pipeline
- **[[SystemControllerConfigBuilder]] 測試** (`tests/integration/test_config_builder.py`): 11 test cases 涵蓋 fluent chain、互斥驗證、完整 build
- **WriteRule (Gateway) 測試** (`tests/modbus_gateway/test_write_rule.py`): 15 test cases 涵蓋 clamp/reject 模式、部分邊界、驗證
- **FFTableRepository 測試** (`tests/controller/test_ff_table_repository.py`): 17 test cases 涵蓋 JSON 讀寫、MongoDB async、空表處理、Protocol 一致性
- **[[PowerCompensator]] 補充測試**: 10 test cases 新增 transient gate (hold_cycles)、EMA 濾波、飽和重設、FF 繼承
- **Root conftest.py 共用 fixture**: `make_mock_device`、`mock_strategy`、`mock_registry` 跨模組共用
- **pytest markers 補齊**: `integration`、`flaky`、`requires_external` 標記定義
- **Slow test 標記**: 6 個慢速測試標記 `@pytest.mark.slow`，支援 `pytest -m "not slow"` 快速開發
- **pytest-xdist 平行測試**: 啟用 `addopts = "-n auto"`，測試執行時間從 120s 降至 ~48s

### Fixed

- **AlarmRecord.alarm_code 未寫入 MongoDB** (`csp_lib.manager.alarm.persistence`): `_on_alarm_triggered` 和 `_on_disconnected` 建立 AlarmRecord 時漏設 `alarm_code`，導致 MongoDB 中 alarm_code 欄位為空字串

### Changed

- **[[DeviceStateSubscriber]] log 等級修正** (`csp_lib.integration.distributed.subscriber`): Redis 讀取失敗 log 從 `debug` 升至 `warning`
- **DeprecationWarning 過濾收窄** (`pyproject.toml`): 從全局忽略改為只過濾已知第三方（pymodbus、motor、redis），自身 deprecation 警告正常顯示

---

## [0.5.1] - 2026-04-01

### Added

- **WeakRef event listener** (`csp_lib.equipment.device.events`): `on(event, handler, weak=True)` 支援弱引用 handler，GC 後自動清理

### Changed

- **錯誤階層擴充**: 新增 `StrategyExecutionError`、`ProtectionError`、`DeviceRegistryError` 結構化例外，取代裸 `RuntimeError` / `ValueError`
- **`ModbusError` 上下文**: `ModbusError` 子類別攜帶 `address`、`unit_id`、`function_code` 欄位，方便上層快速分類
- **Modbus 連線生命週期 log**: connect / disconnect / reconnect 事件統一以 INFO 等級記錄，含連線參數與耗時
- **Writer log 等級修正**: [[ValidatedWriter]] 寫入成功 log 從 DEBUG 降至 TRACE，減少正常運行時的 log 雜訊
- **靜默失敗修復**: `aggregator`、`base`、`scheduler` 捕獲例外後改為 `logger.error()` 並重新拋出或回傳預設值，不再靜默吞掉錯誤
- **Logger 命名統一**: 29 個檔案的 `get_logger()` 呼叫統一使用 `__name__`，確保 log 層級控制與過濾一致
- **WriteRejectedError 結構化 log** (`csp_lib.modbus_gateway.pipeline`): Validator 與 WriteRule 拒絕寫入時改用 `WriteRejectedError` 格式化訊息，log 等級從 DEBUG 升至 WARNING
- **[[StrategyExecutor]] 錯誤上下文**: 策略執行失敗時 log 含 strategy name、SOC、context extra keys，修復潛在 UnboundLocalError
- **Device 事件處理 log**: `_process_values()` 和 alarm 評估例外不再靜默，加 warning log 含 device_id 和 point 上下文
- **[[ContextBuilder]] 映射失敗上下文**: transform/aggregate 失敗 log 含 mapping source、point_name、target field
- **Alarm Evaluator log**: `evaluator.py` 新增 logger，告警觸發/解除以 DEBUG 記錄；`mixins.py` 寫入成功 INFO → DEBUG
- **Cluster 例外鏈**: `sync.py`、`election.py` 所有 `except Exception` 加 `as e` 捕獲 + 重試/狀態上下文
- **loguru exception() 審計**: 可恢復錯誤從 `logger.exception()`（ERROR）改為 `logger.opt(exception=True).warning()`
- **[[DeviceRegistry]] 並發安全**: 加 `threading.Lock` 保護所有讀寫操作，防止並發修改崩潰
- **[[DeviceEventEmitter]] 優雅關閉**: stop() 改為 drain queue + handler 完成等待；emit() 未啟動時不入隊；handler 迭代前 copy 防並發修改
- **Device 重複註冊檢查** (`csp_lib.manager.device.manager`): register() 和 register_group() 檢查 duplicate device_id
- **[[DeviceConfig]] 驗證加強**: `reconnect_interval <= 0` 拒絕（防止 tight loop）
- **WriteRule 驗證加強**: `min_value > max_value` 拒絕
- **Redis Sentinel disconnect**: `disconnect()` 時釋放 `_sentinel` 引用，防止 Sentinel 連線洩漏
- **NotificationBatcher flush retry**: `_on_stop()` flush 失敗時重試一次，記錄 dropped notification 數量
- **[[CircuitBreaker]] 指數退避**: 加 `max_cooldown`、`backoff_factor` 參數，故障恢復時加 jitter 防止 thundering herd
- **[[ModbusRequestQueue]] 清理 log**: `stop()` 加 cancelled/done futures summary log
- **Device 狀態 asyncio.Lock** (`csp_lib.equipment.device.base`): `_status_lock` 保護 responsive/failure 狀態更新，防止並發競態
- **[[UnifiedDeviceManager]] 註冊 threading.Lock**: `_register_lock` 防止並發註冊重複訂閱
- **StatisticsEngine 去重**: `register_power_sum_devices()` 去重防止累計值翻倍
- **DataFeed attach 回滾**: `attach()` 部分失敗時回滾已訂閱的 handler，防止洩漏
- **Heartbeat point 驗證**: `_on_start()` 時驗證 heartbeat point 在目標設備上是否存在

---

## [0.5.0] - 2026-03-31

### Added

- **[[RuntimeParameters]]** (`csp_lib.core.runtime_params`): Thread-safe 即時參數容器
  - 支援 `get` / `set` / `update` / `snapshot` / `delete` / `setdefault` 操作
  - Observer pattern：`on_change(callback)` 在值變更時觸發通知（在鎖外同步呼叫）
  - 以 `threading.Lock` 保護，Modbus hook thread 與 asyncio event loop 之間安全存取
  - 適用於需從外部系統（EMS / Modbus / Redis）即時推送的參數（如 SOC 上下限、功率限制）
- **[[CommandProcessor]] Protocol** (`csp_lib.controller.core.processor`): Post-Protection 命令處理器
  - `@runtime_checkable Protocol`，定義 `async def process(command, context) -> Command` 介面
  - 插入於 [[ProtectionGuard]] 與 [[CommandRouter]] 之間，支援功率補償、命令日誌、審計追蹤
  - [[SystemControllerConfig]] 新增 `post_protection_processors` 欄位以組合多個處理器
- **[[DroopStrategy]]** (`csp_lib.controller.strategies.droop_strategy`): 標準下垂一次頻率響應策略
  - 根據頻率偏差透過下垂公式計算功率：`gain = 100 / (f_base × droop)`
  - `DroopConfig` 可配置下垂係數、死區寬度、基準頻率、最大 AFC 功率與執行週期
  - 支援 `schedule_p + dreg_power` 疊加，自動 clamp 於額定功率範圍
  - `context.extra` 無頻率資料時維持上一次命令（fail-safe hold）
- **[[PowerCompensator]]** (`csp_lib.controller.compensator`): 前饋 + 積分閉環功率補償器
  - 實作 [[CommandProcessor]] Protocol，可直接加入 `post_protection_processors`
  - 前饋表（FF table）按功率區間查表，補償 PCS 非線性與輔電損耗
  - 積分修正含 deadband、anti-windup、rate limiting
  - 穩態自動學習：I 項貢獻吸收進 FF 表，長期自適應
  - 暫態閘門：setpoint 變更後等 PCS 到位才啟動積分
  - FF 表持久化支援 `FFTableRepository` Protocol（可注入 JSON / MongoDB 等後端）
  - `PowerCompensator.async_init()` 支援 async repository（如 MongoDB）啟動後載入
  - `SystemController._on_start()` 自動呼叫 processors 的 `async_init()`
- **動態保護規則** (`csp_lib.controller.system.dynamic_protection`): 從 [[RuntimeParameters]] 讀取動態參數
  - `DynamicSOCProtection`：每次 `evaluate()` 從 [[RuntimeParameters]] 讀取 `soc_max` / `soc_min`，支援 EMS 即時更新
  - `GridLimitProtection`：外部功率限制保護（電力公司 / 排程上限）
  - `RampStopProtection`：故障 / 告警時斜坡降功率至 0（graceful ramp-down）；已標記 deprecated，建議改用 [[RampStopStrategy]]
- **[[RampStopStrategy]]** (`csp_lib.controller.strategies.ramp_stop`): 斜坡降功率策略
  - 替代 `RampStopProtection`，本質上是「接管控制」而非「修改數值」，更適合作為 Strategy
  - 使用實際 dt（monotonic clock）計算每步降幅，不依賴固定 interval
  - 搭配 [[EventDrivenOverride]] + [[ModeManager]]（PROTECTION）使用
  - 不同停止原因可觸發不同策略：通訊中斷 → [[RampStopStrategy]]，告警 → `StopStrategy`
- **[[FFCalibrationStrategy]]** (`csp_lib.controller.calibration`): FF Table 步階校準策略
  - 維護型一次性操作（類似 SOC 校正），自動遍歷各功率 bin 量測 FF ratio
  - 狀態機：IDLE → STEPPING → DONE，完成後寫入 [[PowerCompensator]] FF Table
  - 支援 `on_complete` callback，可配合 [[RuntimeParameters]] 或 Redis 觸發
  - `FFCalibrationConfig` 可配置步幅、穩態門檻、settle wait 等
- **FFTableRepository Protocol** (`csp_lib.controller.compensator`): FF Table 持久化介面
  - `JsonFFTableRepository`：JSON 檔案持久化（預設，向後相容）
  - `MongoFFTableRepository`：MongoDB 持久化（async save + async_load）
  - [[PowerCompensator]] 新增 `repository` 參數，可注入任意後端
  - `PowerCompensator.load_ff_table(table)` 方法供外部校準或 async load 使用
- **[[StrategyContext]]`.params`** (`csp_lib.controller.core.context`): 系統參數直接引用
  - 新增 `params: RuntimeParameters | None` 欄位，區隔系統參數（EMS 指令）與設備讀值（extra）
  - [[SystemControllerConfig]] 新增 `runtime_params` 欄位，[[ContextBuilder]] 自動注入
  - 向後相容：`params=None` 為預設值，不影響現有使用 extra 的程式碼
- **[[ModbusGatewayServer]]** (`csp_lib.modbus_gateway`): 完整 Modbus TCP Gateway Server 模組
  - 宣告式暫存器映射（`GatewayRegisterDef`），支援 HR（Holding）/ IR（Input）分區
  - Write validation chain：`AddressWhitelistValidator`、composable WriteRule Protocol
  - Write hooks：`RedisPublishHook`、`CallbackHook`、`StatePersistHook`
  - 資料同步來源：`RedisSubscriptionSource`、`PollingCallbackSource`
  - 通訊 watchdog：含 timeout / recovery 回呼（`CommunicationWatchdog`）
  - Thread-safe pymodbus 整合，含 asyncio bridge
  - 實作 [[AsyncLifecycleMixin]]，透過 `async with` 管理完整生命週期
- **WriteRule Protocol** (`csp_lib.modbus_gateway.protocol`): 可組合寫入規則介面
  - `apply(register_name, value) -> (value, rejected)` 簽名，支援值轉換與拒絕
  - **RangeRule**: 連續範圍驗證，支援 clamp / reject 模式
  - **AllowedValuesRule**: 離散值白名單（如模式暫存器只接受 `{0, 1, 3, 7}`）
  - **StepRule**: 步進量化（如 `step=0.5` 對齊 0.5 kW 解析度），永不拒絕
  - **CompositeRule**: 串接多個 rule 依序套用，任一拒絕即短路
- **[[SystemControllerConfigBuilder]]** (`csp_lib.integration.system_controller`): Fluent builder
  - `SystemControllerConfig.builder()` 回傳 builder 物件，支援鏈式呼叫
  - `.map_context()` / `.map_command()` / `.protect()` / `.processor()` / `.params()` 等方法
  - 不破壞現有 dataclass 直接建構方式（純加法）

### Changed

- **DRegStrategy → [[DroopStrategy]]**: 重新命名（`DRegConfig` → `DroopConfig`，`max_dreg_power` → `max_droop_power`，檔案 `dreg_strategy.py` → `droop_strategy.py`）
- **[[StrategyContext]]**: 新增 `params` 欄位（`RuntimeParameters | None`），系統參數與設備讀值分離
- **[[SOCBalancingDistributor]]**: 新增個別設備功率上限參數（`per_device_max_p`、`per_device_max_q`），四次算法確保總容量足夠時功率守恆
- **[[RedisClient]]**: `TLSConfig.ca_certs` 改為 Optional；新增 `pubsub()` 與 `scan()` 方法
- **WritePipeline** (`csp_lib.modbus_gateway.pipeline`): 寫入規則改用 WriteRule Protocol，`write_rules` 型別從 `Sequence[WriteRule]` 改為 `Mapping[str, WriteRule]`

### Fixed

- **[[SOCBalancingDistributor]]**: 修復 clamp 溢出重分配後二次溢出被丟棄的問題，新增 Pass 4 確保總容量足夠時功率守恆

### Deprecated

- **RampStopProtection** (`csp_lib.controller.system.dynamic_protection`): 建議改用 [[RampStopStrategy]] + [[EventDrivenOverride]]

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
