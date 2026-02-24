---
CSP Library — 程式架構總覽
---
  一、完整檔案結構（Package Tree）

  csp_lib/                          # 套件根目錄
  │
  ├── core/                         # 🔧 核心基礎設施
  │   ├── __init__.py               #   Logging (loguru)、全域設定
  │   ├── errors.py                 #   統一例外階層 (DeviceError, CommunicationError, AlarmError, ConfigurationError)
  │   ├── health.py                 #   健康狀態模型 (HealthStatus, HealthReport, HealthCheckable Protocol)
  │   └── lifecycle.py              #   AsyncLifecycleMixin (async 生命週期基底)
  │
  ├── modbus/                       # 📡 Modbus 通訊協定層
  │   ├── enums.py                  #   ByteOrder, RegisterOrder, Parity, FunctionCode
  │   ├── exceptions.py             #   ModbusError 例外階層
  │   ├── config.py                 #   ModbusTcpConfig, ModbusRtuConfig
  │   ├── codec.py                  #   ModbusCodec (encode/decode 引擎)
  │   ├── types/                    #   資料型別定義
  │   │   ├── base.py               #     ModbusDataType (ABC)
  │   │   ├── numeric.py            #     Int16, UInt16, Int32, UInt32, Int64, UInt64, Float32, Float64
  │   │   ├── dynamic.py            #     DynamicInt, DynamicUInt (任意位寬)
  │   │   └── string.py             #     ModbusString
  │   └── clients/                  #   非同步客戶端
  │       ├── base.py               #     AsyncModbusClientBase (ABC)
  │       ├── client.py             #     PymodbusTcpClient, PymodbusRtuClient, SharedPymodbusTcpClient
  │       └── compat.py             #     pymodbus 版本相容層
  │
  ├── equipment/                    # ⚙️ 設備抽象層
  │   ├── core/                     #   資料處理核心
  │   │   ├── point.py              #     ReadPoint, WritePoint, PointDefinition, Validators
  │   │   ├── transform.py          #     ScaleTransform, BitExtractTransform, EnumMap... (10 種)
  │   │   └── pipeline.py           #     ProcessingPipeline (Transform 串接)
  │   ├── alarm/                    #   告警系統
  │   │   ├── definition.py         #     AlarmDefinition, AlarmLevel, HysteresisConfig
  │   │   ├── evaluator.py          #     BitMaskAlarmEvaluator, ThresholdAlarmEvaluator, TableAlarmEvaluator
  │   │   └── state.py              #     AlarmState, AlarmStateManager, AlarmEvent
  │   ├── device/                   #   設備本體
  │   │   ├── config.py             #     DeviceConfig
  │   │   ├── events.py             #     DeviceEventEmitter, 9 種事件 Payload
  │   │   ├── mixins.py             #     AlarmMixin (告警管理), WriteMixin (寫入管理)
  │   │   ├── base.py               #     AsyncModbusDevice (核心設備類別)
  │   │   └── event_bridge.py       #     EventBridge (跨設備事件聚合, edge-detection + debounce)
  │   ├── transport/                #   傳輸排程
  │   │   ├── config.py             #     PointGrouperConfig (各 FC 最大讀取長度)
  │   │   ├── base.py               #     ReadGroup, PointGrouper (暫存器合併)
  │   │   ├── reader.py             #     GroupReader (批次讀取 + 解碼)
  │   │   ├── scheduler.py          #     ReadScheduler (固定 + 輪替排程)
  │   │   └── writer.py             #     ValidatedWriter (驗證 + 寫入 + 回讀)
  │   ├── processing/               #   後處理
  │   │   ├── aggregator.py         #     CoilToBitmaskAggregator, ComputedValueAggregator
  │   │   ├── decoder.py            #     解碼器
  │   │   └── can_parser.py         #     CAN Bus 解析
  │   └── simulation/               #   模擬工具
  │       ├── curve.py              #     曲線模擬
  │       └── virtual_meter.py      #     虛擬電表
  │
  ├── controller/                   # 🧠 控制策略層
  │   ├── core/                     #   策略框架核心
  │   │   ├── strategy.py           #     Strategy (ABC)
  │   │   ├── command.py            #     Command, SystemBase, ConfigMixin
  │   │   ├── context.py            #     StrategyContext
  │   │   └── execution.py          #     ExecutionMode, ExecutionConfig
  │   ├── strategies/               #   策略實作 (8 種)
  │   │   ├── pq_strategy.py        #     PQModeStrategy (定功率)
  │   │   ├── pv_smooth_strategy.py #     PVSmoothStrategy (太陽能平滑)
  │   │   ├── qv_strategy.py        #     QVStrategy (電壓支撐)
  │   │   ├── fp_strategy.py        #     FPStrategy (頻率響應/AFC)
  │   │   ├── island_strategy.py    #     IslandModeStrategy (孤島模式)
  │   │   ├── schedule_strategy.py  #     ScheduleStrategy (排程切換)
  │   │   ├── stop_strategy.py      #     StopStrategy (停機)
  │   │   └── bypass_strategy.py    #     BypassStrategy (旁路)
  │   ├── executor/                 #   策略執行引擎
  │   │   ├── strategy_executor.py  #     StrategyExecutor (週期/觸發/混合模式)
  │   │   └── compute_offloader.py  #     ComputeOffloader (ThreadPoolExecutor 卸載同步計算)
  │   ├── system/                   #   系統級控制
  │   │   ├── mode.py               #     ModeManager, ModeDefinition, ModePriority
  │   │   ├── cascading.py          #     CascadingStrategy, CapacityConfig (多策略功率分配)
  │   │   └── protection.py         #     ProtectionGuard, SOCProtection, ReversePowerProtection...
  │   ├── services/                 #   輔助服務
  │   │   └── pv_data_service.py    #     PVDataService (太陽能歷史數據)
  │   └── protocol.py               #   GridControllerProtocol (外部介面)
  │
  ├── integration/                  # 🔗 整合層（膠水層）
  │   ├── registry.py               #   DeviceRegistry (Trait-based 設備查詢)
  │   ├── schema.py                 #   ContextMapping, CommandMapping, DataFeedMapping
  │   ├── context_builder.py        #   ContextBuilder (設備數據 → StrategyContext)
  │   ├── command_router.py         #   CommandRouter (Command → 設備寫入)
  │   ├── data_feed.py              #   DeviceDataFeed (PV 資料注入)
  │   ├── loop.py                   #   GridControlLoop (基本控制迴圈)
  │   ├── system_controller.py      #   SystemController (完整系統控制器)
  │   ├── group_controller.py       #   GroupControllerManager (多群組獨立控制)
  │   └── orchestrator.py           #   SystemCommand, CommandStep, StepCheck (多步驟系統命令)
  │
  ├── manager/                      # 📦 管理層（外部服務整合）
  │   ├── base.py                   #   DeviceEventSubscriber (事件訂閱基底)
  │   ├── unified.py                #   UnifiedDeviceManager (組合管理器)
  │   ├── device/                   #   設備生命週期管理
  │   │   ├── manager.py            #     DeviceManager (啟動/停止/連線)
  │   │   └── group.py              #     DeviceGroup (RTU 共線順序讀取)
  │   ├── alarm/                    #   告警持久化
  │   │   ├── config.py             #     AlarmPersistenceConfig (斷線告警設定)
  │   │   ├── persistence.py        #     AlarmPersistenceManager (→ MongoDB)
  │   │   ├── repository.py         #     MongoAlarmRepository
  │   │   └── schema.py             #     AlarmRecord, AlarmStatus, AlarmType
  │   ├── command/                  #   寫入命令管理
  │   │   ├── manager.py            #     WriteCommandManager
  │   │   ├── repository.py         #     MongoCommandRepository
  │   │   ├── schema.py             #     WriteCommand, CommandRecord
  │   │   └── adapters/
  │   │       ├── config.py         #       CommandAdapterConfig (Redis 頻道名稱)
  │   │       └── redis.py          #       RedisCommandAdapter (Pub/Sub 接收命令)
  │   ├── data/                     #   資料上傳
  │   │   └── upload.py             #     DataUploadManager (→ MongoDB 批次寫入)
  │   └── state/                    #   狀態同步
  │       ├── config.py             #     StateSyncConfig (TTL 設定)
  │       └── sync.py               #     StateSyncManager (→ Redis Hash/Set/Pub/Sub)
  │
  ├── cluster/                      # 🌐 分散式叢集控制
  │   ├── __init__.py               #   公開 API
  │   ├── config.py                 #   ClusterConfig, EtcdConfig
  │   ├── election.py               #   LeaderElector (etcd lease-based 選舉, CANDIDATE/LEADER/FOLLOWER/STOPPED)
  │   ├── sync.py                   #   ClusterStatePublisher (Leader→Redis), ClusterStateSubscriber (Follower←Redis)
  │   ├── context.py                #   VirtualContextBuilder (從 Redis 快取建構 StrategyContext)
  │   └── controller.py             #   ClusterController (中央編排器, 角色自動切換)
  │
  ├── monitor/                      # 📊 系統健康監控
  │   ├── __init__.py               #   公開 API
  │   ├── config.py                 #   MonitorConfig, MetricThresholds
  │   ├── collector.py              #   SystemMetricsCollector (psutil), ModuleHealthCollector
  │   ├── alarm.py                  #   SystemAlarmEvaluator (閾值 + 遲滯告警)
  │   ├── publisher.py              #   RedisMonitorPublisher (指標發佈)
  │   └── manager.py                #   SystemMonitor (AsyncLifecycleMixin 主編排器)
  │
  ├── notification/                 # 🔔 多通道告警通知
  │   ├── __init__.py               #   公開 API
  │   ├── config.py                 #   NotificationConfig (標題/標籤模板)
  │   ├── base.py                   #   Notification, NotificationEvent, NotificationChannel (ABC)
  │   └── dispatcher.py             #   NotificationDispatcher (多通道分發, 獨立失敗隔離)
  │
  ├── statistics/                   # 📈 能源統計
  │   ├── __init__.py               #   公開 API
  │   ├── config.py                 #   StatisticsConfig, MetricDefinition, PowerSumDefinition
  │   ├── tracker.py                #   DeviceEnergyTracker, IntervalAccumulator (區間累積)
  │   ├── engine.py                 #   StatisticsEngine (累計差值/梯形積分計算)
  │   └── manager.py                #   StatisticsManager (事件驅動 + MongoDB 上傳)
  │
  ├── gui/                          # 🖥️ Web 控制面板
  │   ├── __init__.py               #   公開 API
  │   ├── config.py                 #   GUIConfig (host, port, CORS, snapshot_interval)
  │   ├── app.py                    #   create_app() FastAPI 工廠函式
  │   ├── dependencies.py           #   FastAPI 依賴注入
  │   ├── api/                      #   REST API 路由
  │   │   ├── devices.py            #     設備查詢/操作
  │   │   ├── alarms.py             #     告警查詢
  │   │   ├── commands.py           #     命令下發
  │   │   ├── modes.py              #     模式切換
  │   │   ├── health.py             #     健康檢查
  │   │   └── config_io.py          #     設定匯入/匯出
  │   ├── ws/                       #   WebSocket 即時推送
  │   │   ├── manager.py            #     WebSocketManager (連線管理)
  │   │   ├── router.py             #     WebSocket 路由
  │   │   └── events.py             #     EventBridge (SystemController → WebSocket)
  │   └── static/                   #   前端靜態資源 (HTML/CSS/JS SPA)
  │
  ├── modbus_server/                # 🧪 模擬伺服器（測試用）
  │   ├── __init__.py               #   公開 API
  │   ├── config.py                 #   ServerConfig, SimulatedDeviceConfig, Sim*Config, MicrogridConfig
  │   ├── server.py                 #   SimulationServer (AsyncLifecycleMixin), SimulatorDataBlock
  │   ├── register_block.py         #   RegisterBlock (暫存器管理)
  │   ├── microgrid.py              #   MicrogridSimulator (微電網功率平衡聯動)
  │   ├── simulator/                #   設備模擬器
  │   │   ├── base.py               #     BaseDeviceSimulator
  │   │   ├── pcs.py                #     PCSSimulator (儲能變流器)
  │   │   ├── solar.py              #     SolarSimulator (太陽能, 日照曲線)
  │   │   ├── power_meter.py        #     PowerMeterSimulator (電表)
  │   │   ├── generator.py          #     GeneratorSimulator (發電機)
  │   │   └── load.py               #     LoadSimulator (負載)
  │   └── behaviors/                #   模擬行為
  │       ├── alarm.py              #     AlarmBehavior (告警觸發/重置模擬)
  │       ├── curve.py              #     CurveBehavior (曲線跟隨)
  │       ├── noise.py              #     NoiseBehavior (隨機雜訊)
  │       └── ramp.py               #     RampBehavior (線性漸變)
  │
  ├── mongo/                        # 🗄️ MongoDB 客戶端
  │   ├── config.py                 #   MongoConfig (Standalone/ReplicaSet/X.509)
  │   ├── client.py                 #   create_mongo_client()
  │   ├── queue.py                  #   內部佇列
  │   ├── uploader.py               #   MongoBatchUploader
  │   └── writer.py                 #   批次寫入器
  │
  └── redis/                        # 🔴 Redis 客戶端
      ├── config.py                 #   RedisConfig, TLSConfig (Standalone/Sentinel/mTLS)
      └── client.py                 #   RedisClient (Hash/Set/Pub/Sub)

  ---
  二、分層架構圖

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                            🧪 Modbus Server (模擬層)                            │
  │  SimulationServer ← MicrogridSimulator ← [PCS|Solar|PowerMeter|Generator|Load] │
  │  用途：開發測試、整合驗證，模擬完整微電網環境                                        │
  └──────────────────────────────────┬──────────────────────────────────────────────┘
                                     │ Modbus TCP (模擬設備通訊)
  ┌──────────────────────────────────▼──────────────────────────────────────────────┐
  │                              📡 Layer 1: Modbus 通訊層                          │
  │                                                                                 │
  │  ┌─────────────┐  ┌──────────────────┐  ┌─────────────────────────────────┐    │
  │  │ ModbusCodec  │  │ ModbusDataType   │  │ AsyncModbusClientBase (ABC)     │    │
  │  │ encode/decode│  │ Int16..Float64   │  │ ├─ PymodbusTcpClient            │    │
  │  │              │  │ DynamicInt/UInt   │  │ ├─ PymodbusRtuClient (共線鎖)   │    │
  │  │              │  │ ModbusString      │  │ └─ SharedPymodbusTcpClient      │    │
  │  └─────────────┘  └──────────────────┘  └─────────────────────────────────┘    │
  │                                                                                 │
  │  職責：暫存器層級的二進位編解碼、通訊協定連線管理                                      │
  └──────────────────────────────────┬──────────────────────────────────────────────┘
                                     │
  ┌──────────────────────────────────▼──────────────────────────────────────────────┐
  │                            ⚙️ Layer 2: Equipment 設備層                         │
  │                                                                                 │
  │  ┌──────────────────────────────────────────────────────────┐                   │
  │  │              AsyncModbusDevice (核心設備類別)               │                   │
  │  │  ┌─ AlarmMixin ─────────────────────────────────────┐    │                   │
  │  │  │  AlarmEvaluator → AlarmStateManager → AlarmEvent  │    │                   │
  │  │  └──────────────────────────────────────────────────┘    │                   │
  │  │  ┌─ WriteMixin ─────────────────────────────┐            │                   │
  │  │  │  ValidatedWriter → encode → write → verify│            │                   │
  │  │  └──────────────────────────────────────────┘            │                   │
  │  │  ┌─ Transport ──────────────────────────────────┐        │                   │
  │  │  │  ReadScheduler → PointGrouper → GroupReader   │        │                   │
  │  │  │  (固定+輪替)     (暫存器合併)   (批次解碼)     │        │                   │
  │  │  └──────────────────────────────────────────────┘        │                   │
  │  │  ┌─ Data Pipeline ──────────────────────────────┐        │                   │
  │  │  │  ReadPoint → ProcessingPipeline → Transform   │        │                   │
  │  │  │              (Scale, BitExtract, Enum...)      │        │                   │
  │  │  └──────────────────────────────────────────────┘        │                   │
  │  │  ┌─ Events ─────────────────────────────────────┐        │                   │
  │  │  │  DeviceEventEmitter (async Queue-based)       │        │                   │
  │  │  │  9 events: connected, read_complete,          │        │                   │
  │  │  │  value_change, alarm_triggered, write_complete…│        │                   │
  │  │  └──────────────────────────────────────────────┘        │                   │
  │  └──────────────────────────────────────────────────────────┘                   │
  │                                                                                 │
  │  ┌──────────────────────────────────────────────────────────┐                   │
  │  │ EventBridge (跨設備事件聚合)                                │                   │
  │  │  AggregateCondition → edge-detection + debounce           │                   │
  │  │  例：「全部 PCS 已連線」→ emit「system_ready」              │                   │
  │  └──────────────────────────────────────────────────────────┘                   │
  │                                                                                 │
  │  職責：設備抽象、週期讀取、資料轉換、告警偵測、事件發射、跨設備聚合                        │
  └──────────────┬─────────────────────────────────┬────────────────────────────────┘
                 │ 事件 (read_complete, alarm...)   │ latest_values
  ┌──────────────▼─────────────────────────────────▼────────────────────────────────┐
  │                          🔗 Layer 3: Integration 整合層                          │
  │                                                                                 │
  │  ┌─────────────────┐                                                            │
  │  │ DeviceRegistry   │  Trait-based 設備索引 (e.g. trait="pcs", "bms")            │
  │  └────────┬────────┘                                                            │
  │           │                                                                     │
  │  ┌────────▼────────┐  ContextMapping   ┌──────────────────┐                     │
  │  │ ContextBuilder   │ ─────────────────→│ StrategyContext   │                     │
  │  │ 設備數據 → 上下文  │  (聚合/轉換)      │ soc, voltage,    │                     │
  │  └─────────────────┘                   │ frequency, extra  │                     │
  │                                        └────────┬─────────┘                     │
  │                                                  │                              │
  │                                        ┌────────▼─────────┐                     │
  │  ┌─────────────────┐  CommandMapping   │ StrategyExecutor  │                     │
  │  │ CommandRouter    │ ←────────────────│ (週期執行策略)      │                     │
  │  │ Command → 設備寫入│  (單播/廣播)      └──────────────────┘                     │
  │  └─────────────────┘                                                            │
  │                                                                                 │
  │  ┌──────────────────────────────────────────────────────────────────────┐       │
  │  │ SystemController (完整系統控制器)                                       │       │
  │  │  ├── ModeManager (多模式優先級切換)                                     │       │
  │  │  ├── ProtectionGuard (SOC/逆功率/系統告警 保護鏈)                       │       │
  │  │  ├── CascadingStrategy (多策略功率分配)                                 │       │
  │  │  └── Auto-Stop (告警自動停機)                                          │       │
  │  └──────────────────────────────────────────────────────────────────────┘       │
  │                                                                                 │
  │  ┌──────────────────────────────────────────────────────────────────────┐       │
  │  │ GroupControllerManager (多群組獨立控制)                                  │       │
  │  │  └── GroupDefinition[] → 每群組獨立 SystemController                    │       │
  │  │       (子 DeviceRegistry, 獨立 ModeManager/ProtectionGuard/Executor)   │       │
  │  └──────────────────────────────────────────────────────────────────────┘       │
  │                                                                                 │
  │  ┌──────────────────────────────────────────────────────────────────────┐       │
  │  │ SystemCommand / Orchestrator (多步驟系統命令)                           │       │
  │  │  CommandStep[] → 依序執行 (delay + health check + abort-on-fail)       │       │
  │  │  例：system_start → 啟動 MBMS → 等待 → 啟動 PCS                        │       │
  │  └──────────────────────────────────────────────────────────────────────┘       │
  │                                                                                 │
  │  職責：設備查詢、數據聚合、策略調度、命令路由、保護邏輯、群組控制、系統編排                  │
  └──────────────────────────────────┬──────────────────────────────────────────────┘
                                     │
  ┌──────────────────────────────────▼──────────────────────────────────────────────┐
  │                         🧠 Layer 4: Controller 控制策略層                        │
  │                                                                                 │
  │  ┌──────────────────────────────────────────────────────┐                       │
  │  │ Strategy (ABC)                                        │                       │
  │  │  execute(StrategyContext) → Command(p_target, q_target)│                       │
  │  ├──────────────────────────────────────────────────────┤                       │
  │  │ PQModeStrategy     │ 定功率輸出 (P=500kW, Q=100kVar)  │                       │
  │  │ PVSmoothStrategy   │ 太陽能平滑化 (ramp rate 限制)     │                       │
  │  │ QVStrategy         │ 電壓-無效功率下垂控制              │                       │
  │  │ FPStrategy         │ 頻率-有效功率響應 (AFC 6 點曲線)   │                       │
  │  │ IslandModeStrategy │ 孤島模式 (斷路器開/合)             │                       │
  │  │ ScheduleStrategy   │ 排程切換 (動態換策略)              │                       │
  │  │ StopStrategy       │ 停機 (P=0, Q=0)                  │                       │
  │  │ BypassStrategy     │ 旁路 (保持上一次命令)              │                       │
  │  │ CascadingStrategy  │ 多策略功率級聯分配                 │                       │
  │  └──────────────────────────────────────────────────────┘                       │
  │                                                                                 │
  │  ┌──────────────────────────────────────────────────────┐                       │
  │  │ ProtectionRule (ABC)  — 保護規則鏈                     │                       │
  │  │  SOCProtection         │ 電量保護 (高低 SOC 限制)       │                       │
  │  │  ReversePowerProtection│ 逆功率保護 (防送電)            │                       │
  │  │  SystemAlarmProtection │ 系統告警保護 (強制停機)         │                       │
  │  └──────────────────────────────────────────────────────┘                       │
  │                                                                                 │
  │  ┌──────────────────────────────────────────────────────┐                       │
  │  │ ComputeOffloader                                      │                       │
  │  │  ThreadPoolExecutor 卸載同步策略計算，避免阻塞 event loop │                       │
  │  └──────────────────────────────────────────────────────┘                       │
  │                                                                                 │
  │  職責：控制演算法、功率計算、保護規則、計算卸載                                          │
  └─────────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────────────────────┐
  │                          📦 Layer 5: Manager 管理層                               │
  │                                                                                  │
  │  ┌─────────────────────────────────────────────────────────────────────┐         │
  │  │ UnifiedDeviceManager (組合門面)                                       │         │
  │  │  ├── DeviceManager         設備生命週期 (start/stop/connect)          │         │
  │  │  │   └── DeviceGroup       RTU 共線循序讀取群組                       │         │
  │  │  ├── AlarmPersistenceManager 告警事件 → MongoDB 寫入                  │         │
  │  │  ├── DataUploadManager     讀取數據 → MongoDB 批次上傳                │         │
  │  │  ├── WriteCommandManager   外部寫入命令執行 + 審計記錄                 │         │
  │  │  └── StateSyncManager      即時狀態 → Redis (Hash/Set/Pub/Sub)       │         │
  │  └─────────────────────────────────────────────────────────────────────┘         │
  │                                                                                  │
  │  ┌─────────────────────────────────────────────────────────────────────┐         │
  │  │ StatisticsManager (能源統計)                                          │         │
  │  │  └── StatisticsEngine → DeviceEnergyTracker → IntervalAccumulator   │         │
  │  │      支援累計差值 (CUMULATIVE) / 梯形積分 (INSTANTANEOUS)              │         │
  │  │      PowerSumDefinition → 跨設備 trait 功率加總                       │         │
  │  └─────────────────────────────────────────────────────────────────────┘         │
  │                                                                                  │
  │  職責：設備生命週期、外部儲存整合、即時狀態同步、能源統計                                  │
  └──────────────────────┬──────────────────────────────┬────────────────────────────┘
                         │                              │
            ┌────────────▼──────────┐      ┌────────────▼──────────┐
            │  🗄️ MongoDB (motor)   │      │  🔴 Redis (redis-py)  │
            │  • 設備讀值歷史         │      │  • 即時狀態 (Hash)     │
            │  • 告警記錄            │      │  • 上線狀態 (String)   │
            │  • 命令審計日誌         │      │  • 活躍告警 (Set)      │
            │  • 批次上傳            │      │  • 事件推播 (Pub/Sub)  │
            │  • 能源統計記錄         │      │  • 叢集狀態同步         │
            └───────────────────────┘      │  • 系統監控指標         │
                                           └───────────────────────┘

  ┌──────────────────────────────────────────────────────────────────────────────────┐
  │                          🌐 附加模組：跨層級服務                                    │
  │                                                                                  │
  │  ┌─ Cluster (分散式 HA) ──────────────────────────────────────────────────┐      │
  │  │  LeaderElector (etcd lease) → ClusterController                        │      │
  │  │  Leader: 本地設備控制 + ClusterStatePublisher → Redis                   │      │
  │  │  Follower: ClusterStateSubscriber → VirtualContextBuilder → 影子執行    │      │
  │  │  Failover: lease 過期 → 重新選舉 → grace period → 新 Leader 接管       │      │
  │  └────────────────────────────────────────────────────────────────────────┘      │
  │                                                                                  │
  │  ┌─ Monitor (系統監控) ──────────────────────────────────────────────────┐       │
  │  │  SystemMonitor → SystemMetricsCollector (psutil) + ModuleHealthCollector│      │
  │  │  → SystemAlarmEvaluator (閾值+遲滯) → RedisMonitorPublisher            │      │
  │  │  → NotificationDispatcher (告警通知)                                    │      │
  │  └────────────────────────────────────────────────────────────────────────┘      │
  │                                                                                  │
  │  ┌─ Notification (告警通知) ─────────────────────────────────────────────┐       │
  │  │  NotificationDispatcher → NotificationChannel[] (ABC)                  │      │
  │  │  可擴充通道：LINE / Telegram / Email / Webhook ...                      │      │
  │  │  每通道獨立失敗隔離，單一通道錯誤不影響其他通道                              │      │
  │  └────────────────────────────────────────────────────────────────────────┘      │
  │                                                                                  │
  │  ┌─ GUI (Web 控制面板) ──────────────────────────────────────────────────┐       │
  │  │  FastAPI + WebSocket SPA                                               │      │
  │  │  REST API: devices / alarms / commands / modes / health / config_io    │      │
  │  │  EventBridge: SystemController events → WebSocket 即時推送              │      │
  │  └────────────────────────────────────────────────────────────────────────┘      │
  └──────────────────────────────────────────────────────────────────────────────────┘

  ---
  三、核心類別關係圖

                          ┌────────────────────┐
                          │ AsyncLifecycleMixin │  (所有長生命週期物件的基底)
                          └─────────┬──────────┘
                ┌──────────────┬────┼────────────────┬───────────────────┐
                ▼              ▼    ▼                ▼                   ▼
      ┌─────────────┐ ┌───────────────┐ ┌──────────────────┐ ┌──────────────────┐
      │DeviceManager │ │GridControlLoop│ │SystemController   │ │ClusterController  │
      └─────────────┘ └───────┬───────┘ └────────┬─────────┘ └────────┬─────────┘
                               │                  │                     │
                    ┌──────────┼──────────┐       │ (extends GCL)      │ (composes SC)
                    ▼          ▼          ▼       │                     │
            ContextBuilder  CommandRouter  StrategyExecutor ◄───────────┘
                    │                        │
                    │                        ▼
                    │                    Strategy (ABC)
                    │                    ├── PQModeStrategy
                    │                    ├── PVSmoothStrategy
                    ▼                    ├── QVStrategy
              DeviceRegistry             ├── FPStrategy
                    │                    ├── IslandModeStrategy
                    ▼                    ├── ScheduleStrategy
            AsyncModbusDevice            ├── StopStrategy
            ├── AlarmMixin               ├── BypassStrategy
            ├── WriteMixin               └── CascadingStrategy
            │                                    │
            │ composes:                           │ composes:
            ├── ReadScheduler                     ├── list[Strategy]
            ├── GroupReader                       └── CapacityConfig
            ├── ValidatedWriter
            ├── AlarmStateManager
            ├── DeviceEventEmitter
            └── AggregatorPipeline

      GroupControllerManager               SystemMonitor
            │                              ├── SystemMetricsCollector
            └── GroupDefinition[]           ├── ModuleHealthCollector
                └── SystemController[]      ├── SystemAlarmEvaluator
                                           └── RedisMonitorPublisher

      StatisticsManager                    NotificationDispatcher
            └── StatisticsEngine                └── NotificationChannel[]
                └── DeviceEnergyTracker[]

  ---
  四、核心資料流

  4.1 讀取循環（每 1~60 秒）

  ReadScheduler.get_next_groups()
      │  (固定點位 + 當前輪替點位)
      ▼
  PointGrouper 合併相鄰暫存器
      │  (減少 Modbus 請求數)
      ▼
  GroupReader.read_many()
      │  (Modbus TCP/RTU 通訊)
      ▼
  raw registers [0x1234, 0x5678, ...]
      │
      ▼
  ModbusDataType.decode()  →  typed values (float, int, str)
      │
      ▼
  ProcessingPipeline.process()  →  transformed values
      │  (Scale × 0.1, BitExtract, EnumMap...)
      ▼
  AggregatorPipeline.process()  →  computed values
      │  (CoilToBitmask, ComputedValue...)
      ▼
  AsyncModbusDevice._latest_values  (更新快取)
      │
      ├── emit(VALUE_CHANGE)  →  訂閱者
      ├── emit(READ_COMPLETE) →  DataUploadManager   → MongoDB
      │                       →  StateSyncManager    → Redis
      │                       →  StatisticsManager   → 區間累積 → MongoDB
      │
      └── AlarmEvaluator.evaluate()
              │
              ▼
          AlarmStateManager.update()  (套用遲滯邏輯)
              │
              ├── emit(ALARM_TRIGGERED) → AlarmPersistenceManager → MongoDB
              │                         → NotificationDispatcher  → LINE/Telegram/...
              └── emit(ALARM_CLEARED)   → StateSyncManager → Redis
                                        → NotificationDispatcher  → 解除通知

  4.2 控制循環

  ContextBuilder.build()
      │  讀取 DeviceRegistry 中各設備的 latest_values
      │  根據 ContextMapping 聚合、轉換
      ▼
  StrategyContext { soc, extra: {voltage, frequency, ...} }
      │
      ▼
  StrategyExecutor  (PERIODIC / TRIGGERED / HYBRID)
      │  呼叫當前 Strategy.execute(context)
      │  (可透過 ComputeOffloader 卸載至執行緒池)
      ▼
  Command { p_target: 500.0, q_target: 100.0 }
      │
      ▼
  ProtectionGuard.apply()  (保護鏈)
      │  SOCProtection → ReversePowerProtection → SystemAlarmProtection
      ▼
  Protected Command { p_target: 450.0, q_target: 100.0 }
      │
      ▼
  CommandRouter.route()
      │  根據 CommandMapping 路由到設備
      │  單播 (device_id) 或 廣播 (trait)
      ▼
  AsyncModbusDevice.write("active_power", 450.0)
      │  ValidatedWriter → encode → Modbus write → (verify)
      ▼
  物理設備執行功率命令

  4.3 模式切換流程

  ModeManager
      │
      ├── register("pq", PQModeStrategy, priority=10)
      ├── register("pv_smooth", PVSmoothStrategy, priority=10)
      ├── register("qv", QVStrategy, priority=10)
      ├── register("protection_stop", StopStrategy, priority=100)
      │
      ├── set_base_mode("pq")           →  正常運行用 PQ
      ├── add_base_mode("qv")           →  多策略 → CascadingStrategy
      ├── push_override("protection_stop") →  告警時覆蓋為停機
      └── pop_override("protection_stop")  →  告警解除，恢復原策略

      優先級邏輯:
      ┌─────────────────────────────────────┐
      │  Override Stack (高優先)             │
      │   protection_stop (100) ← 最高優先   │
      │   manual_override (50)              │
      ├─────────────────────────────────────┤
      │  Base Modes (低優先)                 │
      │   pq (10)                           │
      │   qv (10)  ← 多個 base → Cascading  │
      └─────────────────────────────────────┘

  4.4 叢集 Leader/Follower 流程

  ClusterController
      │
      ├── LeaderElector (etcd lease-based 選舉)
      │     CANDIDATE → 嘗試取得 lease → LEADER 或 FOLLOWER
      │
      ├── Leader 模式:
      │     LocalDevice.read() → Redis.publish(state)  [ClusterStatePublisher]
      │     ContextBuilder(local) → StrategyExecutor → CommandRouter → Device.write()
      │     ClusterSnapshot (modes, protection, commands) → Redis Hash
      │
      ├── Follower 模式:
      │     Redis.subscribe(state) → VirtualContextBuilder [ClusterStateSubscriber]
      │     VirtualContextBuilder → StrategyExecutor → (no write, shadow mode)
      │     用途：hot standby, 隨時可接管
      │
      └── Failover:
            Leader down → etcd lease 過期 → 重新選舉
            新 Leader: grace period → 開始控制
            Redis Key Schema:
              cluster:{namespace}:state          # 叢集狀態 Hash
              cluster:{namespace}:device:{id}    # 設備狀態 Hash
              channel:cluster:{namespace}:state  # 狀態變更 Pub/Sub

  4.5 多步驟系統命令流程

  SystemCommand("system_start")
      │
      ├── Step 1: action="start", trait="mbms", delay_before=0
      │     → 啟動所有 MBMS 設備
      │     → check_after: trait="mbms", check="is_responsive", timeout=30s
      │
      ├── Step 2: action="start", trait="pcs", delay_before=5s
      │     → 等待 5 秒後啟動所有 PCS
      │     → check_after: trait="pcs", check="is_healthy", timeout=60s
      │
      └── 任何步驟失敗 → abort (不執行後續步驟)

  4.6 能源統計流程

  StatisticsManager (訂閱 read_complete 事件)
      │
      ├── MetricDefinition (單設備能源指標)
      │     CUMULATIVE: 累計電表讀數差值 (kWh_end - kWh_start)
      │     INSTANTANEOUS: 即時功率梯形積分 (kW → kWh)
      │     → DeviceEnergyTracker → IntervalAccumulator
      │
      ├── PowerSumDefinition (跨設備功率加總)
      │     trait="pcs", point_name="active_power"
      │     → 加總所有該 trait 設備的即時功率
      │
      └── 每 interval_minutes → IntervalRecord / PowerSumRecord → MongoDB

  ---
  五、設計模式總覽

  ┌─────────────────────────┬─────────────────────────────────┬──────────────────────────────────────────┐
  │          模式           │            應用位置             │                   說明                   │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Strategy                │ Controller 全部策略             │ 可插拔的控制演算法，統一 execute() 介面  │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Command                 │ Command dataclass               │ 不可變命令物件，安全跨 async 傳遞        │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Observer                │ DeviceEventEmitter, EventBridge │ 設備事件的發布/訂閱，async Queue-based   │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Chain of Responsibility │ ProtectionGuard                 │ 多個保護規則依序套用                     │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Pipeline                │ ProcessingPipeline              │ Transform 步驟串接處理                   │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Mixin                   │ AlarmMixin, WriteMixin          │ 設備功能解耦                             │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Facade                  │ UnifiedDeviceManager            │ 整合所有子管理器的統一介面               │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Template Method         │ AsyncLifecycleMixin             │ _on_start() / _on_stop() 由子類覆寫      │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Singleton (引用計數)    │ RTU/SharedTCP Client            │ 同一 port 共享連線，引用計數管理生命週期 │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Protocol (Structural)   │ AlarmRepository, ValueValidator │ Python Protocol 定義介面契約             │
  │                         │ HealthCheckable, NotifChannel   │                                          │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Registry                │ DeviceRegistry                  │ Trait-based 雙索引設備查詢               │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Delta-based Clamping    │ CascadingStrategy               │ 只縮放增量功率，保護高優先策略的分配     │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Leader Election         │ ClusterController               │ etcd lease 選舉，Leader/Follower 角色切換│
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Fan-out                 │ NotificationDispatcher          │ 多通道分發，獨立失敗隔離                 │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Factory                 │ create_app(), create_mongo_client│ 工廠函式建構複雜物件                    │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Edge Detection          │ EventBridge                     │ 跨設備事件聚合 + debounce               │
  ├─────────────────────────┼─────────────────────────────────┼──────────────────────────────────────────┤
  │ Transaction Steps       │ SystemCommand / Orchestrator    │ 多步驟命令序列，失敗中止                 │
  └─────────────────────────┴─────────────────────────────────┴──────────────────────────────────────────┘

  ---
  六、可選依賴架構

  csp_lib (核心，僅依賴 loguru)
      │
      ├── csp_lib[modbus]   →  pymodbus      (Modbus 通訊)
      ├── csp_lib[mongo]    →  motor          (MongoDB 非同步客戶端)
      ├── csp_lib[redis]    →  redis          (Redis 非同步客戶端)
      ├── csp_lib[monitor]  →  psutil         (系統資源監控)
      ├── csp_lib[cluster]  →  etcetra        (etcd 客戶端, leader election)
      ├── csp_lib[gui]      →  fastapi, uvicorn, pyyaml (Web 控制面板)
      └── csp_lib[all]      →  以上全部

  惰性載入 (Lazy Import)：
    modbus clients  → 使用時才 import pymodbus
    mongo module    → 使用時才 import motor
    redis module    → 使用時才 import redis
    monitor module  → 使用時才 import psutil
    cluster module  → 使用時才 import etcetra
    gui module      → 使用時才 import fastapi

  ---
  七、測試架構

  tests/
  ├── core/
  │   ├── test_errors.py              # 例外階層單元測試
  │   ├── test_health.py              # 健康狀態模型單元測試
  │   └── test_lifecycle.py           # AsyncLifecycleMixin 單元測試
  ├── modbus/
  │   ├── test_config.py              # Modbus 設定測試
  │   ├── test_enums.py               # 列舉測試
  │   └── test_types.py               # 資料型別測試
  ├── equipment/
  │   ├── test_core_point.py          # 點位定義測試
  │   ├── test_core_transform.py      # 資料轉換測試
  │   ├── test_core_pipeline.py       # 處理管線測試
  │   ├── test_alarm_*.py             # 告警系統測試 (definition/evaluator/state)
  │   ├── test_device_*.py            # 設備測試 (base/config/events)
  │   ├── test_transport_*.py         # 傳輸層測試 (base/reader/writer)
  │   ├── test_processing_*.py        # 後處理測試 (aggregator/can_parser/decoder)
  │   ├── test_simulation.py          # 模擬工具測試
  │   └── device/                     # 設備子模組測試 (event_bridge, mixins)
  ├── controller/
  │   ├── test_core.py                # 策略框架核心測試
  │   ├── test_strategies.py          # 8 種策略單元測試
  │   ├── test_executor.py            # StrategyExecutor 測試
  │   ├── test_services.py            # PVDataService 測試
  │   ├── system/
  │   │   ├── test_mode.py            # ModeManager 單元測試
  │   │   ├── test_cascading.py       # CascadingStrategy 單元測試
  │   │   └── test_protection.py      # ProtectionGuard 單元測試
  │   └── executor/                   # ComputeOffloader 測試
  ├── integration/
  │   ├── test_registry.py            # DeviceRegistry 測試
  │   ├── test_schema.py              # 映射 Schema 測試
  │   ├── test_context_builder.py     # ContextBuilder 測試
  │   ├── test_command_router.py      # CommandRouter 整合測試
  │   ├── test_data_feed.py           # DataFeed 測試
  │   ├── test_loop.py                # GridControlLoop 整合測試
  │   ├── test_system_controller.py   # SystemController 整合測試
  │   ├── test_group_controller.py    # GroupControllerManager 測試
  │   └── test_orchestrator.py        # SystemCommand 測試
  ├── manager/
  │   ├── test_alarm_*.py             # 告警持久化測試 (persistence/schema)
  │   ├── test_command_*.py           # 命令管理測試 (manager/schema)
  │   ├── test_data_upload.py         # 資料上傳測試
  │   ├── test_device_*.py            # 設備管理測試 (manager/group)
  │   ├── test_state_sync.py          # 狀態同步測試
  │   └── test_unified.py             # UnifiedDeviceManager 測試
  ├── cluster/                        # 叢集模組測試 (election/sync/context/controller)
  ├── monitor/                        # 監控模組測試 (collector/alarm/publisher/manager)
  ├── notification/                   # 通知模組測試 (dispatcher)
  ├── statistics/                     # 統計模組測試 (tracker/engine/manager)
  ├── gui/                            # GUI 模組測試 (app/ws/api)
  ├── modbus_server/                  # 模擬伺服器測試 (server/simulator/behaviors/microgrid)
  ├── mongo/
  │   └── test_mongo_config.py        # MongoDB 設定測試
  └── redis/
      └── test_redis_config.py        # Redis 設定測試

  ---
  八、一句話架構總結

  Modbus 負責「聽懂設備」，Equipment 負責「抽象設備」，Controller 負責「做出決策」，Integration 負責「串接一切」，Manager 負責「記錄和同步」。Cluster 負責「高可用」，Monitor 負責「自我觀測」，GUI 負責「人機互動」。

  分層架構中，依賴方向嚴格由上往下，每層只依賴下一層的公開介面，不跨層直接存取，實現了良好的關注點分離。附加模組（Cluster/Monitor/Notification/Statistics/GUI）橫跨多層但不改變核心依賴方向。
