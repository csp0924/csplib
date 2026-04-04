---
tags: [type/concept, status/complete]
updated: 2026-04-04
version: 0.6.1
---
# Layered Architecture

> csp_lib 八層分層架構詳解

## 架構總覽

csp_lib 採用嚴格的由下往上分層架構，每層只依賴下一層的公開介面，不跨層直接存取，實現良好的關注點分離。

**一句話總結**：Core 提供基礎設施，Modbus/CAN 負責「聽懂設備」，Equipment 負責「抽象設備」，Controller 負責「做出決策」，Integration 負責「串接一切」，Manager 負責「記錄和同步」。

## 架構圖

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            Modbus Server (模擬層)                                │
│  SimulationServer <- MicrogridSimulator <- [PCS|Solar|PowerMeter|Generator|Load] │
│  用途：開發測試、整合驗證，模擬完整微電網環境                                        │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   │ Modbus TCP (模擬設備通訊)
┌──────────────────────────────────┬──────────────────────────────────────────────┐
│         Layer 1a: Modbus 通訊層   │         Layer 1b: CAN Bus 通訊層              │
│                                  │                                               │
│  ┌──────────────┐ ┌───────────┐  │  ┌──────────────────┐  ┌──────────────────┐  │
│  │ ModbusCodec   │ │ ModbusData│  │  │ AsyncCANClientBase│  │ CANBusConfig     │  │
│  │ encode/decode │ │ Int16..   │  │  │ (ABC)            │  │ CANFrame         │  │
│  │               │ │ Float64   │  │  │ └─PythonCANClient│  │                  │  │
│  └──────────────┘ └───────────┘  │  └──────────────────┘  └──────────────────┘  │
│  ┌────────────────────────────┐  │                                               │
│  │ AsyncModbusClientBase (ABC)│  │  需安裝：csp0924_lib[can]                      │
│  │ ├─ PymodbusTcpClient       │  │  第三方：python-can>=4.0                       │
│  │ ├─ PymodbusRtuClient       │  │                                               │
│  │ └─ SharedPymodbusTcpClient │  │                                               │
│  └────────────────────────────┘  │                                               │
│                                  │                                               │
│  職責：暫存器層級的二進位編解碼       │  職責：CAN 幀收發、Bus 連線管理                  │
│  通訊協定連線管理                   │                                               │
└──────────────────┬───────────────┴─────────────────────┬─────────────────────────┘
                   │ Modbus 連線                           │ CAN 連線
┌──────────────────▼───────────────────────────────────────▼─────────────────────────┐
│                            Layer 2: Equipment 設備層                               │
│                                                                                 │
│  ┌───────────────────────────────────────┐  ┌──────────────────────────────┐    │
│  │     AsyncModbusDevice (Modbus 設備)    │  │  AsyncCANDevice (CAN 設備)    │    │
│  │  ┌─ AlarmMixin ──────────────────┐    │  │  ┌─ RxFrame 解析 ──────────┐   │    │
│  │  │  AlarmEvaluator               │    │  │  │  CANRxFrameDefinition    │   │    │
│  │  │  → AlarmStateManager          │    │  │  │  → 解碼 + 事件發射        │   │    │
│  │  └───────────────────────────────┘    │  │  └─────────────────────────┘   │    │
│  │  ┌─ WriteMixin ───────────────────┐   │  │  ┌─ PeriodicSendScheduler ─┐   │    │
│  │  │  ValidatedWriter → write       │   │  │  │  週期 CAN 幀發送排程      │   │    │
│  │  └───────────────────────────────┘   │  │  └─────────────────────────┘   │    │
│  │  ┌─ Transport ────────────────────┐  │  └──────────────────────────────┘    │
│  │  │  ReadScheduler → PointGrouper  │  │                                        │
│  │  │  → GroupReader (批次解碼)       │  │  ┌─ DeviceProtocol (Protocol) ──────┐  │
│  │  └────────────────────────────────┘  │  │  @runtime_checkable 設備介面契約  │  │
│  │  ┌─ Data Pipeline ───────────────┐   │  └──────────────────────────────────┘  │
│  │  │  ReadPoint → ProcessingPipeline│  │                                        │
│  │  │  → Transform (Scale, Enum...)  │  │  共用：DeviceEventEmitter (9 種事件)    │
│  │  └────────────────────────────────┘  │                                        │
│  └───────────────────────────────────────┘                                       │
│                                                                                  │
│  職責：設備抽象、週期讀取、資料轉換、告警偵測、事件發射                                   │
└──────────────┬─────────────────────────────────┬────────────────────────────────┘
               │ 事件 (read_complete, alarm...)   │ latest_values
