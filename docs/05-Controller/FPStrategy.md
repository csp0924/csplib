---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/fp_strategy.py
created: 2026-02-17
---

# FPStrategy

頻率-功率控制策略 (AFC, Automatic Frequency Control)。

> [!info] 回到 [[_MOC Controller]]

## 概述

根據系統頻率偏差，透過分段線性插值計算功率輸出。適用於自動頻率控制 (AFC) 應用。從 `context.extra["frequency"]` 讀取即時頻率值，輸出功率百分比，透過 [[SystemBase]] 轉換為 kW。

## FPConfig

繼承 [[ConfigMixin]]，搭配 `@dataclass` 使用。使用基準頻率 + 偏移量定義 6 點頻率-功率曲線。

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `f_base` | `float` | `60.0` | 基準頻率 (Hz) |
| `f1` | `float` | `-0.5` | 最低頻率偏移 |
| `f2` | `float` | `-0.25` | 偏移 2 |
| `f3` | `float` | `-0.02` | 死區下限 |
| `f4` | `float` | `0.02` | 死區上限 |
| `f5` | `float` | `0.25` | 偏移 5 |
| `f6` | `float` | `0.5` | 最高頻率偏移 |
| `p1` | `float` | `100.0` | f1 時功率 (%) — 最大放電 |
| `p2` | `float` | `52.0` | f2 時功率 (%) |
| `p3` | `float` | `9.0` | 死區下限功率 (%) |
| `p4` | `float` | `-9.0` | 死區上限功率 (%) |
| `p5` | `float` | `-52.0` | f5 時功率 (%) |
| `p6` | `float` | `-100.0` | f6 時功率 (%) — 最大充電 |

### validate() 驗證規則

- 頻率偏移量必須按升序排列：f1 < f2 < f3 < f4 < f5 < f6
- 功率百分比必須按降序排列：p1 >= p2 >= p3 >= p4 >= p5 >= p6

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | `PERIODIC` |
| 週期 | 1 秒 |

## 頻率-功率曲線

```
P(%)
 100 |--*
     |    \
  52 |     *
     |      \
   9 |       *---*  (死區)
  -9 |           *---*
     |                \
 -52 |                 *
     |                  \
-100 |                   *--
     +--+--+--+--+--+--+--→ f(Hz)
       f1  f2 f3 f4 f5  f6
```

## 程式碼範例

```python
from csp_lib.controller import FPStrategy, FPConfig

strategy = FPStrategy(FPConfig(
    f_base=60.0,
    f1=-0.5, f2=-0.25, f3=-0.02, f4=0.02, f5=0.25, f6=0.5,
    p1=100, p2=52, p3=9, p4=-9, p5=-52, p6=-100,
))
# Reads frequency from context.extra["frequency"]
# Outputs power percentage, converted to kW via system_base
```

## 資料來源

| 鍵 | 來源 | 說明 |
|----|------|------|
| `context.extra["frequency"]` | 外部注入 | 系統即時頻率 (Hz) |

> [!note] 無頻率資料時維持 `last_command`。

## 相關連結

- [[Strategy]] — 基礎類別
- [[StrategyContext]] — 從 `extra["frequency"]` 讀取頻率
- [[SystemBase]] — 將百分比轉換為 kW
- [[Command]] — execute 回傳值
