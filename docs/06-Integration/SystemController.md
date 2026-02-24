---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/system_controller.py
---

# SystemController

進階系統控制器，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`SystemController` 是 [[GridControlLoop]] 的進階版本，在完整控制迴圈的基礎上整合了 `ModeManager`（模式管理）與 `ProtectionGuard`（保護機制）。繼承 `AsyncLifecycleMixin`，支援 `async with` 使用。

### 核心能力

- **模式管理**：透過 `ModeManager` 註冊多種模式（schedule、manual 等），以優先權決定生效策略
- **保護機制**：透過 `ProtectionGuard` 套用 SOC 限制、逆送保護等保護規則
- **自動告警處理**：設備告警時自動推入 stop override（`system_wide` 模式）或逐設備關機（`per_device` 模式）
- **級聯策略**：設定 `capacity_kva` 時，多 base mode 共存自動啟用 `CascadingStrategy`

## SystemControllerConfig

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `context_mappings` | `list[ContextMapping]` | `[]` | 設備點位 → StrategyContext 映射 |
| `command_mappings` | `list[CommandMapping]` | `[]` | Command 欄位 → 設備寫入映射 |
| `system_base` | `SystemBase \| None` | `None` | 系統基準值 |
| `data_feed_mapping` | [[DataFeedMapping]] `\| None` | `None` | PV 資料餵入映射 |
| `pv_max_history` | `int` | `300` | PVDataService 最大歷史記錄數 |
| `protection_rules` | `list[ProtectionRule]` | `[]` | 保護規則列表 |
| `auto_stop_on_alarm` | `bool` | `True` | 系統告警時自動推入 stop override |
| `system_alarm_key` | `str` | `"system_alarm"` | system_alarm 在 context.extra 中的 key |
| `capacity_kva` | `float \| None` | `None` | 級聯策略最大視在功率（kVA） |
| `alarm_mode` | `str` | `"system_wide"` | 告警模式：`"system_wide"` 全系統停機 / `"per_device"` 僅告警設備關機 |

## API

### 模式管理

| 方法 | 說明 |
|------|------|
| `register_mode(name, strategy, priority, description="")` | 註冊模式 |
| `set_base_mode(name)` | 設定基礎模式 |
| `add_base_mode(name)` | 新增基礎模式（多 base mode 共存） |
| `remove_base_mode(name)` | 移除基礎模式 |
| `push_override(name)` | 推入 override 模式 |
| `pop_override(name)` | 移除 override 模式 |
| `trigger()` | 手動觸發策略執行 |

### 唯讀屬性

| 屬性 | 說明 |
|------|------|
| `registry` | 設備查詢索引 |
| `executor` | 策略執行器 |
| `mode_manager` | 模式管理器 |
| `protection_guard` | 保護鏈 |
| `effective_mode_name` | 當前生效的模式名稱 |
| `protection_status` | 最近一次保護結果 |
| `pv_service` | PV 資料服務 |
| `alarmed_device_ids` | 當前處於告警狀態的設備 ID 集合 |
| `auto_stop_active` | 自動停機是否啟動 |
| `is_running` | 是否正在執行 |

## 內部流程

```
ContextBuilder.build() -> StrategyContext (inject system_alarm)
       |
StrategyExecutor (strategy decided by ModeManager)
       |
Command (raw) -> ProtectionGuard.apply() -> Command (protected)
       |
CommandRouter.route() -> Device writes
```

## 使用範例

```python
from csp_lib.integration import SystemController, SystemControllerConfig
from csp_lib.controller import ModePriority, SOCProtection

config = SystemControllerConfig(
    context_mappings=[...],
    command_mappings=[...],
    system_base=SystemBase(p_base=1000, q_base=500),
    protection_rules=[SOCProtection(), ReversePowerProtection()],
    auto_stop_on_alarm=True,
    capacity_kva=1000,  # Enable CascadingStrategy for multi base mode
)

controller = SystemController(registry, config)

# Register modes
controller.register_mode("schedule", schedule_strategy, ModePriority.SCHEDULE)
controller.register_mode("manual", pq_strategy, ModePriority.MANUAL)

# Set mode
await controller.set_base_mode("schedule")

async with controller:
    # Full control loop with:
    #   ContextBuilder -> StrategyContext (+ system_alarm injection)
    #   StrategyExecutor (strategy from ModeManager)
    #   Command -> ProtectionGuard -> CommandRouter
    await asyncio.sleep(3600)
```

## 相關頁面

- [[GridControlLoop]] — 基礎版控制迴圈
- [[GroupControllerManager]] — 多群組控制器管理（管理多個獨立 SystemController）
- [[ContextBuilder]] — 設備值建構器
- [[CommandRouter]] — 命令路由器
- [[DeviceRegistry]] — 設備查詢索引
