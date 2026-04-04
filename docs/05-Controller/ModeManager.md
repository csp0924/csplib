---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/system/mode.py
created: 2026-02-17
updated: 2026-04-04
version: ">=0.4.2"
---

# ModeManager

模式管理器，負責模式註冊與優先權切換。

> [!info] 回到 [[_MOC Controller]]

## 概述

ModeManager 管理多個模式的註冊與切換，支援 **base mode** (基礎模式) 與 **override 堆疊** (覆蓋模式)。多個 override 同時活躍時，取 priority 最高者；無 override 時回退到 base mode。策略變更時透過 `on_strategy_change` callback 通知外部。

## SwitchSource 列舉

模式切換來源，用於審計追蹤。

```python
from csp_lib.controller.system.mode import SwitchSource

class SwitchSource(Enum):
    MANUAL   = "manual"    # 操作員手動切換
    SCHEDULE = "schedule"  # 排程驅動切換
    EVENT    = "event"     # 事件驅動（EventDrivenOverride）
    INTERNAL = "internal"  # 框架內部生命週期
```

`ModeManager.last_switch_source` 記錄最近一次切換的來源，便於日誌分析與事後排查。詳見 [[EventDrivenOverride]]。

## ModePriority 列舉

| 等級 | 值 | 說明 |
|------|-----|------|
| `SCHEDULE` | 10 | 排程模式 |
| `MANUAL` | 50 | 手動模式 |
| `PROTECTION` | 100 | 保護模式 (最高優先) |

## ModeDefinition

`@dataclass(frozen=True)` 的模式定義。

| 屬性 | 型別 | 說明 |
|------|------|------|
| `name` | `str` | 模式名稱 (唯一) |
| `strategy` | [[Strategy]] | 策略實例 |
| `priority` | `int` | 優先等級 (數值越大越優先) |
| `description` | `str` | 模式描述 |

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `on_strategy_change` | `Callable[[Strategy\|None, Strategy\|None], Awaitable[None]]` (Optional) | 策略變更時的回呼 |

## 方法

### 註冊 / 移除

| 方法 | 說明 |
|------|------|
| `register(name, strategy, priority, description)` | 註冊模式 (名稱唯一) |
| `unregister(name)` | 移除模式，同時清理 base 與 override 引用 |

### 基礎模式

| 方法 | 說明 |
|------|------|
| `set_base_mode(name, *, source=None)` | 設定單一基礎模式 (清除列表後設定)；`source` 為可選 `SwitchSource`，用於審計 |
| `add_base_mode(name, *, source=None)` | 新增基礎模式 (多 base mode 共存)；`source` 為可選 `SwitchSource`，用於審計 |
| `remove_base_mode(name, *, source=None)` | 移除指定基礎模式；`source` 為可選 `SwitchSource`，用於審計 |

### 模式策略更新（v0.4.2 新增）

| 方法 | 說明 |
|------|------|
| `update_mode_strategy(name, strategy, *, source=None, description=None)` | 原子替換已註冊模式的策略（含生命週期 hooks） |
| `async_unregister(name, *, source=None)` | 非同步移除模式（先執行 `on_deactivate()`，再觸發 `_notify_change`） |

#### `update_mode_strategy(name, strategy, *, source=None, description=None)`

原子操作，替換指定模式的策略實例，無需先 unregister 再 register。

- 若該模式當前為活躍狀態（在 base mode 或 override 中），自動依序呼叫：
  1. `old_strategy.on_deactivate()`
  2. 更新 `ModeDefinition`（strategy + 可選 description）
  3. `new_strategy.on_activate()`
  4. `_notify_change(old_strategy, new_strategy)` → 觸發 `on_strategy_change` callback
- 若該模式不在活躍狀態，僅更新 `ModeDefinition`，不觸發 activate/deactivate

| 參數 | 型別 | 說明 |
|------|------|------|
| `name` | `str` | 模式名稱（必須已註冊，否則拋出 `KeyError`） |
| `strategy` | `Strategy` | 新策略實例 |
| `source` | `SwitchSource \| None` | 切換來源（可選，審計用） |
| `description` | `str \| None` | 新描述（可選；`None` 時保留原描述） |

> [!note] 與 unregister + register 的差異
> `update_mode_strategy()` 保留模式的 `priority` 與名稱，策略替換為原子操作。
> 若使用 `unregister()` + `register()` 兩步驟，base mode 名稱列表可能在中間狀態產生不一致。

#### `async_unregister(name, *, source=None)`

非同步移除模式，確保在模式活躍時正確執行生命週期清理。