┌──────────────▼─────────────────────────────────▼────────────────────────────────┐
│                          Layer 3: Integration 整合層                              │
│                                                                                 │
│  ┌─────────────────┐                                                            │
│  │ DeviceRegistry   │  Trait-based 設備索引 (e.g. trait="pcs", "bms")            │
│  └────────┬────────┘                                                            │
│           │                                                                     │
│  ┌────────▼────────┐  ContextMapping   ┌──────────────────┐                     │
│  │ ContextBuilder   │ ────────────────→│ StrategyContext   │                     │
│  │ 設備數據 → 上下文  │  (聚合/轉換)      │ soc, voltage,    │                     │
│  └─────────────────┘                   │ frequency, extra  │                     │
│                                        └────────┬─────────┘                     │
│                                                  │                              │
│                                        ┌────────▼─────────┐                     │
│  ┌─────────────────┐  CommandMapping   │ StrategyExecutor  │                     │
│  │ CommandRouter    │ ←───────────────│ (週期執行策略)      │                     │
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
│  │ GroupControllerManager (多群組控制器管理)                               │       │
│  │  └── N × SystemController (每組設備獨立控制)                           │       │
│  └──────────────────────────────────────────────────────────────────────┘       │
│                                                                                 │
│  職責：設備查詢、數據聚合、策略調度、命令路由、保護邏輯                                  │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────────┐
│                         Layer 4: Controller 控制策略層                            │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────┐                       │
│  │ Strategy (ABC)                                        │                       │
│  │  execute(StrategyContext) → Command(p_target, q_target)│                       │
│  ├──────────────────────────────────────────────────────┤                       │
│  │ PQModeStrategy      │ 定功率輸出 (P=500kW, Q=100kVar)  │                      │
│  │ PVSmoothStrategy    │ 太陽能平滑化 (ramp rate 限制)     │                      │
│  │ QVStrategy          │ 電壓-無效功率下垂控制              │                      │
│  │ FPStrategy          │ 頻率-有效功率響應 (AFC 6 點曲線)   │                      │
│  │ DroopStrategy       │ 通用下垂控制                      │                      │
│  │ IslandModeStrategy  │ 孤島模式 (斷路器開/合)             │                      │
│  │ ScheduleStrategy    │ 排程切換 (動態換策略)              │                      │
│  │ StopStrategy        │ 停機 (P=0, Q=0)                  │                      │
│  │ RampStopStrategy    │ 斜率停機 (漸進式降載)              │                      │
│  │ BypassStrategy      │ 旁路 (保持上一次命令)              │                      │
│  │ CascadingStrategy   │ 多策略功率級聯分配                 │                      │
│  │ LoadSheddingStrategy│ 階段性負載卸載 (離網場景)           │                      │
│  └──────────────────────────────────────────────────────┘                       │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────┐                       │
│  │ EventDrivenOverride (Protocol) — 事件驅動覆蓋協定     │                       │
│  │  AlarmStopOverride  │ 告警自動停機                    │                       │
│  │  ContextKeyOverride │ 通用 context key 觸發            │                       │
│  └──────────────────────────────────────────────────────┘                       │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────┐                       │
│  │ ScheduleModeController (Protocol) — 排程模式控制協定  │                       │
│  │  橋接 ScheduleService (L5) 與 SystemController (L6)  │                       │
│  │  activate_schedule_mode() / deactivate_schedule_mode()│                      │
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
│  │ CommandProcessor (Protocol) — Post-Protection 管線    │                       │
│  │  PowerCompensator      │ FF + I 閉環功率補償           │                       │
│  │  FFCalibrationStrategy │ FF 表步進校準（維護模式）       │                       │
│  └──────────────────────────────────────────────────────┘                       │
│                                                                                 │
│  職責：控制演算法、功率計算、保護規則、命令後處理                                        │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│                          Layer 5: Manager 管理層                                  │
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
│  職責：設備生命週期、外部儲存整合、即時狀態同步                                        │
└──────────────────────┬──────────────────────────────┬────────────────────────────┘
                       │                              │
          ┌────────────▼──────────┐      ┌────────────▼──────────┐
          │  MongoDB (motor)      │      │  Redis (aioredis)     │
          │  • 設備讀值歷史         │      │  • 即時狀態 (Hash)     │
          │  • 告警記錄            │      │  • 上線狀態 (String)   │
          │  • 命令審計日誌         │      │  • 活躍告警 (Set)      │
          │  • 批次上傳            │      │  • 事件推播 (Pub/Sub)  │
          └───────────────────────┘      └───────────────────────┘
