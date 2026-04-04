---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/ramp_stop.py
updated: 2026-04-04
version: ">=0.5.0"
---

# RampStopStrategy

斜坡降功率策略，從當前功率開始按斜率降至 0。

> [!info] v0.5.0 新增

> [!warning] Deprecated — `RampStopProtection`
> `RampStopProtection`（位於 `csp_lib/controller/system/dynamic_protection.py`）已棄用。
> RampStop 本質上是「接管控制」而非「修改數值」，更適合作為 [[Strategy]] 搭配 [[EventDrivenOverride]] + [[ModeManager]] 使用。

> [!info] 回到 [[_MOC Controller]]

## 概述

透過 [[ModeManager]] 的 `push_override()` 啟動，從當前功率開始按斜率降至 0。到達 0 後維持 P=0 直到被 `pop_override()` 移除。

使用實際 dt（monotonic clock）計算每步降幅，不依賴固定 interval：

```
ramp_step = ramp_rate_pct / 100 × rated_power × dt
```

### 與 StopStrategy 的區別

| | [[StopStrategy]] | RampStopStrategy |
|---|---|---|
| 行為 | 立即 P=0 | 斜坡降至 0 |
| 適用情境 | 設備告警、需立即停止 | 通訊中斷等可容忍漸進停止 |

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `rated_power` | `float` | — | 系統額定功率 (kW) |
| `ramp_rate_pct` | `float` | `5.0` | 斜率 (%/s)，每秒降 5% 額定功率 |

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | `PERIODIC` |
| 週期 | 1 秒 |

## 行為

1. `on_activate()` — 重置狀態
2. 第一次 `execute()` — 繼承 `context.last_command.p_target` 作為起始功率
3. 每次執行按 `ramp_step` 逐步降低
4. 到達 P=0 後維持
5. `on_deactivate()` — 重置狀態

## Quick Example

```python
from csp_lib.controller.strategies import RampStopStrategy

ramp_stop = RampStopStrategy(rated_power=2000.0, ramp_rate_pct=5.0)

# 搭配 EventDrivenOverride + ModeManager
controller.register_mode("ramp_stop", ramp_stop, ModePriority.PROTECTION)
controller.register_event_override(
    ContextKeyOverride(name="ramp_stop", key="comm_timeout")
)
```

## 相關連結

- [[Strategy]] — 基礎類別
- [[StopStrategy]] — 立即停止策略
- [[ModeManager]] — 模式管理器，透過 override 啟動
- [[EventDrivenOverride]] — 事件驅動自動啟動
- [[Command]] — 輸出的功率命令
