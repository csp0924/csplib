---
tags:
  - type/architecture
  - layer/integration
  - status/complete
created: 2026-03-06
updated: 2026-04-04
version: ">=0.4.2"
---

# CapabilityBinding Integration

能力驅動的設備整合 -- 架構與流程圖，隸屬於 [[_MOC Integration|Integration 模組]]。

## 設計動機

csp_lib 的 Capability 系統定義了 9 個標準能力（HEARTBEAT、ACTIVE_POWER_CONTROL 等），每個能力使用語意插槽 (slot) 描述讀/寫操作。不同設備透過 `CapabilityBinding` 將 slot 映射到各自的實際點位名稱。

本整合讓 Capability 從純粹的 metadata 宣告，升級為設備整合的驅動力：

- **讀取**：[[CapabilityContextMapping]] 用 capability slot 自動解析點位
- **寫入**：[[CapabilityCommandMapping]] 用 capability slot 自動路由寫入
- **心跳**：`use_heartbeat_capability` 自動發現 HEARTBEAT 設備
- **驗證**：`Strategy.required_capabilities` 在註冊時檢查設備能力

## 層級架構圖

```mermaid
graph TB
    subgraph L3["Layer 3 -- Equipment"]
        CAP["Capability<br/><i>name, read_slots, write_slots</i>"]
        CB["CapabilityBinding<br/><i>capability + point_map</i>"]
        DEV["AsyncModbusDevice<br/><i>has_capability(), resolve_point()</i>"]
        TPL["EquipmentTemplate<br/><i>宣告 bindings</i>"]

        TPL -->|"宣告"| CB
        CB -->|"綁定"| CAP
        DEV -->|"儲存"| CB
    end

    subgraph L4["Layer 4 -- Controller"]
        STR["Strategy ABC<br/><i>+ required_capabilities</i>"]
    end

    subgraph L6["Layer 6 -- Integration"]
        REG["DeviceRegistry<br/><i>get_devices_with_capability()<br/>get_responsive_devices_with_capability()</i>"]

        subgraph READ["讀取路徑"]
            CTX_M["ContextMapping<br/><i>明確 point_name</i>"]
            CAP_CTX["CapabilityContextMapping<br/><i>capability + slot</i>"]
            CTX_B["ContextBuilder<br/><i>build()</i>"]
        end

        subgraph WRITE["寫入路徑"]
            CMD_M["CommandMapping<br/><i>明確 point_name</i>"]
            CAP_CMD["CapabilityCommandMapping<br/><i>capability + slot</i>"]
            CMD_R["CommandRouter<br/><i>route()</i>"]
        end

        subgraph HEARTBEAT["心跳路徑"]
            HB_M["HeartbeatMapping<br/><i>明確 point_name</i>"]
            HB_CAP["use_heartbeat_capability<br/><i>HEARTBEAT 能力</i>"]
            HB_S["HeartbeatService<br/><i>_send_heartbeats()</i>"]
        end

        SC["SystemController<br/><i>register_mode() 驗證 capabilities</i>"]
        SC_CFG["SystemControllerConfig"]
    end

    SC_CFG -->|"context_mappings"| CTX_B
    SC_CFG -->|"capability_context_mappings"| CTX_B
    SC_CFG -->|"command_mappings"| CMD_R
    SC_CFG -->|"capability_command_mappings"| CMD_R
    SC_CFG -->|"heartbeat_mappings"| HB_S
    SC_CFG -->|"use_heartbeat_capability"| HB_S

    CTX_B --> REG
    CMD_R --> REG
    HB_S --> REG
    REG --> DEV

    STR -.->|"required_capabilities"| SC
    SC -.->|"warning if missing"| REG

    style CAP_CTX fill:#4CAF50,color:#fff
    style CAP_CMD fill:#2196F3,color:#fff
    style HB_CAP fill:#FF9800,color:#fff
    style STR fill:#9C27B0,color:#fff
```

## 控制迴圈流程圖

完整的 Pipeline：讀取 → 策略執行 → 保護 → 寫入（含心跳並行）。

