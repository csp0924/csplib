---
tags:
  - type/diagram
  - layer/architecture
  - status/complete
created: 2026-03-06
updated: 2026-04-04
version: 0.6.1
---

# System Diagrams

csp_lib v0.6 系統圖表集，以 Mermaid 語法呈現系統總覽、核心流程、狀態機與設備生命週期。

---

## 1. 系統總覽架構圖

v0.6 完整 8 層架構。依賴方向由下往上；CAN（Layer 2b）與 Modbus（Layer 2a）並列於 Layer 2。

```mermaid
graph TB
    subgraph L8["Layer 8 ── Additional"]
        L8A[cluster]
        L8B[monitor]
        L8C[notification]
        L8D[modbus_server]
        L8E[gui]
        L8F[modbus_gateway]
        L8G[statistics]
    end

    subgraph L7["Layer 7 ── Storage"]
        L7A[MongoClient]
        L7B[RedisClient]
    end

    subgraph L6["Layer 6 ── Integration"]
        L6A[DeviceRegistry]
        L6B[ContextBuilder]
        L6C[CommandRouter]
        L6D[SystemController]
        L6E[PowerDistributor]
        L6F[HeartbeatService]
    end

    subgraph L5["Layer 5 ── Manager"]
        L5A[UnifiedDeviceManager]
        L5B[AlarmPersistenceManager]
        L5C[DataUploadManager]
    end

    subgraph L4["Layer 4 ── Controller"]
        L4A["策略 × 9
PQMode / QV / FP / Island
PVSmooth / Schedule / Stop
Bypass / LoadShedding"]
        L4B[StrategyExecutor]
        L4C[ModeManager]
        L4D[ProtectionGuard]
        L4E[EventDrivenOverride]
        L4F[LoadSheddingStrategy]
        L4G[CommandProcessor]
        L4H[PowerCompensator]
    end

    subgraph L3["Layer 3 ── Equipment"]
        L3A[AsyncModbusDevice]
        L3B[AsyncCANDevice]
        L3C[DeviceProtocol]
        L3D[ReadScheduler]
        L3E[AlarmStateManager]
        L3F[CANEncoder]
        L3G[PeriodicSendScheduler]
    end

    subgraph L2a["Layer 2a ── Modbus"]
        L2aA[ModbusDataType]
        L2aB[AsyncModbusClientBase]
        L2aC[ModbusCodec]
        L2aD[ModbusRequestQueue]
    end

    subgraph L2b["Layer 2b ── CAN"]
        L2bA[CANBusConfig]
        L2bB[AsyncCANClientBase]
        L2bC[PythonCANClient]
    end

    subgraph L1["Layer 1 ── Core"]
        L1A[AsyncLifecycleMixin]
        L1B[CircuitBreaker]
        L1C[RetryPolicy]
        L1D[HealthCheckable]
        L1E[RuntimeParameters]
    end

    L8 --> L6
    L8 --> L7
    L7 --> L5
    L6 --> L5
    L6 --> L4
    L6 --> L3
    L5 --> L4
    L5 --> L3
    L4 --> L3
    L3 --> L2a
    L3 --> L2b
    L2a --> L1
    L2b --> L1
```

### 關鍵元件

| 元件 | 職責 | 頁面 |
|------|------|------|
| `AsyncLifecycleMixin` | 所有生命週期元件的 `async with` 基底 | [[Layered Architecture]] |
| `CircuitBreaker` | 通用斷路器（Core 層，v0.4.2 移入） | [[_MOC Core]] |
| `DeviceProtocol` | 統一 Modbus/CAN 設備介面的 Protocol | [[DeviceProtocol]] |
| `SystemController` | 頂層控制器，整合所有 Layer 4–6 元件 | [[SystemController]] |
| `PowerDistributor` | 系統級 Command 分配到多設備 | [[PowerDistributor]] |

---

## 2. SystemController 內部編排流程圖

展示 `SystemController` 在每個執行週期中 `_build_context()` 與 `_on_command()` 的完整決策路徑。

