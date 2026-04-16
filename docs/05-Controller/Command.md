---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/core/command.py
created: 2026-02-17
updated: 2026-04-16
version: ">=0.7.3"
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
| `is_fallback` | `bool` | `False` | 是否為 fallback 命令（v0.7.3 BUG-011）。`StrategyExecutor` 策略執行失敗時回傳 `Command(0, 0, is_fallback=True)`，供監控、叢集等上層辨識異常情境 |

## 方法

| 方法 | 回傳 | 說明 |
|------|------|------|
| `with_p(p)` | `Command` | 建立新 Command，替換 P 值（保留 `is_fallback`） |
| `with_q(q)` | `Command` | 建立新 Command，替換 Q 值（保留 `is_fallback`） |

## 程式碼範例

```python
from csp_lib.controller import Command

cmd = Command(p_target=100.0, q_target=50.0)
cmd2 = cmd.with_p(200.0)  # 建立新 Command，P=200，is_fallback 保留為 False
# -> Command(P=200.0kW, Q=50.0kVar)

# StrategyExecutor 執行策略失敗時自動回傳：
fallback = Command(p_target=0.0, q_target=0.0, is_fallback=True)
if fallback.is_fallback:
    logger.warning("策略執行失敗，收到 fallback 零命令")
```

## 設計備註

- 不可變設計使 Command 可安全地在多個模組間傳遞，不需擔心被意外修改
- `__str__` 輸出格式：`Command(P=100.0kW, Q=50.0kVar)`
- 內部使用 `dataclasses.replace()` 實作 `with_p()` / `with_q()`，`is_fallback` 自動繼承
- `is_fallback=True` 的 Command 由 `StrategyExecutor` 在 `except Exception` 路徑建立；`_last_command` 不在此路徑更新，確保下輪 `context.last_command` 仍是上次正常命令

> [!note] v0.7.3 新增
> `is_fallback` 欄位由 BUG-011 修復引入。升級前請確認監控/叢集程式碼若依賴 `last_command` 回傳值做狀態判斷，是否需要額外處理 fallback 情境。

## 相關連結

- [[StrategyContext]] — 上下文中包含 `last_command`
- [[Strategy]] — `execute()` 方法回傳 Command
- [[ProtectionGuard]] — 保護規則可修改 Command
- [[SystemBase]] — 百分比轉換為 kW/kVar 的基準值
