---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/command_router.py
updated: 2026-04-04
version: ">=0.4.2"
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

## Per-Device 分配模式

當 `SystemControllerConfig` 設定了 `power_distributor` 時，控制迴圈會改用 `route_per_device()` 代替 `route()`。

`route_per_device(command, per_device_commands)` 採用混合寫入策略：
- **明確映射（`CommandMapping`）**：使用系統級 `command`，行為與 `route()` 完全相同
- **Capability 映射（`CapabilityCommandMapping`）**：使用 `per_device_commands[device_id]` 中的 per-device `Command`，實現精確的設備級分配

這種設計讓使用者可以同時擁有：明確點位的廣播寫入，以及 capability 點位的精確分配寫入。

> [!note] Per-device 分配
> `per_device_commands` dict 中未包含的設備不會被 capability 映射寫入，但不影響明確映射路徑。詳見 [[PowerDistributor]]。

## 相關頁面

- [[CommandMapping]] — 明確映射定義
- [[CapabilityCommandMapping]] — Capability-driven 映射定義
- [[DeviceRegistry]] — 設備查詢索引
- [[PowerDistributor]] — 提供 per-device Command 給 `route_per_device()`
- [[GridControlLoop]] — 使用 CommandRouter 作為 on_command 回呼
- [[SystemController]] — 在 ProtectionGuard 之後使用 CommandRouter
- [[CapabilityBinding Integration]] — 完整架構與流程圖