```mermaid
flowchart TD
    A([StrategyExecutor 週期觸發]) --> B

    subgraph CTX["_build_context()"]
        B[ContextBuilder.build] --> C[注入 system_alarm 旗標]
        C --> C1{alarm_mode == per_device?}
        C1 -->|是| C2[system_alarm = False]
        C1 -->|否| C3[system_alarm = any device.is_protected]
    end

    C2 & C3 --> D[StrategyContext 快取至 _cached_context]
    D --> E[StrategyExecutor → Strategy.execute → Command]

    subgraph CMD["_on_command(command)"]
        E --> F[ProtectionGuard.apply] --> G[Protected Command]
        G --> G2[CommandProcessor Pipeline\npost_protection_processors]
        G2 --> H{有 EventDrivenOverride?}
        H -->|是| I[_evaluate_event_overrides]
        H -->|否| J
        I --> J

        J{有 PowerDistributor\n且 capability_command_mappings?}
        J -->|是| K[_build_device_snapshots]
        K --> L[distributor.distribute]
        L --> M[CommandRouter.route_per_device\n各設備收到不同 Command]
        J -->|否| N[CommandRouter.route\n同值廣播所有設備]

        M & N --> O{alarm_mode == per_device?}
        O -->|是| P[_handle_device_alarms\n逐設備檢查送停機指令]
        O -->|否| Q([結束])
        P --> Q
    end
```

### 關鍵元件

| 元件 | 職責 | 頁面 |
|------|------|------|
| `ContextBuilder` | 讀取設備點位、組裝 `StrategyContext` | [[ContextBuilder]] |
| `StrategyExecutor` | 以固定週期或事件驅動呼叫策略 | [[SystemController]] |
| `ProtectionGuard` | 套用 SOC 限制、逆送保護等保護規則 | [[SystemController]] |
| `CommandProcessor` | Post-Protection 命令處理管線 | [[CommandProcessor]] |
| `EventDrivenOverride` | 條件驅動的自動 push/pop override | [[EventDrivenOverride]] |
| `PowerDistributor` | 將系統 Command 分配到各設備 | [[PowerDistributor]] |
| `CommandRouter` | 將 Command 欄位寫入對應設備點位 | [[CommandRouter]] |

---

## 3. ModeManager 狀態轉換圖

展示 `ModeManager` 的模式管理狀態機，包含 base mode 列表與 override 堆疊的切換邏輯。

```mermaid
stateDiagram-v2
    [*] --> 閒置 : 初始化

    閒置 --> 單一Base : set_base_mode(name)\n或 add_base_mode(name)

    單一Base --> 閒置 : set_base_mode(None)
    單一Base --> 多Base : add_base_mode(另一 name)
    單一Base --> Override活躍 : push_override(name)\n[source: EVENT / MANUAL]

    多Base --> 單一Base : remove_base_mode(某 name)\n剩餘 1 個
    多Base --> 閒置 : remove_base_mode 直到清空
    多Base --> CascadingStrategy啟用 : capacity_kva 已設定
    CascadingStrategy啟用 --> 多Base : 狀態不變（由 SystemController 組合）
    多Base --> Override活躍 : push_override(name)\n[source: EVENT / MANUAL]

    Override活躍 --> 單一Base : pop_override(name)
    Override活躍 --> 多Base : pop_override(name)\n[base modes > 1]
    Override活躍 --> Override活躍 : push_override(另一 name)\n多 override 同時活躍\n取 priority 最高者生效

    note right of Override活躍
        SwitchSource:
        MANUAL  = 手動切換
        SCHEDULE = 排程觸發
        EVENT   = 事件驅動（AlarmStopOverride 等）
        INTERNAL = 系統內部
    end note
```

### 關鍵元件

| 元件 | 職責 | 頁面 |
|------|------|------|
| `ModeManager` | 管理 base mode 列表與 override 堆疊 | [[ModeManager]] |
| `SwitchSource` | 模式切換來源審計標記 | [[ModeManager]] |
| `CascadingStrategy` | 多 base mode 共存時的組合策略 | [[SystemController]] |
| `ModePriority` | 預設優先等級（SCHEDULE=10、MANUAL=50、PROTECTION=100） | [[ModeManager]] |

