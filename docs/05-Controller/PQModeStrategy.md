---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/pq_strategy.py
created: 2026-02-17
---

# PQModeStrategy

固定 P/Q 輸出的控制策略。

> [!info] 回到 [[_MOC Controller]]

## 概述

PQ 模式策略根據配置輸出固定的有功功率 (P) 與無功功率 (Q) 值。每秒執行一次 (PERIODIC)。是最基本的控制策略，常用於手動設定或排程輸出。

## PQModeConfig

繼承 [[ConfigMixin]]，搭配 `@dataclass` 使用。

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `p` | `float` | `0.0` | 有功功率目標值 (kW) |
| `q` | `float` | `0.0` | 無功功率目標值 (kVar) |

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | `PERIODIC` |
| 週期 | 1 秒 |

## 方法

| 方法 | 說明 |
|------|------|
| `execute(context)` | 回傳 `Command(p_target=config.p, q_target=config.q)` |
| `update_config(config)` | 動態更新 PQ 配置 |

## 程式碼範例

```python
from csp_lib.controller import PQModeStrategy, PQModeConfig

strategy = PQModeStrategy(PQModeConfig(p=100, q=50))
strategy.update_config(PQModeConfig(p=200, q=0))
```

## 相關連結

- [[Strategy]] — 基礎類別
- [[Command]] — execute 回傳值
- [[ConfigMixin]] — PQModeConfig 繼承的 Mixin
- [[ScheduleStrategy]] — 可在排程中使用 PQModeStrategy
- [[CascadingStrategy]] — 可作為級聯策略的某一層
