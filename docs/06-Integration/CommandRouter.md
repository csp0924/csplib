---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/command_router.py
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

## API

| 方法 | 說明 |
|------|------|
| `route(command) → None` | 遍歷所有映射，取得 Command 對應欄位值後寫入設備 |

## 相關頁面

- [[CommandMapping]] — 映射定義
- [[DeviceRegistry]] — 設備查詢索引
- [[GridControlLoop]] — 使用 CommandRouter 作為 on_command 回呼
- [[SystemController]] — 在 ProtectionGuard 之後使用 CommandRouter
