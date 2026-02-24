---
tags:
  - type/protocol
  - layer/controller
  - status/complete
source: csp_lib/controller/core/strategy.py
created: 2026-02-17
---

# Strategy

所有控制策略的**抽象基礎類別** (ABC)。

> [!info] 回到 [[_MOC Controller]]

## 概述

所有策略必須繼承 `Strategy` 並實作 `execution_config` 屬性與 `execute()` 方法。可選擇覆寫 `on_activate()` 與 `on_deactivate()` 來處理策略啟用/停用時的生命週期事件。

## 抽象介面

| 成員 | 類型 | 說明 |
|------|------|------|
| `execution_config` | `property (abstract)` | 回傳 [[ExecutionMode\|ExecutionConfig]]，定義執行模式與週期 |
| `execute(context)` | `method (abstract)` | 執行策略邏輯，回傳 [[Command]] |
| `on_activate()` | `async method` | 策略啟用時呼叫 (可選覆寫) |
| `on_deactivate()` | `async method` | 策略停用時呼叫 (可選覆寫) |

## 程式碼範例

### 自訂策略

```python
from csp_lib.controller import Strategy, ExecutionConfig, ExecutionMode, StrategyContext, Command

class MyStrategy(Strategy):
    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command(p_target=100.0)

    async def on_activate(self) -> None:
        ...  # Optional: called when strategy is activated

    async def on_deactivate(self) -> None:
        ...  # Optional: called when strategy is deactivated
```

## 擴充性設計

- 策略可在 `execute()` 中呼叫其他策略的 `execute()` 取得 Command
- 自行組合多個 Command 達成複合策略效果
- [[ScheduleStrategy]] 即為此模式的實際應用

## 相關連結

- [[ExecutionMode]] — 定義執行模式 (PERIODIC / TRIGGERED / HYBRID)
- [[StrategyContext]] — `execute()` 方法的輸入參數
- [[Command]] — `execute()` 方法的回傳值
- [[StrategyExecutor]] — 管理 Strategy 的執行生命週期
- [[ModeManager]] — 管理多個 Strategy 的註冊與切換
