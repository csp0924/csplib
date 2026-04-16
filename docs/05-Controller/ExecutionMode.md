---
tags:
  - type/enum
  - layer/controller
  - status/complete
source: csp_lib/controller/core/execution.py
created: 2026-02-17
updated: 2026-04-17
version: ">=0.8.0"
---

# ExecutionMode

策略執行模式列舉與執行配置。

> [!info] 回到 [[_MOC Controller]]

## ExecutionMode 列舉

| 模式 | 說明 |
|------|------|
| `PERIODIC` | 固定週期執行 |
| `TRIGGERED` | 僅在外部觸發時執行 |
| `HYBRID` | 週期執行，但可被提前觸發 |

### 各策略使用的模式

| 策略 | 模式 | 週期 |
|------|------|------|
| [[PQModeStrategy]] | PERIODIC | 1s |
| [[PVSmoothStrategy]] | PERIODIC | 900s |
| [[QVStrategy]] | PERIODIC | 1s |
| [[FPStrategy]] | PERIODIC | 1s |
| [[DroopStrategy]] | PERIODIC | 1s |
| [[IslandModeStrategy]] | TRIGGERED | - |
| [[BypassStrategy]] | TRIGGERED | - |
| [[StopStrategy]] | PERIODIC | 1s |
| [[RampStopStrategy]] | PERIODIC | 1s |
| [[ScheduleStrategy]] | PERIODIC | 1s (委派給子策略) |
| [[LoadSheddingStrategy]] | PERIODIC | 5s (config) |
| [[FFCalibrationStrategy]] | PERIODIC | 1s (config) |

## ExecutionConfig 類別

`@dataclass(frozen=True)` 的不可變配置。

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `mode` | `ExecutionMode` | (必填) | 執行模式 |
| `interval_seconds` | `float` | `1` | 週期秒數（v0.8.0 起改為 float，支援 sub-second 如 0.3 s；適用於 PERIODIC 和 HYBRID） |

> [!note] v0.8.0 型別變更
> `interval_seconds` 由 `int` 改為 `float`，向後相容（既有 int 值可直接賦值）。現可傳入 `0.3` 等小數值支援高頻策略（如 DReg）。

> [!warning] PERIODIC 與 HYBRID 模式下 `interval_seconds` 必須大於 0，否則在 `__post_init__` 中拋出 `ValueError`。

## 程式碼範例

```python
from csp_lib.controller import ExecutionConfig, ExecutionMode

config = ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)
config = ExecutionConfig(mode=ExecutionMode.TRIGGERED)  # interval_seconds 不影響
config = ExecutionConfig(mode=ExecutionMode.HYBRID, interval_seconds=5)

# v0.8.0+ 支援 sub-second（DReg 0.3s 需求）
config_fast = ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=0.3)
```

## 相關連結

- [[Strategy]] — `execution_config` 屬性回傳 ExecutionConfig
- [[StrategyExecutor]] — 根據 ExecutionConfig 決定等待方式
