---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/system/protection.py
created: 2026-02-17
---

# ReversePowerProtection

表後逆送保護規則。

> [!info] 回到 [[_MOC Controller]]

## 概述

防止儲能系統放電功率過大，導致多餘電力逆送回電網。從 `context.extra["meter_power"]` 讀取電表功率，限制放電上限為 `meter_power + threshold`。

## 功率正負號定義

| 符號 | meter_power | p_target |
|------|-------------|----------|
| 正 | 買電 (從電網進) | 放電 |
| 負 | 賣電 (逆送到電網) | 充電 |

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `threshold` | `float` | `0.0` | 允許的逆送門檻 (kW)，預設不允許逆送 |
| `meter_power_key` | `str` | `"meter_power"` | extra 中電表功率的鍵名 |

## 保護邏輯

```
約束: p_target <= meter_power + threshold

若 P < 0 (充電): 不受限
若 P > max_discharge: clamp P = max_discharge
  其中 max_discharge = max(meter_power + threshold, 0)
```

> [!note] `meter_power` 為 `None` 時不介入。

## 資料來源

| 鍵 | 來源 | 說明 |
|----|------|------|
| `context.extra["meter_power"]` | 外部注入 | 電表即時功率 (kW) |

## 相關連結

- [[ProtectionGuard]] — 保護規則鏈，管理此規則
- [[SOCProtection]] — 另一個保護規則
- [[SystemAlarmProtection]] — 另一個保護規則
- [[StrategyContext]] — 從 extra 讀取 meter_power
