---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/core/context.py
created: 2026-02-17
updated: 2026-04-06
version: ">=0.7.1"
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
| `extra` | `dict[str, Any]` | `{}` | 額外資料 — 設備讀值（由 ContextMapping 注入） |
| `params` | `RuntimeParameters \| None` | `None` | 系統參數 — RuntimeParameters 引用（由 SystemController 注入） |

> [!info] v0.5.0 新增
> `params` 屬性在 v0.5.0 加入，提供對 `RuntimeParameters` 的引用。

### params 與 extra 的區別

| 面向 | `extra` | `params` |
|------|---------|----------|
| **用途** | 設備讀值、感測器資料（frequency, voltage, meter_power 等） | 系統參數、EMS 指令（soc_max, grid_limit_pct, ramp_rate 等） |
| **注入方式** | 由 `ContextMapping` 從設備 `latest_values` 映射 | 由 `SystemController` 從 `RuntimeParameters` 直接引用 |
| **資料來源** | Modbus 設備輪詢 | EMS/Modbus 寫入、Redis channel、外部 API |
| **更新頻率** | 每個控制週期重新映射 | 外部觸發時更新（thread-safe） |
| **存取方式** | `context.extra["key"]` | `context.params.get("key")` |
| **典型使用者** | [[FPStrategy]]、[[QVStrategy]]、[[ReversePowerProtection]] | [[DynamicSOCProtection]]、[[GridLimitProtection]]、[[PowerCompensator]] |

### extra 常見鍵值

| 鍵 | 用途 | 使用者 |
|----|------|--------|
| `"voltage"` | 系統電壓 (V) | [[QVStrategy]] |
| `"frequency"` | 系統頻率 (Hz) | [[FPStrategy]]、[[DroopStrategy]] |
| `"meter_power"` | 電表功率 (kW) | [[ReversePowerProtection]]、[[PowerCompensator]] |
| `"system_alarm"` | 系統告警旗標 | [[SystemAlarmProtection]] |
| `"remaining_s_kva"` | 剩餘視在功率容量 | [[CascadingStrategy]] |
| `"schedule_p"` | 排程功率設定點 (kW) | [[DroopStrategy]] |
| `"dt"` | 距上次呼叫的時間間隔 (秒) | [[PowerCompensator]] |

> [!tip] CTX_* 常數（v0.7.1）
> `csp_lib.controller.core.constants` 提供上述所有鍵的具名常數，避免字串魔法值：
>
> ```python
> from csp_lib.controller.core.constants import (
>     CTX_FREQUENCY,       # "frequency"
>     CTX_VOLTAGE,         # "voltage"
>     CTX_METER_POWER,     # "meter_power"
>     CTX_SCHEDULE_P,      # "schedule_p"
>     CTX_DT,              # "dt"
>     CTX_SYSTEM_ALARM,    # "system_alarm"
>     CTX_REMAINING_S_KVA, # "remaining_s_kva"
> )
>
> # 使用常數而非字串
> freq = context.extra.get(CTX_FREQUENCY, 60.0)
> ```
>
> 這些常數為 internal，僅供策略實作內部使用，不屬於公開 API。

## 輔助方法

| 方法 | 回傳 | 說明 |
|------|------|------|
| `percent_to_kw(p_percent)` | `float` | 將百分比轉換為 kW |
| `percent_to_kvar(q_percent)` | `float` | 將百分比轉換為 kVar |

> [!warning] 呼叫 `percent_to_kw` / `percent_to_kvar` 前需確保 `system_base` 已設定，否則拋出 `ValueError`。

## Quick Example

```python
from csp_lib.controller import StrategyContext, Command, SystemBase
from csp_lib.core import RuntimeParameters

# 建立帶有 params 的 context
params = RuntimeParameters(soc_max=95.0, soc_min=5.0)

context = StrategyContext(
    last_command=Command(),
    soc=75.0,
    system_base=SystemBase(p_base=1000, q_base=500),
    extra={"voltage": 380.0, "frequency": 60.0},
    params=params,
)

# extra: 讀取設備資料
freq = context.extra["frequency"]  # 60.0

# params: 讀取系統參數
soc_max = context.params.get("soc_max")  # 95.0

# 百分比轉換
p_kw = context.percent_to_kw(50)    # -> 500.0
q_kvar = context.percent_to_kvar(20) # -> 100.0
```

## 相關連結

- [[Command]] — `last_command` 的型別
- [[SystemBase]] — `system_base` 的型別
- [[Strategy]] — `execute(context)` 接收 StrategyContext
- [[StrategyExecutor]] — 負責建構與注入 StrategyContext
- [[DynamicSOCProtection]] — 透過 `params` 讀取動態 SOC 上下限
- [[GridLimitProtection]] — 透過 `params` 讀取功率限制
- [[PowerCompensator]] — 透過 `extra` 讀取量測值
