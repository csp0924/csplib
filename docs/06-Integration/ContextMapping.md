---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/schema.py
created: 2026-02-17
updated: 2026-04-17
version: ">=0.8.0"
---

# ContextMapping

設備值 / RuntimeParameters → StrategyContext 的映射定義，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`ContextMapping` 是一個 frozen dataclass，用於宣告如何將設備的讀取值或 `RuntimeParameters` 中的參數映射到策略上下文（`StrategyContext`）中的特定欄位。v0.8.0 起支援三種模式（三擇一）：

- **device_id 模式**：讀取單一指定設備的值
- **trait 模式**：收集所有同 trait 設備的值並聚合
- **param_key 模式**（v0.8.0+）：從 `RuntimeParameters` 直接讀值，不需手動搬進 extra dict

## 欄位

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `point_name` | `str` | 必填 | 設備點位名稱（param_key 模式下不使用，但為相容 Builder 介面仍需設值） |
| `context_field` | `str` | 必填 | 目標 context 欄位（`"soc"` 或 `"extra.xxx"`） |
| `device_id` | `str \| None` | `None` | 指定單一設備 ID（與 `trait` / `param_key` 三擇一） |
| `trait` | `str \| None` | `None` | 指定 trait 標籤（與 `device_id` / `param_key` 三擇一） |
| `param_key` | `str \| None` | `None` | v0.8.0+：RuntimeParameters key，直接注入 context 欄位（與 `device_id` / `trait` 三擇一） |
| `aggregate` | [[AggregateFunc]] | `AVERAGE` | 多設備聚合函式（僅 trait 模式有效） |
| `custom_aggregate` | `Callable` | `None` | 自訂聚合函式，優先於 `aggregate` |
| `default` | `Any` | `None` | 無法取得有效值時的預設值 |
| `transform` | `Callable` | `None` | 值轉換函式，套用於聚合結果之後（param_key 模式同樣生效） |

> [!warning] 三擇一驗證
> `device_id`、`trait`、`param_key` 必須恰好設定其一，`__post_init__` 以 `_validate_context_source()` 驗證，違反時拋 `ValueError`。

## Quick Example

```python
from csp_lib.integration import ContextMapping, AggregateFunc

# device_id 模式：讀取單一設備的 soc 點位
ContextMapping(
    point_name="soc",
    context_field="soc",
    device_id="bms_001",
)

# trait 模式：聚合所有 meter 的 power
ContextMapping(
    point_name="power",
    context_field="extra.meter_power",
    trait="meter",
    aggregate=AggregateFunc.SUM,
    default=0.0,
)

# param_key 模式（v0.8.0+）：從 RuntimeParameters 讀 grid_limit
ContextMapping(
    point_name="",              # param_key 模式下不使用，但需要設值
    context_field="extra.grid_limit_kw",
    param_key="grid_limit_kw",  # RuntimeParameters.get("grid_limit_kw")
    default=0.0,
)
```

## param_key 模式（v0.8.0）

`param_key` 模式讓 `ContextBuilder` 直接從 `RuntimeParameters.get(param_key)` 讀值並注入 context，省去手動搬入 `extra` 的樣板代碼。

**使用前提**：`ContextBuilder` 必須以 `runtime_params=...` 建構；若未提供則 log warning 並回退至 `default`。

```python
# SystemControllerConfig.builder() 方式
config = (
    SystemControllerConfig.builder()
    .map_context("", target="extra.grid_limit_kw", param_key="grid_limit_kw", default=0.0)
    .build()
)

# 執行期 runtime_params 更新 → 下次 build() 自動反映新值
params.set("grid_limit_kw", 500.0)
```

**與 `transform` / `default` 的搭配**：param_key 模式下 `transform` 和 `default` 同樣生效，可對參數值做比例縮放或設定回退值。

## context_field 路徑規則

- 一般欄位（如 `"soc"`）：直接對應 `ctx.soc = value`
- `extra.` 前綴（如 `"extra.meter_power"`）：對應 `ctx.extra["meter_power"] = value`

## 相關頁面

- [[AggregateFunc]] — 聚合函式定義
- [[ContextBuilder]] — 使用 ContextMapping 建構 StrategyContext（含 param_key 路徑）
- [[CommandMapping]] — Command 欄位映射
- [[DataFeedMapping]] — PV 資料餵入映射
- [[SystemController]] — Builder 的 `map_context(param_key=...)` 介面
