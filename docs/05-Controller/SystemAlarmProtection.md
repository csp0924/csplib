---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/system/protection.py
created: 2026-02-17
---

# SystemAlarmProtection

系統告警保護規則，告警時強制 P=0, Q=0。

> [!info] 回到 [[_MOC Controller]]

## 概述

當 `context.extra["system_alarm"]` 為 `True` 時，強制將命令設為 `Command(p_target=0.0, q_target=0.0)`，無視原始命令的任何值。

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `alarm_key` | `str` | `"system_alarm"` | extra 中系統告警的鍵名 |

## 保護邏輯

```
if context.extra["system_alarm"] == True:
    return Command(p_target=0.0, q_target=0.0)
else:
    return command  (不修改)
```

## 資料來源

| 鍵 | 來源 | 說明 |
|----|------|------|
| `context.extra["system_alarm"]` | 外部注入 | 系統告警旗標 (bool) |

> [!warning] 與 [[SOCProtection]] 和 [[ReversePowerProtection]] 不同，此規則同時清除 P 和 Q，是最嚴格的保護措施。

## 相關連結

- [[ProtectionGuard]] — 保護規則鏈，管理此規則
- [[SOCProtection]] — 另一個保護規則
- [[ReversePowerProtection]] — 另一個保護規則
- [[StopStrategy]] — 功能類似（P=0, Q=0），但作為策略而非保護規則
