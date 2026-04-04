---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/system_controller.py
updated: 2026-04-04
version: ">=0.4.2"
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
| `capability_context_mappings` | `list[CapabilityContextMapping]` | `[]` | Capability-driven context 映射 |
| `capability_command_mappings` | `list[CapabilityCommandMapping]` | `[]` | Capability-driven command 映射 |
| `system_base` | `SystemBase \| None` | `None` | 系統基準值 |
| `data_feed_mapping` | [[DataFeedMapping]] `\| None` | `None` | PV 資料餵入映射 |
| `pv_max_history` | `int` | `300` | PVDataService 最大歷史記錄數 |
| `protection_rules` | `list[ProtectionRule]` | `[]` | 保護規則列表 |
| `auto_stop_on_alarm` | `bool` | `True` | 系統告警時自動推入 stop override |
| `system_alarm_key` | `str` | `"system_alarm"` | system_alarm 在 context.extra 中的 key |
| `capacity_kva` | `float \| None` | `None` | 級聯策略最大視在功率（kVA） |
| `alarm_mode` | `str` | `"system_wide"` | 告警模式：`"system_wide"` 全系統停機 / `"per_device"` 僅告警設備關機 |
| `heartbeat_mappings` | `list[HeartbeatMapping]` | `[]` | 心跳寫入映射列表 |
| `heartbeat_interval` | `float` | `1.0` | 心跳寫入間隔（秒） |
| `use_heartbeat_capability` | `bool` | `False` | 啟用 HEARTBEAT 能力發現模式 |
| `heartbeat_capability_mode` | `HeartbeatMode` | `TOGGLE` | 能力發現模式的心跳值模式 |
| `heartbeat_capability_constant_value` | `int` | `1` | CONSTANT 模式的固定寫入值 |
| `heartbeat_capability_increment_max` | `int` | `65535` | INCREMENT 模式的最大計數值 |
| `power_distributor` | `PowerDistributor \| None` | `None` | 功率分配器；設定後 capability command mappings 使用 per-device 分配 |

## API

### 模式管理

| 方法 | 說明 |
|------|------|
| `register_mode(name, strategy, priority, description="")` | 註冊模式（驗證 `strategy.required_capabilities`） |
| `set_base_mode(name)` | 設定基礎模式 |
| `add_base_mode(name)` | 新增基礎模式（多 base mode 共存） |
| `remove_base_mode(name)` | 移除基礎模式 |
| `push_override(name)` | 推入 override 模式 |
| `pop_override(name)` | 移除 override 模式 |
| `register_event_override(override)` | 註冊事件驅動 override（見[[EventDrivenOverride]]） |
| `trigger()` | 手動觸發策略執行 |

### 排程模式控制（v0.4.2 新增）

`SystemController` 實作 [[ScheduleModeController]] Protocol，供 `ScheduleService` 透過協定介面驅動模式切換，無需直接依賴 Integration 層。

| 方法 | 說明 |
|------|------|
| `activate_schedule_mode(strategy, *, description="")` | 啟用排程模式（首次呼叫時自動註冊，後續呼叫原子替換策略） |
| `deactivate_schedule_mode()` | 停用排程模式（從 base mode 移除 `__schedule__`） |

#### `activate_schedule_mode(strategy, *, description="")`

```python
async def activate_schedule_mode(
    self, strategy: Strategy, *, description: str = ""
) -> None
```

內部流程：

1. 若 `__schedule__` 模式**尚未註冊**：呼叫 `mm.register(...)` 並呼叫 `mm.add_base_mode("__schedule__", source=SwitchSource.SCHEDULE)`
2. 若 `__schedule__` 模式**已存在**：呼叫 `mm.update_mode_strategy("__schedule__", strategy, source=SwitchSource.SCHEDULE, description=description)`，確保策略原子替換並觸發 `on_strategy_change`；若此時 `__schedule__` 不在 base mode 中，額外呼叫 `add_base_mode` 重新加入

#### `deactivate_schedule_mode()`

```python
async def deactivate_schedule_mode(self) -> None
```

若 `__schedule__` 在 base mode 列表中，呼叫 `mm.remove_base_mode("__schedule__")`；否則靜默不做任何動作。

