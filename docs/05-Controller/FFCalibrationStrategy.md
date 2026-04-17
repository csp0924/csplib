---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/calibration.py
updated: 2026-04-16
version: ">=0.7.3"
---

# FFCalibrationStrategy

FF Table 步階校準策略（維護型一次性操作）。

> [!info] v0.5.0 新增

> [!info] 回到 [[_MOC Controller]]

## 概述

遍歷各功率 bin，在每個 bin 輸出對應功率指令、等穩態、記錄 `ff_ratio`，完成後寫入 [[PowerCompensator]] 的 FF Table。

這是一個維護型策略，透過 [[ModeManager]] 的 `push_override()` 啟動，完成後由 `on_complete` callback 觸發 `pop_override()` 回到正常模式。

## 狀態機

```
IDLE ──(on_activate)──> STEPPING ──(所有 bin 完成)──> DONE
  ^                        |
  └──(on_deactivate)───────┘  (中斷時回到 IDLE，FF 表不更新)
```

| 狀態 | 說明 |
|------|------|
| `IDLE` | 初始/待機狀態，回傳 `last_command` |
| `STEPPING` | 逐 bin 校準中 |
| `DONE` | 校準完成，輸出 P=0 |

## FFCalibrationConfig

`@dataclass` 配置，繼承 [[ConfigMixin]]。

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `step_pct` | `int` | `5` | 每步幅度 (% of rated power) |
| `min_pct` | `int` | `-100` | 最小校準百分比（負值 = 充電側） |
| `max_pct` | `int` | `100` | 最大校準百分比 |
| `skip_zero` | `bool` | `True` | 是否跳過 0% bin |
| `steady_threshold` | `float` | `0.02` | 穩態門檻 \|error/setpoint\| |
| `steady_cycles` | `int` | `10` | 連續穩態週期數，達標後記錄 FF |
| `settle_wait_cycles` | `int` | `5` | 切 bin 後跳過 N 個週期再判穩態 |
| `measurement_key` | `str` | `"meter_power"` | context.extra 中量測值的 key |
| `interval` | `float` | `0.3` | 執行週期（秒） |

## 每個 Bin 的校準流程

1. 輸出 `setpoint = rated × bin_index × step_pct / 100`
2. 跳過 `settle_wait_cycles` 個週期
3. 判斷穩態：`|error / setpoint| < steady_threshold`
4. 連續 `steady_cycles` 個週期穩態 -> 記錄 `ff_ratio = setpoint / avg_measurement`
5. FF ratio clamp 至 [0.8, 1.5]
6. 切到下一個 bin

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `config` | `FFCalibrationConfig \| None` | 校準配置 |
| `compensator` | `PowerCompensator \| None` | 校準完成後寫入的補償器 |
| `rated_power` | `float` | 額定功率 (kW)，0 表示從 `system_base` 取 |
| `on_complete` | `Callable[[dict[int, float]], Awaitable[None]] \| None` | 校準完成 callback |

## 公開屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `state` | `str` | 目前狀態（`"idle"` / `"stepping"` / `"done"`） |
| `progress` | `dict` | 校準進度詳情 |
| `results` | `dict[int, float]` | 校準結果 `{bin_index: ff_ratio}` |

## Quick Example

```python
from csp_lib.controller.calibration import FFCalibrationStrategy, FFCalibrationConfig
from csp_lib.controller.compensator import PowerCompensator

compensator = PowerCompensator(...)

async def handle_done(results: dict[int, float]) -> None:
    print(f"校準完成: {len(results)} bins")
    await controller.pop_override("ff_cal")

cal = FFCalibrationStrategy(
    config=FFCalibrationConfig(step_pct=5, steady_cycles=10),
    compensator=compensator,
    rated_power=2000.0,
    on_complete=handle_done,
)

# 註冊為維護模式
controller.register_mode("ff_cal", cal, ModePriority.MANUAL)

# 觸發校準
await controller.push_override("ff_cal")
```

> [!note] v0.7.3 BUG-007
> `_finish()` 方法已重構為呼叫 `compensator.update_ff_bin()` 和 `compensator.persist_ff_table()` public API，不再直接存取 `_ff_table` / `_save_ff_table`。對外行為不變。

## 相關連結

- [[Strategy]] — 基礎類別
- [[PowerCompensator]] — 校準目標（`update_ff_bin()` / `persist_ff_table()` public API）
- [[FFTableRepository]] — FF 表持久化
- [[ModeManager]] — 透過 override 啟動校準
- [[Command]] — 輸出的功率命令