```mermaid
flowchart TD
    START(["StrategyExecutor 觸發"])

    subgraph BUILD["_build_context()"]
        direction TB
        B1["遍歷 ContextMapping<br/><i>明確 point_name 讀取</i>"]
        B2["遍歷 CapabilityContextMapping"]
        B2 --> B2a{scoping?}
        B2a -->|"device_id"| B2b["_read_capability_single<br/>resolve_point -> latest_values"]
        B2a -->|"trait"| B2c["_read_capability_trait<br/>filter has_capability -> aggregate"]
        B2a -->|"None/None"| B2d["_read_capability_auto<br/>get_responsive_with_capability -> aggregate"]
        B1 --> CTX["StrategyContext"]
        B2b --> CTX
        B2c --> CTX
        B2d --> CTX
        CTX --> INJ["注入 system_alarm 旗標"]
    end

    subgraph EXEC["策略執行"]
        direction TB
        E1["ModeManager -> resolve_strategy()"]
        E2["strategy.execute(context)"]
        E1 --> E2
        E2 --> CMD["Command"]
    end

    subgraph PROTECT["保護鏈"]
        PG["ProtectionGuard.apply()"]
        PG --> PCMD["Protected Command"]
    end

    PCMD --> DIST_CHECK{power_distributor\n已設定?}

    subgraph DIST["PowerDistributor（可選）"]
        direction TB
        DS["_build_device_snapshots()"]
        DA["distributor.distribute(command, snapshots)"]
        DS --> DA
    end

    subgraph ROUTE_PD["CommandRouter.route_per_device()"]
        direction TB
        RPD["per-device Command 寫入"]
        RPD --> DEV_W2["device.write()"]
    end

    subgraph ROUTE["CommandRouter.route()"]
        direction TB
        R1["遍歷 CommandMapping<br/><i>明確 point_name 寫入</i>"]
        R2["遍歷 CapabilityCommandMapping"]
        R2 --> R2a{scoping?}
        R2a -->|"device_id"| R2b["_write_capability_single<br/>has_capability -> resolve_point -> write"]
        R2a -->|"trait"| R2c["_write_capability_trait<br/>filter capable -> resolve_point -> write"]
        R2a -->|"None/None"| R2d["_write_capability_auto<br/>get_responsive_with_capability -> write"]
        R1 --> DEV_W["device.write()"]
        R2b --> DEV_W
        R2c --> DEV_W
        R2d --> DEV_W
    end

    subgraph HB["HeartbeatService（並行）"]
        direction TB
        H1["遍歷 HeartbeatMapping<br/><i>明確映射</i>"]
        H2["use_capability=True?"]
        H2 -->|"Yes"| H3["get_responsive_with_capability(HEARTBEAT)<br/>resolve_point -> write"]
        H1 --> HW["device.write(heartbeat)"]
        H3 --> HW
    end

    START --> BUILD
    BUILD --> EXEC
    EXEC --> PROTECT
    PROTECT --> DIST_CHECK
    DIST_CHECK -->|"否（預設）"| ROUTE
    DIST_CHECK -->|"是"| DIST
    DIST --> ROUTE_PD

    style B2 fill:#4CAF50,color:#fff
    style R2 fill:#2196F3,color:#fff
    style H2 fill:#FF9800,color:#fff
    style DIST fill:#4CAF50,color:#fff
    style DIST_CHECK fill:#FFF3E0,stroke:#FF9800
    style ROUTE_PD fill:#2196F3,color:#fff
```

## Capability 解析序列圖

展示 `resolve_point` 在讀取路徑中的完整呼叫鏈。

```mermaid
sequenceDiagram
    participant CB as ContextBuilder / CommandRouter
    participant REG as DeviceRegistry
    participant DEV as AsyncModbusDevice
    participant BIND as CapabilityBinding

    Note over CB: CapabilityContextMapping<br/>capability=SOC_READABLE, slot="soc"

    alt device_id 模式
        CB->>REG: get_device("bess_01")
        REG-->>CB: device
    else trait 模式
        CB->>REG: get_responsive_devices_by_trait("bess")
        REG-->>CB: [device_A, device_B]
        CB->>CB: filter has_capability(SOC_READABLE)
    else auto 模式 (device_id=None, trait=None)
        CB->>REG: get_responsive_devices_with_capability(SOC_READABLE)
        REG-->>CB: [device_A, device_C]
    end

    loop 每台設備
        CB->>DEV: resolve_point(SOC_READABLE, "soc")
        DEV->>BIND: resolve("soc")
        Note over BIND: point_map = {"soc": "battery_soc_pct"}
        BIND-->>DEV: "battery_soc_pct"
        DEV-->>CB: "battery_soc_pct"
        CB->>DEV: latest_values.get("battery_soc_pct")
        DEV-->>CB: 85.3
    end

    CB->>CB: aggregate([85.3, 72.1]) -> 78.7
```

## Strategy 能力驗證流程

