---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/system_controller.py
created: 2026-02-17
updated: 2026-04-17
version: ">=0.8.1"
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
| `post_protection_processors` | `list[CommandProcessor]` | `[]` | Post-protection 命令處理器列表（如 [[PowerCompensator]]） |
| `runtime_params` | `RuntimeParameters \| None` | `None` | 系統參數，自動注入到 `StrategyContext.params` |
| `capability_requirements` | `list[CapabilityRequirement]` | `[]` | 能力需求列表，供 `preflight_check()` 驗證 |
| `strict_capability_check` | `bool` | `False` | 啟用嚴格能力檢查（preflight 失敗時 raise `ConfigurationError`） |
| `trigger_on_read_device_ids` | `list[str]` | `[]` | v0.8.0+：啟動時自動對這些 device_id 的 `EVENT_READ_COMPLETE` 事件綁定 executor 觸發 |
| `heartbeat` | `HeartbeatConfig \| None` | `None` | v0.8.1+：新版結構化心跳配置（取代下方 6 個 `heartbeat_*` 欄位） |
| `command_refresh` | `CommandRefreshConfig \| None` | `None` | v0.8.1+：命令刷新（reconciler）服務配置；`enabled=True` 時自動啟動 [[Command Refresh\|CommandRefreshService]] |

> [!info] 版本說明
> - v0.6.0 新增：`capability_requirements`、`strict_capability_check`、`post_protection_processors`、`runtime_params`
> - v0.8.0 新增：`trigger_on_read_device_ids`（宣告式 read-complete trigger 配置）
> - v0.8.1 新增：`heartbeat: HeartbeatConfig`、`command_refresh: CommandRefreshConfig`（結構化配置物件，取代舊有分散欄位）

> [!warning] 舊版 heartbeat_* 欄位（Deprecated，v1.0.0 移除）
> `heartbeat_mappings`、`heartbeat_interval`、`use_heartbeat_capability`、`heartbeat_capability_mode`、
> `heartbeat_capability_constant_value`、`heartbeat_capability_increment_max` 六個欄位在 v0.8.1 後
> 已由 `heartbeat: HeartbeatConfig` 取代，維持靜默相容（不 emit DeprecationWarning）至 v1.0.0。

### SystemControllerConfig.builder()

> [!info] v0.6.0 新增

`SystemControllerConfig.builder()` 回傳 `SystemControllerConfigBuilder`，提供 fluent API 逐步建構配置：

```python
from csp_lib.integration import SystemControllerConfig
from csp_lib.integration.schema import CapabilityRequirement

config = (
    SystemControllerConfig.builder()
    .system_base(p_base=2000)
    .map_context(device_id="MTD1", point_name="f", target="extra.frequency")
    .map_context(trait="bms", point_name="soc", target="soc")
    .map_command(field="p_target", device_id="PCS1", point_name="set_p")
    .protect(DynamicSOCProtection(params))
    .processor(compensator)
    .params(runtime_params)
    .require_capability(CapabilityRequirement(
        capability=ACTIVE_POWER_CONTROL, min_count=2,
    ))
    .strict_capability(True)
    .build()
)
```

#### Builder 方法一覽

| 方法 | 說明 |
|------|------|
| `system_base(p_base, q_base=0.0)` | 設定系統基準值 |
| `map_context(point_name, target, *, device_id, trait, ...)` | 新增 context mapping |
| `map_command(field, point_name, *, device_id, trait, ...)` | 新增 command mapping |
| `map_capability_context(mapping)` | 新增 capability context mapping |
| `map_capability_command(mapping)` | 新增 capability command mapping |
| `protect(rule)` | 新增保護規則 |
| `auto_stop(enabled=True, alarm_key="system_alarm")` | 設定自動停機 |
| `processor(proc)` | 新增 post-protection 命令處理器 |
| `params(runtime_params)` | 設定 RuntimeParameters |
| `distributor(dist)` | 設定功率分配器 |
| `heartbeat(mappings_or_config, interval, use_capability, mode)` | 設定心跳服務；v0.8.1+ 支援傳入 `HeartbeatConfig` positional 參數 |
| `command_refresh(interval_seconds, enabled, devices)` | v0.8.1+：啟用命令刷新 reconciler 服務 |
| `alarm_mode_per_device(on_alarm, on_clear)` | 設定 per-device 告警模式 |
| `data_feed(mapping, max_history=300)` | 設定 PV 資料餵入 |
| `cascading(capacity_kva)` | 設定級聯策略最大視在功率 |
| `require_capability(requirement)` | 新增能力需求（供 preflight 驗證） |
| `strict_capability(enabled=True)` | 啟用嚴格能力檢查 |
| `trigger_on_read_complete(device_id)` | v0.8.0+：宣告式 read-complete trigger（可多次呼叫多台設備） |
| `build()` | 建構 `SystemControllerConfig` |

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
| `attach_read_trigger(device_id)` | v0.8.0+：將指定設備的 `EVENT_READ_COMPLETE` 綁定為 executor 觸發，回傳 detacher callable |

### Preflight Check（v0.6.0 新增）

