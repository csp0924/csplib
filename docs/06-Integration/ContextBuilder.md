---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/context_builder.py
---

# ContextBuilder

設備值 → StrategyContext 建構器，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`ContextBuilder` 透過 [[ContextMapping]] 列表，從 [[DeviceRegistry]] 中的設備讀取點位值，映射並聚合後填入 `StrategyContext`。

其 `build()` 方法的簽名 `Callable[[], StrategyContext]` 完全符合 `StrategyExecutor` 的 `context_provider` 介面，可直接作為參數傳入。

### 設計注意事項

- `last_command` / `current_time` 不由 ContextBuilder 設定，由 `StrategyExecutor._execute_strategy` 自行注入
- `latest_values` 回傳 copy，無競態問題

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `registry` | [[DeviceRegistry]] | 設備查詢索引 |
| `mappings` | `list[ContextMapping]` | 設備點位 → context 欄位的映射列表 |
| `system_base` | `SystemBase \| None` | 系統基準值（可選） |

## API

| 方法 | 說明 |
|------|------|
| `build() → StrategyContext` | 遍歷所有映射，解析設備值並填入 StrategyContext |

## 內部流程

1. 建立空的 `StrategyContext`（含 `system_base`）
2. 遍歷每個 [[ContextMapping]]：
   - **device_id 模式**：直接讀取單一設備的 `latest_values`
   - **trait 模式**：收集所有 responsive 設備的值，透過 [[AggregateFunc]] 聚合
3. 聚合結果為 `None` 時使用 `default`
4. 套用 `transform`（若有），例外時回傳 `default` 並 log warning
5. 透過 `context_field` 寫入 context 對應欄位

## 相關頁面

- [[ContextMapping]] — 映射定義
- [[AggregateFunc]] — 聚合函式
- [[DeviceRegistry]] — 設備查詢索引
- [[GridControlLoop]] — 使用 ContextBuilder 作為 context_provider
- [[SystemController]] — 使用 ContextBuilder 並注入 system_alarm