```mermaid
flowchart LR
    A["controller.register_mode<br/>('pq', pq_strategy, ...)"] --> B{"strategy.required_capabilities<br/>is empty?"}
    B -->|"Yes"| D["直接註冊<br/>ModeManager.register()"]
    B -->|"No"| C["遍歷 required capabilities"]
    C --> E{"registry 有設備<br/>具備此 capability?"}
    E -->|"Yes"| F["Pass"]
    E -->|"No"| G["logger.warning<br/><i>不 raise，設備可能晚加入</i>"]
    F --> D
    G --> D

    style G fill:#FFF3E0,stroke:#FF9800
    style D fill:#E8F5E9,stroke:#4CAF50
```

## 三種 Scoping 模式對照

| | device_id 模式 | trait 模式 | auto 模式 |
|---|---|---|---|
| `device_id` | `"pcs_01"` | `None` | `None` |
| `trait` | `None` | `"pcs"` | `None` |
| Context 讀取來源 | 單一設備 | trait 內 capable 設備 | 所有 capable 設備 |
| Command 寫入目標 | 單一設備 | trait 內廣播 | 所有 capable 廣播 |
| 聚合 | 不聚合 | aggregate 函式 | aggregate 函式 |
| 點位解析 | `device.resolve_point(capability, slot)` | 同左 | 同左 |

## 向後相容性

| 項目 | 相容性 | 說明 |
|------|--------|------|
| `SystemControllerConfig` | 完全相容 | 新欄位皆有預設值 |
| `ContextBuilder` | 完全相容 | `capability_mappings` 預設 `None` |
| `CommandRouter` | 完全相容 | `capability_mappings` 預設 `None` |
| `Strategy` ABC | 完全相容 | `required_capabilities` 預設 `()` |
| `HeartbeatService` | 不變 | 已支援 `use_capability` |
| 既有 `ContextMapping` / `CommandMapping` | 不變 | 明確映射路徑完全保留 |
| `PowerDistributor` | 完全相容 | `power_distributor` 預設 `None`，不設定時行為不變 |

## 層級邊界驗證

| 變更 | 依賴方向 | 合規 |
|------|----------|------|
| `schema.py` 引用 `Capability` | Layer 6 → Layer 3 | 合規 |
| `context_builder.py` 使用 `has_capability()` | Layer 6 → Layer 3 | 合規 |
| `command_router.py` 使用 `resolve_point()` | Layer 6 → Layer 3 | 合規 |
| `strategy.py` TYPE_CHECKING `Capability` | Layer 4 → Layer 3 (type only) | 合規 |
| `system_controller.py` 驗證 capabilities | Layer 6 → Layer 3, 4 | 合規 |

## 完整使用範例

```python
from csp_lib.equipment.device.capability import (
    ACTIVE_POWER_CONTROL, HEARTBEAT, MEASURABLE, SOC_READABLE,
)
from csp_lib.integration import (
    SystemController, SystemControllerConfig,
    CapabilityContextMapping, CapabilityCommandMapping,
    AggregateFunc,
)

config = SystemControllerConfig(
    # Heartbeat：自動發現，不需要明確 mapping
    use_heartbeat_capability=True,

    # Context：用 capability 讀取 SOC 和功率
    capability_context_mappings=[
        CapabilityContextMapping(
            capability=SOC_READABLE, slot="soc", context_field="soc",
        ),
        CapabilityContextMapping(
            capability=MEASURABLE, slot="active_power",
            context_field="extra.grid_power",
            aggregate=AggregateFunc.SUM,
        ),
    ],

    # Command：用 capability 寫入 P setpoint
    capability_command_mappings=[
        CapabilityCommandMapping(
            command_field="p_target",
            capability=ACTIVE_POWER_CONTROL, slot="p_setpoint",
        ),
    ],
)

controller = SystemController(registry, config)
# 明確 mapping 和 capability mapping 可共存
```

## 相關頁面

- [[CapabilityRequirement]] -- 能力需求定義（preflight validation）
- [[CapabilityContextMapping]] -- Capability-driven context 映射
- [[CapabilityCommandMapping]] -- Capability-driven command 映射
- [[ContextMapping]] -- 明確映射版 context
- [[CommandMapping]] -- 明確映射版 command
- [[ContextBuilder]] -- 讀取路徑實作
- [[CommandRouter]] -- 寫入路徑實作
- [[PowerDistributor]] -- 功率分配器
- [[SystemController]] -- 頂層控制器配置
- [[DeviceRegistry]] -- 設備 capability 查詢
- [[Strategy]] -- `required_capabilities` 宣告
