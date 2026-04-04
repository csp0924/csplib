---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/schedule_strategy.py
created: 2026-02-17
updated: 2026-04-04
version: ">=0.4.2"
---

# ScheduleStrategy

排程策略，根據外部排程動態切換內部策略。

> [!info] 回到 [[_MOC Controller]]

## 概述

ScheduleStrategy 作為策略容器，可在運行期間動態切換所包裝的策略。當無排程時使用 [[StopStrategy]] 作為預設 fallback。切換策略時自動呼叫舊策略的 `on_deactivate()` 和新策略的 `on_activate()`。

> [!note] v0.4.2 架構調整
> v0.4.2 之後，`ScheduleService` 不再持有 `ScheduleStrategy` 實例。排程驅動的策略切換改由 [[ScheduleModeController]] Protocol → `SystemController.activate_schedule_mode()` → `ModeManager.update_mode_strategy()` 正規路徑完成。`ScheduleStrategy` 類別保留，向後相容。若仍需手動使用排程容器策略（例如不搭配 `ScheduleService` 的場景），此類別仍然適用。

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | 委派給當前子策略的 `execution_config` |

## 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `current_strategy` | [[Strategy]] | 當前執行的策略 (無排程時為 fallback) |
| `has_schedule` | `bool` | 是否有排程 |

## 方法

| 方法 | 說明 |
|------|------|
| `update_schedule(strategy)` | 更新排程策略，None 表示使用 fallback |
| `execute(context)` | 委派給當前策略的 execute() |
| `on_activate()` | 啟用當前策略 |
| `on_deactivate()` | 停用當前策略 |

## 程式碼範例

```python
from csp_lib.controller import ScheduleStrategy, PQModeStrategy, PQModeConfig

schedule = ScheduleStrategy()

# 由外部排程更新器呼叫
await schedule.update_schedule(PQModeStrategy(PQModeConfig(p=100)))  # 切換到 PQ 模式
await schedule.update_schedule(None)  # 無排程 -> StopStrategy
```

## 擴充性設計

- 可在 `execute()` 中呼叫多個策略的 `execute()` 並自行組合 Command
- 例如：P 來自 [[PVSmoothStrategy]]，Q 來自另一個策略

## 相關連結

- [[Strategy]] — 基礎類別
- [[StopStrategy]] — 預設 fallback 策略
- [[ModeManager]] — 通常作為 SCHEDULE 優先權的 base mode
- [[StrategyExecutor]] — 負責執行 ScheduleStrategy
- [[ScheduleModeController]] — v0.4.2 新增：ScheduleService 使用的排程模式控制協定（不再依賴本類別）