| 方法 | 說明 |
|------|------|
| `preflight_check()` | 驗證 `capability_requirements` 是否滿足，回傳失敗描述列表 |

`preflight_check()` 委派 `DeviceRegistry.validate_capabilities()` 驗證所有 [[CapabilityRequirement]]。啟動時（`_on_start()`）自動呼叫。

- 回傳空列表 = 全部通過
- `strict_capability_check=True` 時，有任何失敗會 raise `ConfigurationError`
- `strict_capability_check=False` 時（預設），僅記錄 warning 日誌

```python
failures = controller.preflight_check()
if failures:
    print("能力檢查未通過：", failures)
```

### Event-Driven Trigger（v0.8.0 新增）

`attach_read_trigger(device_id)` 將指定設備的 `EVENT_READ_COMPLETE` 事件綁定為 `StrategyExecutor.trigger()` 的呼叫源，達成「設備讀完即執行策略」的低延遲流程，避免時間錨式 PERIODIC 與 ReadScheduler 之間的 phase drift。

```python
def attach_read_trigger(self, device_id: str) -> Callable[[], None]
```

**行為**：
- 每次 `device_id` 的 `EVENT_READ_COMPLETE` 觸發，自動呼叫 `executor.trigger()`
- 重複 attach 同 device_id 拋 `ValueError`（fail-fast 冪等保護）
- `device_id` 未在 registry 拋 `ValueError`
- 回傳 wrapped detacher callable，呼叫即解除綁定

**宣告式方式（建議）**：透過 Builder 或 Config 設定，`_on_start` 自動 attach，`_on_stop` 自動 detach：

```python
config = (
    SystemControllerConfig.builder()
    .trigger_on_read_complete("meter_01")   # 讀完即觸發策略
    .trigger_on_read_complete("pcs_01")     # 可多台
    .build()
)

# 或等效直接設定 config 欄位
config = SystemControllerConfig(
    trigger_on_read_device_ids=["meter_01", "pcs_01"],
    ...
)
```

**命令式方式（執行期動態）**：

```python
detacher = controller.attach_read_trigger("meter_01")
# ... 使用一段時間後解除
detacher()
```

> [!note] 搭配使用
> 與 `ExecutionMode.TRIGGERED` 或 `HYBRID` 策略搭配使用。PERIODIC 模式搭配後策略雖仍按週期執行，但也可被提前觸發。

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
CommandRouter.route() -> Device writes  ← _last_written 追蹤 (v0.8.1)
  (CommandMapping + CapabilityCommandMapping)

HeartbeatService (parallel)
  (HeartbeatConfig.mappings + HeartbeatConfig.targets)  ← v0.8.1

CommandRefreshService (parallel, v0.8.1)
  每 interval 秒把 CommandRouter._last_written 重傳到設備
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

## v0.8.1 新增：HeartbeatConfig 與 CommandRefreshConfig

### HeartbeatConfig（新版心跳配置）

```python
from csp_lib.integration import HeartbeatConfig, HeartbeatTarget, DeviceHeartbeatTarget
from csp_lib.integration.heartbeat_generators import ToggleGenerator, IncrementGenerator

# 新版 API（v0.8.1）
config = (
    SystemControllerConfig.builder()
    .heartbeat(HeartbeatConfig(
        mappings=[
            HeartbeatMapping(
                device_id="pcs1",
                point_name="heartbeat_reg",
                value_generator=ToggleGenerator(),   # 取代 mode=HeartbeatMode.TOGGLE
            ),
        ],
        targets=[
            DeviceHeartbeatTarget(pcs2_device, "heartbeat_counter"),
            GatewayRegisterHeartbeatTarget(gateway, "ctrl_alive"),
        ],
        interval_seconds=1.0,
    ))
    .build()
)
```

### CommandRefreshConfig（v0.8.1 新增）

```python
from csp_lib.integration import CommandRefreshConfig

# Builder 方式（建議）
config = (
    SystemControllerConfig.builder()
    .command_refresh(
        interval_seconds=1.0,   # < PCS watchdog / 2
        enabled=True,
        devices=["pcs1", "pcs2"],   # None = 所有被追蹤設備
    )
    .build()
)

# 等效直接設定
config = SystemControllerConfig(
    command_refresh=CommandRefreshConfig(
        refresh_interval=1.0,
        enabled=True,
        device_filter=frozenset({"pcs1", "pcs2"}),
    ),
    # ...
)
```

> [!note] v0.8.1 生命週期啟動順序
> 啟動：command_refresh → heartbeat → executor（command_refresh 先於 heartbeat，避免首輪 reconcile 被 pause/resume 干擾；executor 最後掛 task）
> 停止：executor → heartbeat → command_refresh（先停新命令來源，再依序停輸出端）

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
- [[CapabilityRequirement]] — 能力需求定義（preflight validation）
- [[CapabilityBinding Integration]] — 能力驅動整合的完整架構與流程圖
- [[Command Refresh]] — CommandRefreshService 使用指南（v0.8.1）
- [[Reconciliation Pattern]] — reconciler 架構設計說明
