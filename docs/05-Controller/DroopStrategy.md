---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/droop_strategy.py
updated: 2026-04-06
version: ">=0.7.1"
---

# DroopStrategy

標準下垂控制一次頻率響應策略 (Primary Frequency Response)。

> [!info] v0.5.0 新增

> [!info] 回到 [[_MOC Controller]]

## 概述

根據系統頻率偏差，透過下垂公式計算功率輸出並疊加排程功率。適用於併網型儲能系統的一次頻率調節 (AFC/Droop) 應用。

- 頻率低於基準 -> 正功率（放電）
- 頻率高於基準 -> 負功率（充電）
- 頻率偏差在死區內 -> 不響應

## DroopConfig

`@dataclass` 配置，繼承 [[ConfigMixin]]。

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `f_base` | `float` | `60.0` | 基準頻率 (Hz) |
| `droop` | `float` | `0.05` | 下垂係數，5% = 0.05 |
| `deadband` | `float` | `0.0` | 死區寬度 (Hz)，頻率偏差在此範圍內不響應 |
| `rated_power` | `float` | `0.0` | 額定功率 (kW)，0 表示使用 `system_base.p_base` |
| `max_droop_power` | `float` | `0.0` | 最大調頻功率 (kW)，0 表示不限制 |
| `interval` | `float` | `0.3` | 執行週期（秒） |

`validate()` 方法會檢查 `droop > 0`、`f_base > 0`、`deadband >= 0` 等約束。

## 計算公式

```
gain = 100 / (f_base × droop)
pct  = -gain × (frequency - f_base)     # 死區外
pct  = 0                                 # 死區內

droop_power = rated_power × pct / 100
total       = schedule_p + droop_power
total       = clamp(total, -rated_power, rated_power)
```

## 額定功率解析

優先順序：`config.rated_power` > `system_base.p_base` > `0.0`（回傳 schedule_p）。

## context.extra 需求

| 鍵 | 型別 | 必要 | 說明 |
|----|------|------|------|
| `frequency` | `float` | 是 | 當前電網頻率 (Hz) |
| `schedule_p` | `float` | 否（預設 0） | 排程功率設定點 (kW) |

> [!note] 若 `frequency` 為 None，策略會維持上一次的 [[Command]]，不做任何調整。

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | `PERIODIC` |
| 週期 | `max(1, int(config.interval))` 秒 |

## Quick Example

```python
from csp_lib.controller.strategies import DroopStrategy, DroopConfig

config = DroopConfig(
    f_base=60.0,
    droop=0.05,        # 5% 下垂係數
    deadband=0.02,     # 20 mHz 死區
    rated_power=500.0, # 500 kW 額定功率
)
strategy = DroopStrategy(config)

# 註冊至 ModeManager
controller.register_mode("droop", strategy, ModePriority.NORMAL)
```

## 相關連結

- [[Strategy]] — 基礎類別
- [[Command]] — 輸出的功率命令
- [[StrategyContext]] — 策略上下文
- [[SystemBase]] — 提供 `p_base` 作為 fallback 額定功率
- [[ModeManager]] — 模式管理器
