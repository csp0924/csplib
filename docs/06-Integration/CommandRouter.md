---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/command_router.py
created: 2026-02-17
updated: 2026-04-17
version: ">=0.8.1"
---

# CommandRouter

Command → 設備寫入路由器，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`CommandRouter` 將策略執行結果（`Command`）的各欄位，透過 [[CommandMapping]] 路由到設備寫入操作。

其 `route()` 方法的簽名 `async (Command) -> None` 完全符合 `StrategyExecutor` 的 `on_command` 介面，可直接作為回呼傳入。

### 路由模式

- **Unicast（device_id 模式）**：寫入單一指定設備
- **Broadcast（trait 模式）**：廣播寫入所有 responsive 且非 protected 設備

### 錯誤處理策略

| 情境 | 處理方式 |
|------|---------|
| command 欄位值為 `NO_CHANGE` | TRACE log + 跳過該軸的所有設備寫入（v0.8.0） |
| `transform` 例外 | log error + 跳過該映射 |
| 單一設備寫入失敗 | log warning + 繼續寫入其他設備 |
| 設備不存在或離線 | log warning + 跳過 |
| 設備處於 protected 狀態 | log warning + 跳過 |

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `registry` | [[DeviceRegistry]] | 設備查詢索引 |
| `mappings` | `list[CommandMapping]` | Command 欄位 → 設備寫入的映射列表 |
| `capability_mappings` | `list[CapabilityCommandMapping] \| None` | Capability-driven command 映射列表（可選） |

## 路由模式

### 明確映射路徑（CommandMapping）

- **Unicast（device_id 模式）**：寫入單一指定設備
- **Broadcast（trait 模式）**：廣播寫入所有 responsive 且非 protected 設備

### Capability 映射路徑（CapabilityCommandMapping）

- **device_id 模式**：`has_capability` + `resolve_point` → 寫入單一設備
- **trait 模式**：trait 過濾 + `has_capability` → 廣播寫入
- **auto 模式**：`get_responsive_devices_with_capability` → 廣播寫入

## API

| 方法 | 說明 |
|------|------|
| `route(command) → None` | 遍歷所有映射（明確 + capability），取得 Command 對應欄位值後寫入設備 |
| `route_per_device(command, per_device_commands) → None` | 明確映射用系統級 command，capability 映射用 per-device command |
| `try_write_single(device_id, point_name, value) → bool` | v0.8.1+：公開單設備寫入；成功更新 `_last_written` desired state；失敗回傳 `False` |
| `get_last_written(device_id) → dict[str, Any]` | v0.8.1+：回傳指定設備的 desired state snapshot（`point_name → value`） |
| `get_tracked_device_ids() → frozenset[str]` | v0.8.1+：回傳所有已追蹤的 device_id 集合 |

### Desired State 追蹤（v0.8.1 新增）

`CommandRouter` 從 v0.8.1 起維護 `_last_written: dict[str, dict[str, Any]]`，每次成功寫入後更新。此 desired state 表供 [[Command Refresh|CommandRefreshService]] 週期性讀取並重傳，實現 reconciler 模型。

- `NO_CHANGE` 軸跳過寫入，**不**觸及 `_last_written`，保留業務值語義
- `is_protected` / `is_responsive` 等保護條件不通過時，`_last_written` 也不更新
- `try_write_single` 與舊版 `_write_single` 邏輯等效（`_write_single` 現在是 alias）

## Per-Device 分配模式

當 `SystemControllerConfig` 設定了 `power_distributor` 時，控制迴圈會改用 `route_per_device()` 代替 `route()`。

`route_per_device(command, per_device_commands)` 採用混合寫入策略：
- **明確映射（`CommandMapping`）**：使用系統級 `command`，行為與 `route()` 完全相同
- **Capability 映射（`CapabilityCommandMapping`）**：使用 `per_device_commands[device_id]` 中的 per-device `Command`，實現精確的設備級分配

這種設計讓使用者可以同時擁有：明確點位的廣播寫入，以及 capability 點位的精確分配寫入。

> [!note] Per-device 分配
> `per_device_commands` dict 中未包含的設備不會被 capability 映射寫入，但不影響明確映射路徑。詳見 [[PowerDistributor]]。

## Quick Example

```python
from csp_lib.integration import CommandRouter, DeviceRegistry
from csp_lib.integration.schema import CommandMapping, CapabilityCommandMapping
from csp_lib.equipment.device.capability import ACTIVE_POWER_CONTROL

router = CommandRouter(
    registry=registry,
    mappings=[
        CommandMapping(command_field="p_target", point_name="set_p", trait="pcs"),
    ],
    capability_mappings=[
        CapabilityCommandMapping(
            command_field="p_target",
            capability=ACTIVE_POWER_CONTROL,
            slot="p_setpoint",
        ),
    ],
)

await router.route(command)  # 同值廣播
# 或搭配 PowerDistributor
await router.route_per_device(command, per_device_commands)
```

> [!note] v0.8.0 NO_CHANGE 支援
> `route()` 與 `route_per_device()` 在讀取 Command 欄位後，若值為 `NO_CHANGE` sentinel，立即跳過該映射下的所有設備寫入並記錄 TRACE log。這讓 QV 策略（`p=NO_CHANGE`）或 FP 策略（`q=NO_CHANGE`）可正確與其他策略組合，不會將「跳過」誤傳為寫入 0。

## 相關頁面

- [[CommandMapping]] — 明確映射定義
- [[CapabilityCommandMapping]] — Capability-driven 映射定義
- [[DeviceRegistry]] — 設備查詢索引
- [[PowerDistributor]] — 提供 per-device Command 給 `route_per_device()`
- [[GridControlLoop]] — 使用 CommandRouter 作為 on_command 回呼
- [[SystemController]] — 在 ProtectionGuard 之後使用 CommandRouter
- [[Command]] — v0.8.0 起 p_target / q_target 支援 NO_CHANGE
- [[CapabilityBinding Integration]] — 完整架構與流程圖
- [[Command Refresh]] — CommandRefreshService：讀取 desired state 並週期重傳（v0.8.1）
