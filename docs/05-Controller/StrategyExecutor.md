---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/executor/strategy_executor.py
created: 2026-02-17
updated: 2026-05-08
version: ">=0.10.0"
---

# StrategyExecutor

策略執行器，管理策略的執行生命週期。

> [!info] 回到 [[_MOC Controller]]

## 概述

StrategyExecutor 根據策略的 [[ExecutionMode|ExecutionConfig]] 決定執行方式：
- **PERIODIC**: 固定週期，v0.8.0 起使用 `next_tick_delay()` 絕對時間錨定（work-first：啟動後立即執行第一次）
- **TRIGGERED**: 使用 `asyncio.Event` 等待外部觸發
- **HYBRID**: 週期執行，但可被 `trigger()` 提前觸發；提前觸發後重設 anchor，下次 tick 從觸發點起算完整 interval

每次執行前會透過 `context_provider` 取得基礎上下文，再以 `dataclasses.replace()` 注入 `last_command` 與 `current_time`。

> [!warning] v0.8.0 行為變更（PERIODIC / HYBRID）
> v0.8.0 前：啟動後先等待一個 `interval_seconds`，再執行第一次策略。
> v0.8.0 起：**立即執行**第一次策略（work-first），再按 `next_tick_delay()` 排程後續週期。若上層測試或整合邏輯依賴「啟動後先等 N 秒」的舊語義，需調整。TRIGGERED 模式不受影響。

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
| `health()` | 回傳 `HealthReport`（實作 [[HealthCheckable]]，sync、不 await、idempotent） |
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

### health() 快速範例

```python
from csp_lib.core.health import HealthStatus

report = executor.health()
print(report.status)    # HealthStatus.HEALTHY / DEGRADED / UNHEALTHY
print(report.message)   # 人可讀描述
print(report.details)   # 結構化欄位（見下方 health() 段落）
```

## 執行流程

```
run()
 └─ while not stop_event:
      ├─ [PERIODIC/HYBRID] 首次立即執行（work-first，v0.8.0）
      │   之後 next_tick_delay(interval) 絕對時間錨定等待
      ├─ [TRIGGERED] asyncio.Event 等待 trigger()
      ├─ context_provider()               # 取得上下文
      ├─ replace(last_command, time)      # 注入不可變副本
      ├─ strategy.execute(context)        # 執行策略
      │   ├─ [成功] last_command = result # 更新 _last_command
      │   │         on_command(result)    # 回呼
      │   └─ [例外] logger.exception(...) # 記錄後回傳 fallback
      │             return Command(0, 0, is_fallback=True)
      │             # _last_command 不更新；**不呼叫 on_command**
      └─ （繼續下一週期）
```

### 異常 Fallback 行為（v0.7.3）

策略執行拋出例外時（`except Exception`）：

1. 回傳 `Command(p_target=0.0, q_target=0.0, is_fallback=True)` 作為 `_execute_strategy` 的 return value
2. `self._last_command` **不更新**，下輪 `context.last_command` 仍是上次正常命令
3. **不呼叫 `on_command` callback**；`run` 主迴圈丟棄 return value，僅 `execute_once()` 會回傳此 fallback command 供 caller 檢視 `is_fallback`
4. Exception 細節由 `logger.exception(...)` 記錄（含 strategy 名稱、SOC、`last_command`）

> [!warning] 升級注意
> v0.7.3 前，異常時回傳 `self._last_command`（上次成功命令）。
> 升級後回傳明確的零命令 + `is_fallback=True`。
> 若上層程式碼依賴異常後仍沿用上次命令的行為，需評估影響。

### 週期漂移修復（v0.8.0）

v0.8.0 前，PERIODIC/HYBRID 以 `asyncio.wait(timeout=interval)` 相對等待，不扣除 `_execute_strategy()` 耗時，導致高頻策略（如 DReg 0.3 s）發生明顯漂移（50 ms exec → 16.7% 漂移）。

v0.8.0 起改用 `csp_lib.core._time_anchor.next_tick_delay()` 絕對時間錨定，與 CAN/PeriodicSender/Modbus read_loop 採相同機制。10 個 cycle 總耗時 drift < 10%（tests 驗證）。

## health() — HealthCheckable 實作

`StrategyExecutor` 實作 [[HealthCheckable]] Protocol（`csp_lib.core`）。

### 簽名

```python
def health(self) -> HealthReport: ...
```

Sync、read-only 快照，**不 await、不取 lock、不修改任何內部狀態**，可在任意 thread / coroutine 中安全呼叫。

### 狀態判定規則（依優先序）

| 狀態 | 條件 |
|------|------|
| `UNHEALTHY` | `_task` 已結束且有未處理例外（task died）|
| `UNHEALTHY` | 未啟動（`is_running=False`）且未掛策略（`current_strategy=None`）|
| `DEGRADED` | 執行中（`is_running=True`）但無策略 |
| `DEGRADED` | `last_command.is_fallback=True`（策略例外後回傳零命令）|
| `HEALTHY` | 執行中、有策略、上次命令非 fallback |
| `DEGRADED` | （兜底）已掛策略但尚未呼叫 `run()`（strategy attached but not running）|

### details 欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `is_running` | `bool` | 執行迴圈是否 running |
| `current_strategy` | `str \| None` | 當前策略類別名；無則 `None` |
| `execution_mode` | `str \| None` | `ExecutionMode` 名稱（如 `"PERIODIC"`）；無策略則 `None` |
| `interval_seconds` | `float \| None` | PERIODIC/HYBRID 週期秒數；TRIGGERED 或無策略則 `None` |
| `last_command` | `dict` | `{p_target, q_target, is_fallback}`；NO_CHANGE sentinel 序列化為 `"NO_CHANGE"` |
| `trigger_pending` | `bool` | `_trigger_event` 是否處於 set 狀態 |
| `stop_pending` | `bool` | `_stop_event` 是否處於 set 狀態 |
| `has_offloader` | `bool` | 是否注入 `ComputeOffloader` |

> [!note] 上層聚合（J-P2 待完成）
> `SystemController.health()` 聚合 StrategyExecutor.health() 的工作列於 `BACKLOG.md` 子範圍 J（`feat(integration): SystemController.describe()` 聚合所有子系統）。StrategyExecutor 端實作已就緒，待 SystemController 端串接。

## 相關連結

- [[Strategy]] — 被管理的策略基礎類別
- [[StrategyContext]] — 注入策略的上下文
- [[Command]] — 策略輸出（v0.8.0 起支援 NO_CHANGE）
- [[ExecutionMode]] — 決定等待方式（interval_seconds v0.8.0 改為 float）
- [[ModeManager]] — 透過 on_strategy_change 回呼與 Executor 協作
- [[SystemController]] — `attach_read_trigger()` 綁定 EVENT_READ_COMPLETE → `trigger()`