---

## 4. 設備生命週期序列圖

對比 `AsyncModbusDevice`（Modbus 輪詢）與 `AsyncCANDevice`（CAN 訂閱）的啟動、讀取、寫入與關閉流程。

```mermaid
sequenceDiagram
    participant App
    participant Device as AsyncModbusDevice / AsyncCANDevice
    participant Client as ModbusClient / CANClient
    participant Events as DeviceEventEmitter

    App->>Device: async with device:
    Device->>Client: connect()
    Device->>Events: emit("connected")

    alt Modbus 設備
        loop ReadScheduler 週期輪詢
            Device->>Client: read_registers()
            Client-->>Device: 原始暫存器資料
            Device->>Device: ModbusCodec 解碼 + Transform 轉換
            Device->>Events: emit("read_complete")
            Device->>Device: AlarmEvaluator.evaluate()
            Device->>Events: emit("alarm_triggered") [若有告警]
            Device->>Events: emit("value_change") [若值變更]
        end
    else CAN 設備
        Device->>Client: subscribe(can_id, frame_handler)
        Device->>Client: start_listener()
        loop 接收 CAN 訊框（背景）
            Client-->>Device: CANFrame 回調
            Device->>Device: CANFrameParser 解析 + AggregatorPipeline
            Device->>Events: emit("value_change") [若值變更]
        end
        loop snapshot_loop 週期
            Device->>Events: emit("read_complete")
            Device->>Device: AlarmEvaluator.evaluate()
            Device->>Device: _check_rx_timeout()
        end
    end

    App->>Device: write("point", value)
    alt Modbus 寫入
        Device->>Client: write_registers()
    else CAN 寫入
        Device->>Device: CANFrameBuffer.set_signal()
        Device->>Client: send(can_id, frame_data) [immediate=True 時]
    end
    Device->>Events: emit("write_complete")

    App->>Device: __aexit__
    Device->>Client: disconnect()
    Device->>Events: emit("disconnected")
```

### 關鍵元件

| 元件 | 職責 | 頁面 |
|------|------|------|
| `AsyncModbusDevice` | Modbus 輪詢設備，ReadScheduler 驅動 | [[_MOC Equipment]] |
| `AsyncCANDevice` | CAN 訂閱設備，snapshot_loop 週期發射事件 | [[AsyncCANDevice]] |
| `DeviceEventEmitter` | 統一事件分發（connected/read_complete/value_change 等） | [[_MOC Equipment]] |
| `AlarmStateManager` | 告警狀態管理與 `is_protected` 旗標 | [[_MOC Equipment]] |
| `PeriodicSendScheduler` | CAN 定期發送排程（TX 週期控制） | [[PeriodicSendScheduler]] |

---

## 5. 功率分配流程圖

從 `Strategy.execute()` 輸出到各設備寫入的完整路徑，重點展示 `PowerDistributor` 的三種分配策略。

```mermaid
flowchart LR
    A([Strategy.execute]) --> B["Command\n(P=1000, Q=200)"]
    B --> C[ProtectionGuard.apply]
    C --> D["Protected Command\n(P=950, Q=200)"]

    D --> E{有 PowerDistributor?}

    E -->|否| F[CommandRouter.route\n同值廣播]
    F --> G1[設備 A ← P=950]
    F --> G2[設備 B ← P=950]
    F --> G3[設備 C ← P=950]

    E -->|是| H[_build_device_snapshots\n過濾 responsive + non-protected]
    H --> I{分配策略}

    I -->|EqualDistributor| J["P/N, Q/N\n均分（不考慮額定容量）"]
    I -->|ProportionalDistributor| K["按 rated_p 比例\n額定值為零時 fallback 均分"]
    I -->|SOCBalancingDistributor| L["P: 按 rated_p × SOC 偏差權重\nQ: 按 rated_p 比例\n無 SOC 資料時 fallback 比例分配"]

    J & K & L --> M[route_per_device\ndevice_id → Command 映射]
    M --> N1[設備 A ← P=317]
    M --> N2[設備 B ← P=317]
    M --> N3[設備 C ← P=316]
```

### 關鍵元件

