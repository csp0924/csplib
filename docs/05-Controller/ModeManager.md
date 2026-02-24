---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/system/mode.py
created: 2026-02-17
---

# ModeManager

模式管理器，負責模式註冊與優先權切換。

> [!info] 回到 [[_MOC Controller]]

## 概述

ModeManager 管理多個模式的註冊與切換，支援 **base mode** (基礎模式) 與 **override 堆疊** (覆蓋模式)。多個 override 同時活躍時，取 priority 最高者；無 override 時回退到 base mode。策略變更時透過 `on_strategy_change` callback 通知外部。

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
| `set_base_mode(name)` | 設定單一基礎模式 (清除列表後設定) |
| `add_base_mode(name)` | 新增基礎模式 (多 base mode 共存) |
| `remove_base_mode(name)` | 移除指定基礎模式 |

### Override 堆疊

| 方法 | 說明 |
|------|------|
| `push_override(name)` | 推入 override 模式 |
| `pop_override(name)` | 移除指定 override 模式 |
| `clear_overrides()` | 清除所有 override |

### 查詢

| 屬性 | 型別 | 說明 |
|------|------|------|
| `effective_mode` | `ModeDefinition\|None` | 當前生效的模式 |
| `effective_strategy` | `Strategy\|None` | 當前生效的策略 |
| `base_mode_name` | `str\|None` | 基礎模式名稱 (向下相容) |
| `base_mode_names` | `list[str]` | 所有 base mode 名稱 (依 priority 降序) |
| `base_strategies` | `list[Strategy]` | 所有 base mode 的策略 |
| `active_override_names` | `list[str]` | 活躍的 override 名稱列表 |
| `registered_modes` | `dict[str, ModeDefinition]` | 所有已註冊模式 |

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

## 相關連結

- [[Strategy]] — 模式所包裝的策略
- [[StrategyExecutor]] — 透過 `on_strategy_change` 回呼與 ModeManager 協作
- [[CascadingStrategy]] — 多 base mode 時的策略組合方案
- [[ProtectionGuard]] — 保護規則通常搭配 PROTECTION 等級的 override
