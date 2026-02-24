---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/system/cascading.py
created: 2026-02-17
---

# CascadingStrategy

多策略級聯功率分配，使用 delta-based clamping 確保高優先層分配不被修改。

> [!info] 回到 [[_MOC Controller]]

## 概述

當多個策略需要同時運行（例如 PQ + QV），CascadingStrategy 依優先順序逐層分配功率。每一層的增量 (delta) 受系統最大視在功率 (S_max) 限制，若超過容量只縮放該層的 delta，不影響高優先層已分配的值。

## CapacityConfig

`@dataclass(frozen=True)` 的系統容量配置。

| 屬性 | 型別 | 說明 |
|------|------|------|
| `s_max_kva` | `float` | 最大視在功率 (kVA) |

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `layers` | `list[`[[Strategy]]`]` | 策略列表 (依優先順序) |
| `capacity` | `CapacityConfig` | 系統容量配置 |
| `execution_config` | [[ExecutionMode\|ExecutionConfig]] (Optional) | 執行配置，預設 PERIODIC 1s |

## 執行流程

```
Layer 0 (最高優先):
  context = 原始 context
  output -> accumulated = Command(P, Q)

Layer 1:
  context.last_command = accumulated
  context.extra["remaining_s_kva"] = S_max - |accumulated|
  output -> delta_p, delta_q
  if |accumulated + delta| > S_max:
    scale delta (二次方程求解 t)
  accumulated += scaled delta

Layer N:
  ...同上
```

## Delta-based Clamping 範例

```
容量: S_max = 1000 kVA
Layer 1 (PQ): P = 600kW, Q = 0kVar
Layer 2 (QV): wants Q = 900kVar (delta_q = 900)

S = sqrt(600^2 + 900^2) = 1082 > 1000
-> 只縮放 QV 的 delta Q，保留 PQ 的 P=600
-> 最終: P=600kW, Q ≈ 800kVar, S ≈ 1000kVA
```

## 生命週期

| 方法 | 行為 |
|------|------|
| `on_activate()` | 委派給所有子策略 |
| `on_deactivate()` | 委派給所有子策略 |

## 程式碼範例

```python
from csp_lib.controller import CascadingStrategy, CapacityConfig

cascading = CascadingStrategy(
    layers=[pq_strategy, qv_strategy],
    capacity=CapacityConfig(s_max_kva=1000),
)
# Layer 1 (PQ): P=600kW
# Layer 2 (QV): wants Q=900kVar
# S = sqrt(600^2 + 900^2) = 1082 > 1000
# -> Only scales QV's delta Q, preserves PQ's P
```

## 相關連結

- [[Strategy]] — 每一層都是 Strategy 實例
- [[ModeManager]] — 多 base mode 時由 SystemController 組合為 CascadingStrategy
- [[StrategyContext]] — 每層收到修改後的 context（含 `remaining_s_kva`）
- [[Command]] — 逐層累積的命令
