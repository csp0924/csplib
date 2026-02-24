---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/system/protection.py
created: 2026-02-17
---

# ProtectionGuard

保護規則鏈，使用責任鏈模式 (Chain of Responsibility) 逐一套用所有保護規則。

> [!info] 回到 [[_MOC Controller]]

## 概述

ProtectionGuard 維護一組 `ProtectionRule`，透過 `apply()` 方法鏈式套用所有規則。每個規則可修改或維持原始 [[Command]]，最終回傳 `ProtectionResult` 包含修改結果與觸發紀錄。

## ProtectionRule 抽象基礎類別

所有保護規則必須繼承此 ABC。

| 成員 | 類型 | 說明 |
|------|------|------|
| `name` | `property (abstract)` | 規則名稱 |
| `evaluate(command, context)` | `method (abstract)` | 評估並可能修改命令 |
| `is_triggered` | `property (abstract)` | 是否處於觸發狀態 (診斷用) |

## ProtectionResult

`@dataclass(frozen=True)` 的保護結果。

| 屬性 | 型別 | 說明 |
|------|------|------|
| `original_command` | [[Command]] | 原始命令 |
| `protected_command` | [[Command]] | 保護後命令 |
| `triggered_rules` | `list[str]` | 觸發的規則名稱列表 |
| `was_modified` | `property -> bool` | 命令是否被修改 |

## 方法

| 方法 | 說明 |
|------|------|
| `add_rule(rule)` | 新增保護規則 |
| `remove_rule(name)` | 依名稱移除保護規則 |
| `apply(command, context)` | 鏈式套用所有規則，回傳 ProtectionResult |

## 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `last_result` | `ProtectionResult\|None` | 上次套用結果 |
| `rules` | `list[ProtectionRule]` | 所有保護規則 |

## 內建保護規則

| 規則 | 說明 | 資料來源 |
|------|------|---------|
| [[SOCProtection]] | SOC 高限禁充、低限禁放、警戒區漸進限制 | `context.soc` |
| [[ReversePowerProtection]] | 表後逆送保護 | `context.extra["meter_power"]` |
| [[SystemAlarmProtection]] | 系統告警強制停機 | `context.extra["system_alarm"]` |

## 程式碼範例

```python
from csp_lib.controller import (
    ProtectionGuard, SOCProtection, SOCProtectionConfig,
    ReversePowerProtection, SystemAlarmProtection,
)

guard = ProtectionGuard(rules=[
    SOCProtection(SOCProtectionConfig(
        soc_high=95,      # Prohibit charging above 95%
        soc_low=5,        # Prohibit discharging below 5%
        warning_band=5,   # Gradual limiting in warning zone
    )),
    ReversePowerProtection(threshold=0),  # No reverse power
    SystemAlarmProtection(),               # Force P=0, Q=0 on system alarm
])

result = guard.apply(command, context)
# result.protected_command   - modified command
# result.was_modified        - whether command was changed
# result.triggered_rules     - list of triggered rule names
```

## 相關連結

- [[SOCProtection]] — SOC 保護規則
- [[ReversePowerProtection]] — 逆送保護規則
- [[SystemAlarmProtection]] — 系統告警保護規則
- [[Command]] — 輸入與輸出
- [[StrategyContext]] — 提供保護評估所需的上下文
- [[ModeManager]] — 保護模式通常搭配 PROTECTION 等級的 override