```

## 各層詳解

### Layer 1a: Modbus 通訊層

**對應模組**：[[_MOC Modbus]]

最底層之一，負責與物理設備進行暫存器層級的二進位通訊。主要元件：

- [[ModbusCodec]] — 編解碼引擎，支援多種位元組序
- [[ModbusDataType]] — 資料型別抽象（[[Int16]], [[Float32]], [[ModbusString]] 等）
- [[AsyncModbusClientBase]] — 非同步客戶端 ABC，實作包括 TCP、RTU、共享 TCP
- [[ModbusRequestQueue]] — 優先序請求佇列，含斷路器防護

需安裝：`csp0924_lib[modbus]`

### Layer 1b: CAN Bus 通訊層

**對應模組**：[[_MOC CAN]]

與 Modbus 層並列的通訊層，負責 CAN Bus 幀收發。主要元件：

- [[CANBusConfig]] — CAN Bus 連線配置（interface, channel, bitrate）
- [[CANFrame]] — CAN 幀資料結構（arbitration_id, data bytes）
- [[AsyncCANClientBase]] — CAN 客戶端 ABC
- [[PythonCANClient]] — 基於 `python-can` 的非同步實作

需安裝：`csp0924_lib[can]`

### Layer 2: Equipment 設備層

**對應模組**：[[_MOC Equipment]]

建構於通訊層之上，提供完整的設備抽象。v0.4.2 新增 CAN 設備支援。

**[[AsyncModbusDevice]]** 整合了：

- **點位系統**：[[ReadPoint]]、[[WritePoint]] 定義設備可讀寫的資料點
- **資料轉換**：[[ProcessingPipeline]] 串接多種 [[Transform]]（縮放、位元萃取、列舉映射等）
- **告警系統**：[[AlarmDefinition]] + 評估器（[[BitMaskAlarmEvaluator]]、[[ThresholdAlarmEvaluator]]）+ [[AlarmStateManager]]（含遲滯邏輯）
- **傳輸排程**：[[ReadScheduler]]（固定 + 輪替）、[[PointGrouper]]（暫存器合併）、[[GroupReader]]（批次讀取）
- **事件系統**：[[DeviceEventEmitter]]（9 種非同步事件），詳見 [[Event System]]

**[[AsyncCANDevice]]**（v0.4.2 新增）整合了：

- **幀定義**：[[CANRxFrameDefinition]] 宣告式 RX 幀映射
- **週期發送**：[[PeriodicSendScheduler]] 管理週期 CAN 幀發送
- **事件系統**：與 AsyncModbusDevice 共用 [[DeviceEventEmitter]]

**[[DeviceProtocol]]**（v0.4.2 新增）：`@runtime_checkable Protocol`，定義通用設備介面契約，讓 Integration 層可以統一處理 Modbus 與 CAN 設備。

### Layer 3: Integration 整合層

**對應模組**：[[_MOC Integration]]

膠水層，負責將設備層的資料轉換為控制策略所需的上下文，並將策略輸出路由回設備：

- [[DeviceRegistry]] — Trait-based 雙索引設備查詢（v0.4.2 支援 Capability-based 查詢）
- [[ContextBuilder]] — 聚合設備數據，建構 [[StrategyContext]]（支援 [[CapabilityContextMapping]]）
- [[CommandRouter]] — 將 [[Command]] 路由到目標設備（支援 [[CapabilityCommandMapping]]）
- [[SystemController]] — 完整系統控制器，整合 [[ModeManager]]、[[ProtectionGuard]]、[[CascadingStrategy]]（v0.4.2 支援 [[EventDrivenOverride]]、實作 [[ScheduleModeController]] Protocol）
- [[GroupControllerManager]] — 多群組控制器管理，為每組設備建立獨立 [[SystemController]]
- [[PowerDistributor]] — 功率分配器抽象，含 EqualDistributor、ProportionalDistributor、SOCBalancingDistributor
- [[HeartbeatService]] — 心跳寫入服務，支援 TOGGLE / INCREMENT / CONSTANT 模式

### Layer 4: Controller 控制策略層

**對應模組**：[[_MOC Controller]]

純邏輯層，實作 12 種控制策略與保護規則：

| 策略 | 說明 |
|------|------|
| [[PQModeStrategy]] | 定功率輸出 |
| [[PVSmoothStrategy]] | 太陽能平滑化 |
| [[QVStrategy]] | 電壓-無效功率下垂控制 |
| [[FPStrategy]] | 頻率-有效功率響應 |
| [[DroopStrategy]] | 通用下垂控制 |
| [[IslandModeStrategy]] | 孤島模式 |
| [[ScheduleStrategy]] | 排程切換 |
| [[StopStrategy]] | 停機 |
| [[RampStopStrategy]] | 斜率停機（漸進式降載） |
| [[BypassStrategy]] | 旁路 |
| [[CascadingStrategy]] | 多策略功率級聯分配 |
| [[LoadSheddingStrategy]] | 階段性負載卸載 |

保護規則鏈：[[SOCProtection]] -> [[ReversePowerProtection]] -> [[SystemAlarmProtection]]

事件驅動覆蓋機制：
- [[EventDrivenOverride]] — `@runtime_checkable Protocol`，條件驅動的自動 override
- [[AlarmStopOverride]] — 告警自動停機（內建實現）
- [[ContextKeyOverride]] — 通用 context key 觸發（內建實現）

排程模式橋接協定：
- [[ScheduleModeController]] — `@runtime_checkable Protocol`，供 ScheduleService (L5) 驅動 SystemController (L6) 的排程模式切換，避免 Manager 層直接依賴 Integration 層

Post-Protection 命令處理管線：
- [[CommandProcessor]] — `@runtime_checkable Protocol`，在 ProtectionGuard 和 CommandRouter 之間對命令做額外處理
- [[PowerCompensator]] — 前饋 + 積分閉環功率補償（實作 CommandProcessor）
- [[FFCalibrationStrategy]] — 維護模式 FF 表步進校準（實作 Strategy）

### Layer 5: Manager 管理層

**對應模組**：[[_MOC Manager]]

最上層，負責設備生命週期管理與外部服務整合：

- [[UnifiedDeviceManager]] — Facade 模式，組合所有子管理器
- [[DeviceManager]] — 設備啟動/停止/連線管理
- [[AlarmPersistenceManager]] — 告警持久化至 MongoDB
- [[DataUploadManager]] — 讀取數據批次上傳
- [[WriteCommandManager]] — 外部命令執行與審計
- [[StateSyncManager]] — Redis 即時狀態同步
- [[ScheduleService]] — 排程服務，透過 [[ScheduleModeController]] Protocol 驅動策略切換

### Layer 0: Core 基礎層

**對應模組**：[[_MOC Core]]

最底層基礎設施，所有層均可依賴：

- `get_logger` / `configure_logging` — centralized loguru 日誌
- [[AsyncLifecycleMixin]] — 統一 async 生命週期管理（start/stop/async with）
- [[HealthCheckable]] / [[HealthReport]] — 健康檢查協定
- [[RuntimeParameters]] — 執行緒安全的可變參數容器，供 EMS/Modbus/Redis 注入執行期參數
- 錯誤階層：`DeviceError` → `DeviceConnectionError`、`CommunicationError`、`AlarmError`、`ConfigurationError`
- [[CircuitBreaker]] / [[CircuitState]] / [[RetryPolicy]] — 通用韌性模式

### 儲存層

**對應模組**：[[_MOC Storage]]

- MongoDB (motor) — 歷史數據、告警記錄、命令日誌
- Redis (aioredis) — 即時狀態、活躍告警、事件推播

## 設計原則

1. **依賴方向嚴格由上往下** — 每層只依賴下一層的公開介面
2. **非同步優先** — 所有 I/O 操作使用 asyncio，詳見 [[Async Patterns]]
3. **事件驅動** — 設備狀態變化透過事件系統通知，詳見 [[Event System]]
4. **可選依賴** — 透過惰性載入支援按需安裝，詳見 [[Optional Dependencies]]

## 相關頁面

- [[_MOC Architecture]] — 返回架構索引
- [[Data Flow]] — 核心資料流圖
- [[Design Patterns]] — 設計模式總覽
