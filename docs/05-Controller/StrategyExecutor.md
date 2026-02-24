---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/executor/strategy_executor.py
created: 2026-02-17
---

# StrategyExecutor

策略執行器，管理策略的執行生命週期。

> [!info] 回到 [[_MOC Controller]]

## 概述

StrategyExecutor 根據策略的 [[ExecutionMode|ExecutionConfig]] 決定執行方式：
- **PERIODIC**: 固定週期，使用 `asyncio.wait_for` 搭配 stop_event 實現可中斷等待
- **TRIGGERED**: 使用 `asyncio.Event` 等待外部觸發
- **HYBRID**: 週期執行，但可被 `trigger()` 提前觸發

每次執行前會透過 `context_provider` 取得基礎上下文，再以 `dataclasses.replace()` 注入 `last_command` 與 `current_time`。

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `context_provider` | `Callable[[], StrategyContext]` | 提供上下文的 callable |
| `on_command` | `Callable[[Command], Awaitable[None]]` (Optional) | 命令產生後的回呼 |
| `offloader` | `ComputeOffloader` (Optional) | 計算卸載器，將同步策略卸載到執行緒池 |

## 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `last_command` | [[Command]] | 最後一次執行的命令 |
| `current_strategy` | `Optional[`[[Strategy]]`]` | 當前策略 |
| `is_running` | `bool` | 是否正在執行 |

## 方法

| 方法 | 說明 |
|------|------|
| `set_strategy(strategy)` | 設定/切換策略，自動呼叫 on_deactivate / on_activate |
| `run()` | 主執行迴圈 (async) |
| `trigger()` | 手動觸發執行 (適用於 TRIGGERED / HYBRID) |
| `stop()` | 停止執行迴圈 |
| `execute_once()` | 執行一次策略 (測試用，不考慮執行模式) |
| `set_context_provider(provider)` | 動態替換 context provider |
| `set_on_command(callback)` | 動態替換 on_command 回呼 |

## 程式碼範例

```python
from csp_lib.controller import StrategyExecutor

executor = StrategyExecutor(
    context_provider=get_context,      # Callable returning StrategyContext
    on_command=handle_command,         # Optional async callback
)

await executor.set_strategy(strategy)  # Auto calls on_activate/on_deactivate
await executor.run()                   # Main execution loop
executor.trigger()                     # Manual trigger (TRIGGERED/HYBRID)
executor.stop()                        # Stop loop

# One-shot execution (for testing)
command = await executor.execute_once()
```

## 執行流程

```
run()
 └─ while not stop_event:
      ├─ wait_for_execution(config)   # 根據 mode 等待
      ├─ context_provider()           # 取得上下文
      ├─ replace(last_command, time)  # 注入不可變副本
      ├─ strategy.execute(context)    # 執行策略
      ├─ last_command = result        # 更新
      └─ on_command(result)           # 回呼
```

## 相關連結

- [[Strategy]] — 被管理的策略基礎類別
- [[StrategyContext]] — 注入策略的上下文
- [[Command]] — 策略輸出
- [[ExecutionMode]] — 決定等待方式
- [[ModeManager]] — 透過 on_strategy_change 回呼與 Executor 協作
