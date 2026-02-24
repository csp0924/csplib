---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/core/context.py
created: 2026-02-17
---

# StrategyContext

策略執行時上下文，由 [[StrategyExecutor]] 注入，提供策略所需的外部狀態。

> [!info] 回到 [[_MOC Controller]]

## 概述

`StrategyContext` 為唯讀設計，策略不應直接修改此物件。Executor 在每次執行策略前會透過 `dataclasses.replace()` 建立不可變副本，自動注入 `last_command` 與 `current_time`。

## 屬性

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `last_command` | [[Command]] | `Command()` | 上一次執行的命令 |
| `soc` | `Optional[float]` | `None` | 儲能系統 SOC (%) |
| `system_base` | `Optional[`[[SystemBase]]`]` | `None` | 系統基準值 |
| `current_time` | `Optional[datetime]` | `None` | 當前時間 (由 Executor 自動注入) |
| `extra` | `dict[str, Any]` | `{}` | 額外資料 (供擴充使用) |

### extra 常見鍵值

| 鍵 | 用途 | 使用者 |
|----|------|--------|
| `"voltage"` | 系統電壓 (V) | [[QVStrategy]] |
| `"frequency"` | 系統頻率 (Hz) | [[FPStrategy]] |
| `"meter_power"` | 電表功率 (kW) | [[ReversePowerProtection]] |
| `"system_alarm"` | 系統告警旗標 | [[SystemAlarmProtection]] |
| `"remaining_s_kva"` | 剩餘視在功率容量 | [[CascadingStrategy]] |

## 輔助方法

| 方法 | 回傳 | 說明 |
|------|------|------|
| `percent_to_kw(p_percent)` | `float` | 將百分比轉換為 kW |
| `percent_to_kvar(q_percent)` | `float` | 將百分比轉換為 kVar |

> [!warning] 呼叫 `percent_to_kw` / `percent_to_kvar` 前需確保 `system_base` 已設定，否則拋出 `ValueError`。

## 程式碼範例

```python
from csp_lib.controller import StrategyContext, Command, SystemBase

context = StrategyContext(
    last_command=Command(),
    soc=75.0,
    system_base=SystemBase(p_base=1000, q_base=500),
    current_time=None,  # Auto-injected by executor
    extra={"voltage": 380.0, "frequency": 60.0},
)

# Percent to kW/kVar conversion
p_kw = context.percent_to_kw(50)    # -> 500.0
q_kvar = context.percent_to_kvar(20) # -> 100.0
```

## 相關連結

- [[Command]] — `last_command` 的型別
- [[SystemBase]] — `system_base` 的型別
- [[Strategy]] — `execute(context)` 接收 StrategyContext
- [[StrategyExecutor]] — 負責建構與注入 StrategyContext
