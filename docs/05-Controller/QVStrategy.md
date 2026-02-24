---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/qv_strategy.py
created: 2026-02-17
---

# QVStrategy

電壓-無功功率控制策略 (Volt-VAR)。

> [!info] 回到 [[_MOC Controller]]

## 概述

根據系統電壓偏差，透過下垂控制 (Droop Control) 計算無功功率輸出。電壓過低時輸出正 Q (提供無功)，電壓過高時輸出負 Q (吸收無功)。從 `context.extra["voltage"]` 讀取即時電壓值。

## QVConfig

繼承 [[ConfigMixin]]，搭配 `@dataclass` 使用。

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `nominal_voltage` | `float` | `380.0` | 額定電壓 (V) |
| `v_set` | `float` | `100.0` | 電壓設定值 (%) |
| `droop` | `float` | `5.0` | 電壓下垂係數 (%) |
| `v_deadband` | `float` | `0.0` | 電壓死區 (%) |
| `q_max_ratio` | `float` | `0.5` | 最大無功功率比值 (50%) |

### validate() 驗證規則

- 額定電壓 > 0
- 電壓設定值：95% ~ 105%
- 下垂係數：2% ~ 10%
- 死區：0% ~ 0.5%

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | `PERIODIC` |
| 週期 | 1 秒 |

## 計算邏輯

```
V_pu = V_measured / V_nominal
V_set_pu = V_set / 100

if V_pu <= V_set_pu - V_deadband:
    Q = min(0.5 * (V_set_pu - V_deadband - V_pu) / (V_set_pu * droop), Q_max)
elif V_pu >= V_set_pu + V_deadband:
    Q = max(0.5 * (V_set_pu + V_deadband - V_pu) / (V_set_pu * droop), -Q_max)
else:
    Q = 0  (死區)
```

## 程式碼範例

```python
from csp_lib.controller import QVStrategy, QVConfig

strategy = QVStrategy(QVConfig(
    nominal_voltage=380,
    v_set=100,     # Target voltage (%)
    droop=5,       # Droop coefficient (%)
    v_deadband=0,  # Deadband (%)
    q_max_ratio=0.5,
))
# Reads voltage from context.extra["voltage"]
```

## 資料來源

| 鍵 | 來源 | 說明 |
|----|------|------|
| `context.extra["voltage"]` | 外部注入 | 系統即時電壓 (V) |

> [!note] 無電壓資料時維持 `last_command`，P 值保持不變。

## 相關連結

- [[Strategy]] — 基礎類別
- [[StrategyContext]] — 從 `extra["voltage"]` 讀取電壓
- [[SystemBase]] — 將比值轉換為 kVar
- [[CascadingStrategy]] — 常與 PQ 策略級聯使用