| 參數 | 型別 | 說明 |
|------|------|------|
| `name` | `str` | 模式名稱（必須已註冊，否則拋出 `KeyError`） |
| `source` | `SwitchSource \| None` | 切換來源（可選，審計用） |

> [!note] 與 `unregister()` 的差異
> 同步的 `unregister()` 不處理生命週期 hooks，也不觸發 `on_strategy_change`。
> `async_unregister()` 在移除前先執行 `on_deactivate()`，並觸發 `_notify_change`，適合在模式可能處於活躍狀態時使用。

### Override 堆疊

| 方法 | 說明 |
|------|------|
| `push_override(name, *, source=None)` | 推入 override 模式；`source` 為可選 `SwitchSource`，用於審計 |
| `pop_override(name, *, source=None)` | 移除指定 override 模式；`source` 為可選 `SwitchSource`，用於審計 |
| `clear_overrides()` | 清除所有 override |

> [!note] source 參數
> `set_base_mode`、`add_base_mode`、`remove_base_mode`、`push_override`、`pop_override`、`update_mode_strategy`、`async_unregister` 均接受可選的 `source: SwitchSource | None` 關鍵字引數。傳入時會更新 `last_switch_source`，便於審計追蹤切換來源。

### 查詢

| 屬性 | 型別 | 說明 |
|------|------|------|
| `effective_mode` | `ModeDefinition\|None` | 當前生效的模式 |
| `effective_strategy` | `Strategy\|None` | 當前生效的策略 |
| `base_mode_name` | `str\|None` | 基礎模式名稱 (向下相容，多 base mode 時回傳第一個) |
| `base_mode_names` | `list[str]` | 所有 base mode 名稱 (依 priority 降序) |
| `base_strategies` | `list[Strategy]` | 所有 base mode 的策略 (依 priority 降序) |
| `active_override_names` | `list[str]` | 活躍的 override 名稱列表 |
| `registered_modes` | `dict[str, ModeDefinition]` | 所有已註冊模式 |
| `last_switch_source` | `SwitchSource\|None` | 最近一次模式切換的來源（審計用） |

## 程式碼範例

```python
from csp_lib.controller import ModeManager, ModePriority

manager = ModeManager(on_strategy_change=handle_change)

# Register modes
manager.register("schedule", schedule_strategy, ModePriority.SCHEDULE)  # 10
manager.register("manual", pq_strategy, ModePriority.MANUAL)           # 50
manager.register("protection", stop_strategy, ModePriority.PROTECTION) # 100

# Base mode
await manager.set_base_mode("schedule")

# Override stack (highest priority wins)
await manager.push_override("protection")
# -> effective strategy = stop_strategy
await manager.pop_override("protection")
# -> effective strategy = schedule_strategy

# Multi base mode
await manager.add_base_mode("pq")
await manager.add_base_mode("qv")
# -> effective_strategy returns None (use CascadingStrategy for multi-mode)
```

> [!note] 多 base mode 時 `effective_strategy` 回傳 `None`，應由 SystemController 組合為 [[CascadingStrategy]]。

## 進階用法（v0.4.2 新增）

### 動態策略替換（排程場景）

```python
# 初次設定排程模式
manager.register("__schedule__", schedule_strategy_v1, ModePriority.SCHEDULE)
await manager.add_base_mode("__schedule__", source=SwitchSource.SCHEDULE)

# 排程規則更新時，原子替換策略（不需重新 register）
await manager.update_mode_strategy(
    "__schedule__",
    schedule_strategy_v2,
    source=SwitchSource.SCHEDULE,
    description="Night peak strategy",
)
# -> 自動呼叫 v1.on_deactivate() + v2.on_activate() + notify_change
```

### 安全移除活躍模式

```python
# 比同步的 unregister() 更安全，會先執行 on_deactivate()
await manager.async_unregister("__schedule__", source=SwitchSource.SCHEDULE)
```

## 相關連結

- [[Strategy]] — 模式所包裝的策略
- [[StrategyExecutor]] — 透過 `on_strategy_change` 回呼與 ModeManager 協作
- [[CascadingStrategy]] — 多 base mode 時的策略組合方案
- [[EventDrivenOverride]] — 事件驅動自動 push/pop override 機制（SwitchSource.EVENT 的主要來源）
- [[ProtectionGuard]] — 保護規則通常搭配 PROTECTION 等級的 override
- [[ScheduleModeController]] — 排程模式控制協定，使用 `update_mode_strategy()` 實現原子策略替換
- [[StrategyDiscovery]] — 策略插件自動發現機制
