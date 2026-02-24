---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/stop_strategy.py
created: 2026-02-17
---

# StopStrategy

停止策略，輸出 P=0, Q=0。

> [!info] 回到 [[_MOC Controller]]

## 概述

用於停機狀態或無排程時的預設策略。每秒執行一次，始終回傳 `Command(p_target=0.0, q_target=0.0)`。

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | `PERIODIC` |
| 週期 | 1 秒 |

## 行為

- `execute(context)` -> 固定回傳 `Command(p_target=0.0, q_target=0.0)`
- 無需配置、無內部狀態
- 不覆寫 `on_activate()` / `on_deactivate()`

## 使用情境

- [[ScheduleStrategy]] 無排程時的預設 fallback
- [[ModeManager]] 的保護模式
- 系統初始化或錯誤恢復時的安全狀態

## 相關連結

- [[Strategy]] — 基礎類別
- [[Command]] — 固定輸出 P=0, Q=0
- [[ScheduleStrategy]] — 作為預設 fallback
- [[SystemAlarmProtection]] — 告警時強制 P=0, Q=0 的效果類似
