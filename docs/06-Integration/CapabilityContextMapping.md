---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/schema.py
created: 2026-03-06
updated: 2026-04-04
version: ">=0.4.2"
---

# CapabilityContextMapping

Capability-driven 設備值 → StrategyContext 映射定義，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`CapabilityContextMapping` 是一個 frozen dataclass，用於以 **capability + slot** 取代明確的 `point_name`，讓不同設備自動透過 `CapabilityBinding` 解析各自的實際點位名稱。

與 [[ContextMapping]] 的核心差異：
- 使用 `capability` + `slot` 取代 `point_name`
- 支援 **auto 模式**（`device_id` 和 `trait` 皆為 `None`），自動發現所有具備該能力的設備

### 三種 Scoping 模式

| 模式 | device_id | trait | 行為 |
|------|-----------|-------|------|
| **device_id** | 設定 | `None` | 讀取單一指定設備 |
| **trait** | `None` | 設定 | 讀取同 trait 且具備該 capability 的所有設備並聚合 |
| **auto** | `None` | `None` | 自動發現所有具備該 capability 的 responsive 設備並聚合 |

## 欄位

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `capability` | `Capability` | 必填 | 目標能力定義 |
| `slot` | `str` | 必填 | capability 的 read slot 名稱（必須存在於 `capability.read_slots`） |
| `context_field` | `str` | 必填 | 目標 context 欄位（`"soc"` 或 `"extra.xxx"`） |
| `device_id` | `str \| None` | `None` | 指定單一設備 ID（與 `trait` 擇一，或皆不設） |
| `trait` | `str \| None` | `None` | 指定 trait 標籤（與 `device_id` 擇一，或皆不設） |
| `aggregate` | [[AggregateFunc]] | `AVERAGE` | 多設備聚合函式（trait / auto 模式有效） |
| `custom_aggregate` | `Callable` | `None` | 自訂聚合函式，優先於 `aggregate` |
| `default` | `Any` | `None` | 無法取得有效值時的預設值 |
| `transform` | `Callable` | `None` | 值轉換函式，套用於聚合結果之後 |

## 驗證規則

- `device_id` 與 `trait` 不可同時設定（`ValueError`）
- `slot` 必須存在於 `capability.read_slots`（`ValueError`）

## 使用範例

```python
from csp_lib.equipment.device.capability import SOC_READABLE, MEASURABLE
from csp_lib.integration import CapabilityContextMapping, AggregateFunc

# Auto 模式：自動發現所有有 SOC 能力的設備
CapabilityContextMapping(
    capability=SOC_READABLE,
    slot="soc",
    context_field="soc",
)

# Trait 模式：聚合特定 trait 設備的有功功率
CapabilityContextMapping(
    capability=MEASURABLE,
    slot="active_power",
    context_field="extra.grid_power",
    trait="meter",
    aggregate=AggregateFunc.SUM,
)

# Device_id 模式：讀取指定設備
CapabilityContextMapping(
    capability=SOC_READABLE,
    slot="soc",
    context_field="soc",
    device_id="bess_01",
)
```

## 點位解析流程

```
CapabilityContextMapping(capability=SOC_READABLE, slot="soc")
    |
    v
device.resolve_point(SOC_READABLE, "soc")
    |
    v
CapabilityBinding.resolve("soc") -> "battery_soc_pct"  (因設備而異)
    |
    v
device.latest_values.get("battery_soc_pct") -> 85.3
```

## 相關頁面

- [[ContextMapping]] -- 明確 point_name 版本的 context 映射
- [[CapabilityCommandMapping]] -- Capability-driven command 映射
- [[AggregateFunc]] -- 聚合函式定義
- [[ContextBuilder]] -- 使用 CapabilityContextMapping 建構 StrategyContext
- [[SystemController]] -- 透過 `capability_context_mappings` 配置
- [[CapabilityBinding Integration]] -- 完整架構與流程圖
