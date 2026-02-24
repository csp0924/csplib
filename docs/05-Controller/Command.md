---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/core/command.py
created: 2026-02-17
---

# Command

策略輸出的**不可變命令**，封裝有功功率與無功功率目標值。

> [!info] 回到 [[_MOC Controller]]

## 概述

`Command` 使用 `@dataclass(frozen=True)` 實作，確保一旦建立就無法被修改。所有變更都透過 `with_p()` / `with_q()` 方法產生新的 Command 實例。

## 屬性

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `p_target` | `float` | `0.0` | 有功功率目標值 (kW) |
| `q_target` | `float` | `0.0` | 無功功率目標值 (kVar) |

## 方法

| 方法 | 回傳 | 說明 |
|------|------|------|
| `with_p(p)` | `Command` | 建立新 Command，替換 P 值 |
| `with_q(q)` | `Command` | 建立新 Command，替換 Q 值 |

## 程式碼範例

```python
from csp_lib.controller import Command

cmd = Command(p_target=100.0, q_target=50.0)
cmd2 = cmd.with_p(200.0)  # Create new Command with P=200
# -> Command(P=200.0kW, Q=50.0kVar)
```

## 設計備註

- 不可變設計使 Command 可安全地在多個模組間傳遞，不需擔心被意外修改
- `__str__` 輸出格式：`Command(P=100.0kW, Q=50.0kVar)`
- 內部使用 `dataclasses.replace()` 實作 `with_p()` / `with_q()`

## 相關連結

- [[StrategyContext]] — 上下文中包含 `last_command`
- [[Strategy]] — `execute()` 方法回傳 Command
- [[ProtectionGuard]] — 保護規則可修改 Command
- [[SystemBase]] — 百分比轉換為 kW/kVar 的基準值
