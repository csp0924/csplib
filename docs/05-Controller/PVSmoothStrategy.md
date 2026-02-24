---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/pv_smooth_strategy.py
created: 2026-02-17
---

# PVSmoothStrategy

PV 功率平滑控制策略。

> [!info] 回到 [[_MOC Controller]]

## 概述

根據 PV 歷史功率的平均值計算目標輸出，並限制功率變化速率 (Ramp Rate Limiting)，避免功率劇烈波動。使用 [[PVDataService]] 取得歷史功率資料。

## PVSmoothConfig

繼承 [[ConfigMixin]]，搭配 `@dataclass` 使用。

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `capacity` | `float` | `1000.0` | PV 系統容量 (kW) |
| `ramp_rate` | `float` | `10.0` | 功率變化率限制 (百分比/週期) |
| `pv_loss` | `float` | `0.0` | PV 系統損失 (kW)，計算時扣除 |
| `min_history` | `int` | `1` | 最少需要的歷史資料筆數 |

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | `PERIODIC` |
| 週期 | 900 秒 (預設，可自訂) |

## 執行流程

1. **前置條件檢查** — PVDataService 存在性
2. **歷史資料充足性檢查** — 資料筆數 >= min_history
3. **計算歷史平均功率** — `pv_service.get_average()`
4. **扣除系統損耗** — `max(average - pv_loss, 0.0)`
5. **套用斜率限制** — `rate_limit = capacity * ramp_rate / 100`
6. **Clamp 至允許範圍** — `last_p +/- rate_limit`

## 方法

| 方法 | 說明 |
|------|------|
| `execute(context)` | 計算平滑後的 P 目標 (Q 固定為 0) |
| `update_config(config)` | 動態更新配置 |
| `set_pv_service(pv_service)` | 設定/替換 PV 資料服務 |

## 程式碼範例

```python
from csp_lib.controller import PVSmoothStrategy, PVSmoothConfig, PVDataService

pv_service = PVDataService(max_history=300)
strategy = PVSmoothStrategy(
    PVSmoothConfig(capacity=1000, ramp_rate=10, pv_loss=5),
    pv_service=pv_service,
)
# Feed data externally
pv_service.append(current_pv_power)
```

## 相關連結

- [[PVDataService]] — 提供歷史功率資料的服務
- [[Strategy]] — 基礎類別
- [[Command]] — execute 回傳值
- [[StrategyContext]] — 使用 `last_command.p_target` 作為 ramp 基準
