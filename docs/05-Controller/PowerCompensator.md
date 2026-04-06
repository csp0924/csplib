---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/compensator.py
updated: 2026-04-06
version: ">=0.7.1"
---

# PowerCompensator

前饋 (FF) + 積分 (I) 閉環功率補償器，實作 [[CommandProcessor]] Protocol。

> [!info] v0.5.0 新增

> [!info] 回到 [[_MOC Controller]]

## 概述

補償 PCS 非線性與輔電損耗，使電網端實際功率更貼近目標值。核心控制方程式：

```
command = ff(power_bin) × setpoint + Ki × ∫error·dt
```

- **前饋補償**：按功率區間 (bin) 查表取得 FF 係數，補償已知的系統偏差
- **積分修正**：短期殘差修正，含 anti-windup / deadband / clamp
- **穩態學習**：I 項貢獻自動吸收進 FF 表，實現長期自適應
- **暫態閘門**：setpoint 變更後等 PCS 到位才啟動 I

### 充放電方向

| 方向 | 公式 | 說明 |
|------|------|------|
| 放電 (P >= 0) | `ff_output = ff × setpoint` | FF 放大 setpoint |
| 充電 (P < 0) | `ff_output = setpoint / ff` | 補償輔電使電網讀數更負 |

## PowerCompensatorConfig

`@dataclass` 配置。

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `rated_power` | `float` | `2000.0` | 系統額定功率 (kW) |
| `output_min` | `float` | `-2000.0` | 輸出下限 (kW) |
| `output_max` | `float` | `2000.0` | 輸出上限 (kW) |
| `ki` | `float` | `0.3` | 積分增益 (1/s) |
| `integral_max_ratio` | `float` | `0.05` | I 項最大貢獻 = ratio x rated_power |
| `deadband` | `float` | `0.5` | 死區 (kW)，誤差低於此值不累積 I |
| `power_bin_step_pct` | `int` | `5` | FF 表功率區間寬度 (% of rated) |
| `steady_state_threshold` | `float` | `0.02` | 穩態門檻 \|error/setpoint\| |
| `steady_state_cycles` | `int` | `5` | 連續穩態週期數，達標後觸發 FF 學習 |
| `settle_ratio` | `float` | `0.15` | 暫態閘門比例 |
| `hold_cycles` | `int` | `2` | setpoint 變更後暫停積分的週期數 |
| `ff_min` | `float` | `0.8` | FF 補償係數下限 |
| `ff_max` | `float` | `1.5` | FF 補償係數上限 |
| `error_ema_alpha` | `float` | `0.0` | 誤差 EMA 濾波係數（0=停用） |
| `rate_limit` | `float` | `0.0` | 輸出變化率限制 (kW/s, 0=停用) |
| `measurement_key` | `str` | `"meter_power"` | context.extra 中量測值的 key |
| `persist_path` | `str` | `""` | FF 表持久化路徑（空=不持久化） |

## 演算法流程

1. **零目標檢查** — setpoint ≈ 0 時重置狀態，回傳 0
2. **Setpoint 變動策略** — 清除積分、進入 hold、繼承 FF
3. **誤差計算** — `error = setpoint - measurement`
4. **誤差濾波** — 可選 EMA 濾波
5. **前饋查表** — 按 power_bin 取 FF 係數
6. **飽和檢測** — 輸出飽和時重置積分（anti-windup）
7. **積分更新** — hold 結束 + 死區外才累積
8. **計算輸出** — `ff_output + ki × integral`
9. **輸出限幅** — clamp 至 [output_min, output_max]
10. **變化率限制** — 可選 rate limiter
11. **穩態學習** — 條件達標時吸收 I 項進 FF 表

## context.extra 需求

| 鍵 | 型別 | 必要 | 說明 |
|----|------|------|------|
| `measurement_key`（預設 `meter_power`） | `float` | 是 | 電網端實際功率 (kW) |
| `dt` | `float` | 否（預設 0.3） | 距上次呼叫的時間間隔 (秒) |

## FF Table 持久化

透過 [[FFTableRepository]] Protocol 實作持久化。建構時可注入自訂 repository：

- 注入 repository -> 使用注入的
- 未注入但有 `persist_path` -> 自動建立 [[FFTableRepository#JsonFFTableRepository|JsonFFTableRepository]]
- 都沒有 -> 不持久化（僅記憶體）

## 公開介面

| 方法 / 屬性 | 說明 |
|-------------|------|
| `async process(command, context)` | [[CommandProcessor]] 介面實作 |
| `compensate(setpoint, measurement, dt)` | 核心補償計算（同步） |
| `reset()` | 重置積分與追蹤狀態（保留 FF 表） |
| `reset_ff_table()` | 重置 FF 表為全 1.0 |
| `load_ff_table(table)` | 外部載入 FF 表（如校準結果） |
| `async async_init()` | 從 async repository 載入 FF 表 |
| `enabled` | 啟用/停用補償器 |
| `diagnostics` | 診斷資訊 dict |
| `ff_table` | FF 表淺拷貝 |

## Quick Example

```python
from csp_lib.controller.compensator import PowerCompensator, PowerCompensatorConfig

compensator = PowerCompensator(PowerCompensatorConfig(
    rated_power=2000.0,
    measurement_key="meter_power",
    persist_path="ff_table.json",
))

# 作為 post_protection_processor 使用
from csp_lib.integration import SystemControllerConfig

config = SystemControllerConfig(
    post_protection_processors=[compensator],
)

# 或手動呼叫
compensated_cmd = await compensator.process(command, context)
```

## 相關連結

- [[CommandProcessor]] — 實作的 Protocol
- [[FFTableRepository]] — FF 表持久化介面
- [[FFCalibrationStrategy]] — FF 表步階校準
- [[ProtectionGuard]] — 保護鏈（補償器位於保護鏈之後）
- [[Command]] — 輸入/輸出的命令物件
