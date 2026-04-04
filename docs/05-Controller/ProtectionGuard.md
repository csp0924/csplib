---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/system/protection.py
created: 2026-02-17
updated: 2026-04-04
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
| [[SOCProtection]] | SOC 高限禁充、低限禁放、警戒區漸進限制 (Deprecated) | `context.soc` |
| [[DynamicSOCProtection]] | 動態 SOC 保護（支援 RuntimeParameters 與 SOCProtectionConfig） | `context.soc` + `RuntimeParameters` |
| [[GridLimitProtection]] | 外部功率限制（電力公司/排程） | `RuntimeParameters` |
| [[ReversePowerProtection]] | 表後逆送保護 | `context.extra["meter_power"]` |
| [[SystemAlarmProtection]] | 系統告警強制停機 | `context.extra["system_alarm"]` |

## Quick Example

```python
from csp_lib.controller import (
    ProtectionGuard, SOCProtectionConfig,
    ReversePowerProtection, SystemAlarmProtection,
)
from csp_lib.controller.system.dynamic_protection import DynamicSOCProtection

guard = ProtectionGuard(rules=[
    DynamicSOCProtection(SOCProtectionConfig(
        soc_high=95,      # 禁止充電上限
        soc_low=5,        # 禁止放電下限
        warning_band=5,   # 警戒區漸進限制
    )),
    ReversePowerProtection(threshold=0),  # 不允許逆送
    SystemAlarmProtection(),               # 告警時強制 P=0, Q=0
])

result = guard.apply(command, context)
# result.protected_command   — 保護後命令
# result.was_modified        — 命令是否被修改
# result.triggered_rules     — 觸發的規則名稱列表
```

## 相關連結

- [[SOCProtection]] — SOC 保護規則 (Deprecated)
- [[DynamicSOCProtection]] — 動態 SOC 保護規則（取代 SOCProtection）
- [[GridLimitProtection]] — 外部功率限制保護規則
- [[ReversePowerProtection]] — 逆送保護規則
- [[SystemAlarmProtection]] — 系統告警保護規則
- [[CommandProcessor]] — Post-Protection 命令處理管線（在 ProtectionGuard 之後執行）
- [[Command]] — 輸入與輸出
- [[StrategyContext]] — 提供保護評估所需的上下文
- [[ModeManager]] — 保護模式通常搭配 PROTECTION 等級的 override