| 元件 | 職責 | 頁面 |
|------|------|------|
| `EqualDistributor` | 均分分配，適合規格相同的設備群 | [[PowerDistributor]] |
| `ProportionalDistributor` | 按 `rated_p`（或自訂 key）比例分配 | [[PowerDistributor]] |
| `SOCBalancingDistributor` | P 依 SOC 偏差調整，Q 按額定比例 | [[PowerDistributor]] |
| `DeviceSnapshot` | 設備狀態快照（metadata + latest_values + capabilities） | [[PowerDistributor]] |
| `CommandRouter.route_per_device` | 將 per-device Command 映射寫入各設備 | [[CommandRouter]] |

---

## 6. 事件驅動 Override 評估流程圖

展示 `_evaluate_event_overrides()` 在每個執行週期中對所有已註冊 `EventDrivenOverride` 的完整決策邏輯，包含冷卻計時機制。

```mermaid
flowchart TD
    A([_evaluate_event_overrides\n呼叫入口]) --> B[now = time.monotonic]
    B --> C[for each registered EventDrivenOverride]

    C --> D[override.should_activate\ncontext → bool]

    D --> E{should?}

    E -->|是| F{state.active?}
    F -->|否 → 首次啟用| G[state.active = True\nstate.deactivate_at = None]
    G --> H[push_override\nsource=EVENT]
    H --> I([Override 啟用\n日誌 WARNING])
    F -->|是 → 已啟用| J([維持活躍\n無動作])

    E -->|否| K{state.active?}
    K -->|否 → 未啟用| L([無動作])
    K -->|是 → 需評估冷卻| M{deactivate_at 已設定?}

    M -->|否 → 開始冷卻計時| N["deactivate_at =\nnow + override.cooldown_seconds"]
    N --> O{now >= deactivate_at?}
    M -->|是 → 繼續等待| O

    O -->|否 → 仍在冷卻中| P([維持活躍\n等待冷卻結束])
    O -->|是 → 冷卻結束| Q[state.active = False\nstate.deactivate_at = None]
    Q --> R[pop_override\nsource=EVENT]
    R --> S([Override 停用\n日誌 INFO])

    I & J & L & P & S --> T{還有其他 override?}
    T -->|是| C
    T -->|否| U([返回])

    style G fill:#FF9800,color:#fff
    style Q fill:#4CAF50,color:#fff
    style N fill:#2196F3,color:#fff
```

### 關鍵元件

| 元件 | 職責 | 頁面 |
|------|------|------|
| `EventDrivenOverride` | 條件驅動 override 的 Protocol（`should_activate` + `cooldown_seconds`） | [[EventDrivenOverride]] |
| `AlarmStopOverride` | 內建實作：`system_alarm == True` 時啟用停機 override | [[EventDrivenOverride]] |
| `ContextKeyOverride` | 內建實作：根據 `context.extra` 任意 key 觸發 override | [[EventDrivenOverride]] |
| `_OverrideState` | 內部狀態追蹤（`active` + `deactivate_at`） | [[SystemController]] |
| `ModeManager.push_override` | 以 `source=EVENT` 推入 override 並通知策略變更 | [[ModeManager]] |

---

## 相關頁面

| 類別 | 頁面 |
|------|------|
| 分層架構詳解 | [[Layered Architecture]] |
| 資料流說明 | [[Data Flow]] |
| 非同步模式 | [[Async Patterns]] |
| 事件系統 | [[Event System]] |
| Integration 模組索引 | [[_MOC Integration]] |
| Controller 模組索引 | [[_MOC Controller]] |
| Equipment 模組索引 | [[_MOC Equipment]] |
| SystemController API | [[SystemController]] |
| PowerDistributor API | [[PowerDistributor]] |
| ModeManager API | [[ModeManager]] |
| EventDrivenOverride API | [[EventDrivenOverride]] |
| CommandRouter API | [[CommandRouter]] |
| AsyncCANDevice API | [[AsyncCANDevice]] |
| DeviceProtocol API | [[DeviceProtocol]] |
| PeriodicSendScheduler API | [[PeriodicSendScheduler]] |
