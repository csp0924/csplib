---
tags:
  - type/enum
  - layer/integration
  - status/complete
source: csp_lib/integration/schema.py
---

# AggregateFunc

多設備值聚合函式列舉，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`AggregateFunc` 定義了 trait 模式下多台設備值的合併策略。當 [[ContextMapping]] 使用 `trait` 模式時，會從所有匹配的 responsive 設備收集點位值，再透過指定的聚合函式合併為單一值。

## 成員

| 成員 | 值 | 說明 |
|------|------|------|
| `AVERAGE` | `"average"` | 平均值 |
| `SUM` | `"sum"` | 加總 |
| `MIN` | `"min"` | 最小值 |
| `MAX` | `"max"` | 最大值 |
| `FIRST` | `"first"` | 取排序後第一台設備的值 |

## 備註

- 聚合前會先過濾掉 `None` 值
- 若過濾後無有效值，聚合結果為 `None`（由上層轉為 `default`）
- 若需要自訂聚合邏輯，可使用 [[ContextMapping]] 的 `custom_aggregate` 欄位，其優先權高於 `aggregate`

## 相關頁面

- [[ContextMapping]] — 使用 AggregateFunc 進行多設備值聚合
- [[ContextBuilder]] — 實際執行聚合邏輯
