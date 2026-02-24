# Changelog

本專案的所有重要變更皆記錄於此檔案。

格式基於 [Keep a Changelog](https://keepachangelog.com/)，版本號遵循 [Semantic Versioning](https://semver.org/)。

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

### Changed
- 重構管理器使用新基底類別（AlarmPersistenceManager、DataUploadManager、
  StateSyncManager → DeviceEventSubscriber；DeviceManager、UnifiedDeviceManager、
  RedisCommandAdapter → AsyncLifecycleMixin）

### Tests
- 新增 GroupControllerManager 測試（26 個測試：驗證、查詢、模式管理、獨立性、生命週期、健康檢查）
- 新增 integration 模組測試（94 個測試）
- 新增 AsyncLifecycleMixin 單元測試
- 新增 core transform 綜合測試

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
