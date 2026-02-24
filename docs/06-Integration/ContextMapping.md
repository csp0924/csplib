---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/schema.py
---

# ContextMapping

設備值 → StrategyContext 的映射定義，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`ContextMapping` 是一個 frozen dataclass，用於宣告如何將設備的讀取值映射到策略上下文（`StrategyContext`）中的特定欄位。支援兩種模式：

- **device_id 模式**：讀取單一指定設備的值
- **trait 模式**：收集所有同 trait 設備的值並聚合

兩者必須恰好設定其一（互斥）。

## 欄位

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `point_name` | `str` | 必填 | 設備點位名稱（對應 `device.latest_values` 的 key） |
| `context_field` | `str` | 必填 | 目標 context 欄位（`"soc"` 或 `"extra.xxx"`） |
| `device_id` | `str \| None` | `None` | 指定單一設備 ID（與 `trait` 擇一） |
| `trait` | `str \| None` | `None` | 指定 trait 標籤（與 `device_id` 擇一） |
| `aggregate` | [[AggregateFunc]] | `AVERAGE` | 多設備聚合函式（僅 trait 模式有效） |
| `custom_aggregate` | `Callable` | `None` | 自訂聚合函式，優先於 `aggregate` |
| `default` | `Any` | `None` | 無法取得有效值時的預設值 |
| `transform` | `Callable` | `None` | 值轉換函式，套用於聚合結果之後 |

## 使用範例

```python
from csp_lib.integration import ContextMapping, AggregateFunc

# Single device mode
ContextMapping(
    point_name="soc",
    context_field="soc",  # Maps to context.soc
    device_id="bms_001",
)

# Trait mode with aggregation
ContextMapping(
    point_name="power",
    context_field="extra.meter_power",  # Maps to context.extra["meter_power"]
    trait="meter",
    aggregate=AggregateFunc.SUM,
    default=0.0,
)
```

## context_field 路徑規則

- 一般欄位（如 `"soc"`）：直接對應 `ctx.soc = value`
- `extra.` 前綴（如 `"extra.meter_power"`）：對應 `ctx.extra["meter_power"] = value`

## 相關頁面

- [[AggregateFunc]] — 聚合函式定義
- [[ContextBuilder]] — 使用 ContextMapping 建構 StrategyContext
- [[CommandMapping]] — Command 欄位映射
- [[DataFeedMapping]] — PV 資料餵入映射
