---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/context_builder.py
updated: 2026-04-16
version: ">=0.7.2"
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
| `capability_mappings` | `list[CapabilityContextMapping] \| None` | Capability-driven context 映射列表（可選） |
| `runtime_params` | `RuntimeParameters \| None` | 系統參數（可選），直接掛到 `context.params` |

## API

| 方法 | 說明 |
|------|------|
| `build() → StrategyContext` | 遍歷所有映射（明確 + capability），解析設備值並填入 StrategyContext |

## 內部流程

1. 建立空的 `StrategyContext`（含 `system_base`）
2. 遍歷每個 [[ContextMapping]]：
   - **device_id 模式**：直接讀取單一設備的 `latest_values`
   - **trait 模式**：收集所有 responsive 設備的值，透過 [[AggregateFunc]] 聚合
3. 遍歷每個 [[CapabilityContextMapping]]：
   - **device_id 模式**：`resolve_point()` → `latest_values`
   - **trait 模式**：過濾 responsive + `has_capability` → 聚合
   - **auto 模式**：`get_responsive_devices_with_capability()` → 聚合
4. 聚合結果為 `None` 時使用 `default`
5. 套用 `transform`（若有），例外時回傳 `default` 並 log warning
6. 透過 `context_field` 寫入 context 對應欄位

## Quick Example

```python
from csp_lib.integration import ContextBuilder, DeviceRegistry
from csp_lib.integration.schema import ContextMapping, CapabilityContextMapping, AggregateFunc
from csp_lib.equipment.device.capability import SOC_READABLE

builder = ContextBuilder(
    registry=registry,
    mappings=[
        ContextMapping(point_name="soc", context_field="soc", device_id="bms_01"),
    ],
    capability_mappings=[
        CapabilityContextMapping(
            capability=SOC_READABLE, slot="soc", context_field="extra.avg_soc",
            aggregate=AggregateFunc.AVERAGE,
        ),
    ],
    runtime_params=runtime_params,
)

context = builder.build()
# context.soc, context.extra["avg_soc"], context.params 皆已填入
```

> [!note] v0.7.2 NaN/Inf fail-safe（SEC-013a）
> `_set_context_field()` 寫入欄位前先以 `math.isfinite()` 檢查浮點值：非有限 float（NaN/Inf）寫入 `None` 而非保留 stale value。context 欄位型別本就是 `float | None`，下游沿用既有 None 處理路徑。此設計讓 Modbus `Float32/64.decode()` 可維持 IEEE 754 permissive（保留合法 NaN/Inf sentinel，如電表 fault 信號），由 L6 進行 fail-safe 過濾。

## 相關頁面

- [[ContextMapping]] — 明確映射定義
- [[CapabilityContextMapping]] — Capability-driven 映射定義
- [[AggregateFunc]] — 聚合函式
- [[DeviceRegistry]] — 設備查詢索引
- [[GridControlLoop]] — 使用 ContextBuilder 作為 context_provider
- [[SystemController]] — 使用 ContextBuilder 並注入 system_alarm
- [[CapabilityBinding Integration]] — 完整架構與流程圖
