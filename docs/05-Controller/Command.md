---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/core/command.py
created: 2026-02-17
updated: 2026-04-17
version: ">=0.8.0"
---

# Command

策略輸出的**不可變命令**，封裝有功功率與無功功率目標值。

> [!info] 回到 [[_MOC Controller]]

## 概述

`Command` 使用 `@dataclass(frozen=True, slots=True)` 實作，確保一旦建立就無法被修改。所有變更都透過 `with_p()` / `with_q()` 方法產生新的 Command 實例。

v0.8.0 起，`p_target` 與 `q_target` 的型別擴寬為 `float | NoChange`，可傳入 `NO_CHANGE` sentinel 表示「此軸不變更」，讓 `CommandRouter` 跳過對應軸的設備寫入。

## Quick Example

```python
from csp_lib.controller import Command, NO_CHANGE, is_no_change

# QV 策略：只控 Q，P 軸不動
cmd = Command(p_target=NO_CHANGE, q_target=50.0)

# CommandRouter 收到後跳過 P 軸寫入，設備保留當前 P 值
# 確認是否為 NO_CHANGE（TypeGuard 版本）
if is_no_change(cmd.p_target):
    print("P 軸跳過")  # mypy 在此分支確認 p_target: NoChange

# 取得有效數值（NO_CHANGE → 回傳 fallback）
p_float = cmd.effective_p(fallback=0.0)  # -> 0.0
q_float = cmd.effective_q()              # -> 50.0
```

## 屬性

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `p_target` | `float \| NoChange` | `0.0` | 有功功率目標值 (kW)；`NO_CHANGE` 表示此軸不寫入 |
| `q_target` | `float \| NoChange` | `0.0` | 無功功率目標值 (kVar)；`NO_CHANGE` 表示此軸不寫入 |
| `is_fallback` | `bool` | `False` | 是否為 fallback 命令（v0.7.3）。`StrategyExecutor` 策略執行失敗時回傳 `Command(0.0, 0.0, is_fallback=True)`，供監控、叢集等上層辨識異常情境 |

## 方法

| 方法 | 簽名 | 說明 |
|------|------|------|
| `with_p(p)` | `(float \| NoChange) -> Command` | 建立新 Command，替換 P 值（保留 `is_fallback`） |
| `with_q(q)` | `(float \| NoChange) -> Command` | 建立新 Command，替換 Q 值（保留 `is_fallback`） |
| `effective_p(fallback=0.0)` | `(float) -> float` | 取得有效 P 值；若為 NO_CHANGE 回傳 `fallback`（v0.8.0） |
| `effective_q(fallback=0.0)` | `(float) -> float` | 取得有效 Q 值；若為 NO_CHANGE 回傳 `fallback`（v0.8.0） |

## NoChange Sentinel（v0.8.0）

`NoChange` 是全域單例，透過模組常數 `NO_CHANGE` 使用，表示「此軸保留設備當前值，不寫入」。

| 名稱 | 說明 |
|------|------|
| `NoChange` | sentinel 類別，單例（`__new__` 保證同一實例） |
| `NO_CHANGE` | 全域常數，所有地方皆應使用此名稱 |
| `is_no_change(value)` | TypeGuard 函式，True 分支型別收斂為 `NoChange` |

> [!warning] 比較方式
> 必須使用 `value is NO_CHANGE`（身份比較）而非 `value == NO_CHANGE`。
> `bool(NO_CHANGE)` 會拋 `TypeError`，避免在 `if cmd.p_target:` 式樣中被誤用（0.0 是合法 setpoint，NO_CHANGE 是「跳過」，語義不同）。

### 使用場景

```python
from csp_lib.controller import Command, NO_CHANGE

# QV 策略：只管 Q，不動 P
cmd_qv = Command(p_target=NO_CHANGE, q_target=50.0)

# FP 策略：只管 P，不動 Q
cmd_fp = Command(p_target=100.0, q_target=NO_CHANGE)

# Fallback 刻意用 0.0（安全停機，不能保留舊值）
fallback = Command(p_target=0.0, q_target=0.0, is_fallback=True)
```

### effective_p / effective_q

供需要「把 NO_CHANGE 轉成具體 float」的消費點（級聯累加、積分補償器）使用：

```python
cmd = Command(p_target=NO_CHANGE, q_target=30.0)
p = cmd.effective_p(fallback=0.0)  # -> 0.0（NO_CHANGE 轉 fallback）
q = cmd.effective_q()              # -> 30.0
```

## Common Patterns

### 策略組合（Cascade）

在 CascadingStrategy 或 mode switch 場景，下游接收多個策略輸出時，`NO_CHANGE` 可避免策略互相覆蓋：

```python
# QV 策略輸出：P 不管，Q=50
# FP 策略輸出：P=100，Q 不管
# Cascading 將兩者合併為 P=100, Q=50
```

### is_no_change TypeGuard

```python
from csp_lib.controller import is_no_change, Command, NO_CHANGE

def log_command(cmd: Command) -> None:
    p_str = "NO_CHANGE" if is_no_change(cmd.p_target) else f"{cmd.p_target:.1f} kW"
    q_str = "NO_CHANGE" if is_no_change(cmd.q_target) else f"{cmd.q_target:.1f} kVar"
    print(f"P={p_str}, Q={q_str}")
```

## 設計備註

- 不可變設計（`frozen=True, slots=True`）使 Command 可安全地在多個模組間傳遞
- `__str__` 輸出：`NO_CHANGE` 軸顯示 `"NO_CHANGE"`，其餘顯示 `"100.0kW"` 格式
- 內部使用 `dataclasses.replace()` 實作 `with_p()` / `with_q()`，`is_fallback` 自動繼承
- fallback 路徑（`StrategyExecutor` 策略執行失敗）刻意使用 `0.0` 而非 `NO_CHANGE` — 安全停機語義必須明確下達 P=0, Q=0，不能保留可能造成危險的舊值

> [!note] v0.7.3 / v0.8.0 新增欄位
> - `is_fallback`（v0.7.3 BUG-011）：升級前請確認監控/叢集程式碼是否需要處理 fallback 情境。
> - `NoChange` / `NO_CHANGE` / `is_no_change()` / `effective_p()` / `effective_q()`（v0.8.0 WI-V080-004）：既有 `Command(p_target=0.0)` 建構完全不變，型別擴寬屬向後相容。

## 相關連結

- [[StrategyContext]] — 上下文中包含 `last_command`
- [[Strategy]] — `execute()` 方法回傳 Command
- [[ProtectionGuard]] — 保護規則可修改 Command
- [[CommandRouter]] — 偵測 NO_CHANGE 跳過對應軸寫入
- [[SystemBase]] — 百分比轉換為 kW/kVar 的基準值