> [!note] 模式名稱常數
> 內部使用固定常數 `_SCHEDULE_MODE = "__schedule__"` 而非動態名稱（每條規則一個模式）。這確保同一時間最多只有一個排程策略活躍，策略切換走原子的 `update_mode_strategy()` 路徑。

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
| `auto_stop_active` | 自動停機是否啟動（向後相容，由 EventDrivenOverride 機制維護） |
| `event_overrides` | 已註冊的事件驅動 override 列表 |
| `is_running` | 是否正在執行 |

## 內部流程

```
ContextBuilder.build() -> StrategyContext (inject system_alarm)
  (ContextMapping + CapabilityContextMapping)
       |
StrategyExecutor (strategy decided by ModeManager)
       |
Command (raw) -> ProtectionGuard.apply() -> Command (protected)
       |
_evaluate_event_overrides(context) -> push/pop override (ModeManager)
       |
CommandRouter.route() -> Device writes
  (CommandMapping + CapabilityCommandMapping)

HeartbeatService (parallel)
  (HeartbeatMapping + use_heartbeat_capability)
```

## 事件驅動 Override

`SystemController` 支援透過 `register_event_override()` 註冊 [[EventDrivenOverride]] 實例，在每個命令週期自動評估條件並切換模式。

### register_event_override()

```python
def register_event_override(self, override: EventDrivenOverride) -> None:
    """
    註冊事件驅動的 override

    Args:
        override: 實作 EventDrivenOverride 的實例，
                  name 必須對應已在 ModeManager 中 register() 的模式名稱
    """
```

> [!important] 順序要求
> 必須先呼叫 `register_mode()` 將對應模式名稱加入 `ModeManager`，再呼叫 `register_event_override()`。若 `override.name` 對應的模式不存在，`push_override` 在執行期會靜默忽略（`KeyError` 被捕獲並記錄 warning）。

### Override 評估時機

`_evaluate_event_overrides()` 在 `_on_command()` 的命令流程中、`ProtectionGuard` 套用之後、`CommandRouter.route()` 之前執行：

```
ProtectionGuard.apply() → Command (protected)
    ↓
_evaluate_event_overrides(context)   ← 此處評估所有 EventDrivenOverride
    ↓
CommandRouter.route()
```

每個 override 維護獨立的狀態（active / deactivate_at），以 `time.monotonic()` 實現 cooldown 計時，互不干擾。

### auto_stop_on_alarm 的內部實現

`SystemControllerConfig.auto_stop_on_alarm=True`（預設值）時，`SystemController.__init__` 自動執行：

```python
# 1. 內部自動建立 Stop 模式
self._mode_manager.register(
    "__auto_stop__",
    StopStrategy(),
    ModePriority.PROTECTION + 1,
    "Auto stop on system alarm",
)

# 2. 以 AlarmStopOverride 實現觸發邏輯
self.register_event_override(
    AlarmStopOverride(name="__auto_stop__", alarm_key=config.system_alarm_key)
)
```

`_handle_auto_stop()` 方法仍然存在（向後相容），但內部實作已委派給 `_evaluate_event_overrides()`，行為與先前版本完全一致。

### 範例：ACB 跳脫自動進入離網

```python
from csp_lib.controller.system.event_override import ContextKeyOverride
from csp_lib.controller import ModePriority
from csp_lib.controller.strategies import IslandModeStrategy

# 1. 先註冊模式
controller.register_mode(
    "islanding",
    IslandModeStrategy(...),
    priority=ModePriority.PROTECTION,
)

# 2. 建立並註冊事件 override
controller.register_event_override(
    ContextKeyOverride(
        name="islanding",
        context_key="acb_trip",           # ContextBuilder 注入的感測值
        activate_when=lambda v: v is True,
        cooldown_seconds=10.0,
    )
)
# 之後每個週期自動評估，ACB 跳脫時自動切換到離網模式
```

詳細說明見 [[EventDrivenOverride]]。

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
- [[EventDrivenOverride]] — 事件驅動的自動 Override 協定與內建實現
- [[ScheduleModeController]] — 排程模式控制協定（`SystemController` 的實作目標）
- [[ModeManager]] — 底層模式管理，`update_mode_strategy()` 由此提供
- [[CapabilityContextMapping]] — Capability-driven context 映射
- [[CapabilityCommandMapping]] — Capability-driven command 映射
- [[CapabilityBinding Integration]] — 能力驅動整合的完整架構與流程圖
