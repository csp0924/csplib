---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/core/command.py
created: 2026-02-17
---

# SystemBase

系統基準值，用於**百分比與絕對值轉換**。

> [!info] 回到 [[_MOC Controller]]

## 概述

AFC、QV 等策略計算出的結果為百分比，需透過 `SystemBase` 轉換為實際的 kW/kVar 值。`SystemBase` 使用 `@dataclass(frozen=True)` 確保不可變，並繼承 [[ConfigMixin]] 以支援 `from_dict()` 建構。

## 屬性

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `p_base` | `float` | `0.0` | 有功功率基準值 (kW) |
| `q_base` | `float` | `0.0` | 無功功率基準值 (kVar) |

## 轉換公式

```
p_kw   = p_percent * system_base.p_base / 100
q_kvar = q_percent * system_base.q_base / 100
```

## 程式碼範例

```python
from csp_lib.controller import SystemBase

base = SystemBase(p_base=1000, q_base=500)
# p_kw = p_percent * p_base / 100
# 例如：50% -> 500 kW
```

## 相關連結

- [[StrategyContext]] — 持有 `system_base` 欄位，並提供 `percent_to_kw()` / `percent_to_kvar()` 方法
- [[FPStrategy]] — 輸出百分比功率，需透過 SystemBase 轉換
- [[QVStrategy]] — 輸出無功功率比值，需透過 SystemBase 轉換
- [[ConfigMixin]] — 提供 `from_dict()` 方法
