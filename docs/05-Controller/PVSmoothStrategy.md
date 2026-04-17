---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/pv_smooth_strategy.py
created: 2026-02-17
updated: 2026-04-17
version: ">=0.8.2"
---

# PVSmoothStrategy

PV 功率平滑控制策略。

> [!info] 回到 [[_MOC Controller]]

## 概述

根據 PV 歷史功率的平均值計算目標輸出，並限制功率變化速率 (Ramp Rate Limiting)，避免功率劇烈波動。使用 [[PVDataService]] 取得歷史功率資料。

## PVSmoothConfig

繼承 [[ConfigMixin]]，搭配 `@dataclass` 使用。

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `capacity` | `float` | `1000.0` | PV 系統容量 (kW) |
| `ramp_rate` | `float` | `10.0` | 功率變化率限制 (百分比/週期) |
| `pv_loss` | `float` | `0.0` | PV 系統損失 (kW)，計算時扣除 |
| `min_history` | `int` | `1` | 最少需要的歷史資料筆數 |

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | `PERIODIC` |
| 週期 | 900 秒 (預設，可自訂) |

## 執行流程

1. **前置條件檢查** — PVDataService 存在性
2. **歷史資料充足性檢查** — 資料筆數 >= min_history
3. **計算歷史平均功率** — `pv_service.get_average()`
4. **扣除系統損耗** — `max(average - pv_loss, 0.0)`
5. **套用斜率限制** — `rate_limit = capacity * ramp_rate / 100`
6. **Clamp 至允許範圍** — `last_p +/- rate_limit`

## 方法

| 方法 | 說明 |
|------|------|
| `execute(context)` | 計算平滑後的 P 目標 (Q 固定為 0) |
| `update_config(config)` | 動態更新配置 |
| `set_pv_service(pv_service)` | 設定/替換 PV 資料服務 |

## 程式碼範例

```python
from csp_lib.controller import PVSmoothStrategy, PVSmoothConfig, PVDataService

pv_service = PVDataService(max_history=300)
strategy = PVSmoothStrategy(
    PVSmoothConfig(capacity=1000, ramp_rate=10, pv_loss=5),
    pv_service=pv_service,
)
# Feed data externally
pv_service.append(current_pv_power)
```

## 動態參數化（v0.8.2）

透過 `RuntimeParameters` + `param_keys` 讓 EMS 在執行期即時覆蓋策略配置，無需重啟。

### 可動態化欄位

| `PVSmoothConfig` 欄位 | 說明 |
|----------------------|------|
| `capacity` | PV 系統容量 (kW) |
| `ramp_rate` | 功率變化率限制 (百分比/週期) |
| `pv_loss` | PV 系統損失 (kW) |
| `min_history` | 最少歷史資料筆數 |

### 建構參數（v0.8.2 新增）

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `params` | `RuntimeParameters \| None` | `None` | 動態參數來源；與 `param_keys` 同時提供或同時省略 |
| `param_keys` | `Mapping[str, str] \| None` | `None` | `{config 欄位名: runtime key}` 映射；未列欄位 fallback config 預設值 |
| `enabled_key` | `str \| None` | `None` | runtime 啟停旗標 key；falsy 時立即輸出 `Command(0, 0)`（安全降級） |

### `enabled_key` 行為

> [!note] PVSmooth 的 disabled 行為
> `enabled_key` 指向的 `params` 值為 falsy（0、`None`、`False`、`""`）時，策略**立即輸出 `Command(p_target=0, q_target=0)`**。這是主動停止 PV 輸出（PV 離線即停語義），而非保留上次命令。

### 範例

```python
from csp_lib.core import RuntimeParameters
from csp_lib.controller import PVSmoothStrategy, PVSmoothConfig

params = RuntimeParameters()
params.set("pv_capacity", 800.0)
params.set("pv_ramp", 8.0)
params.set("pv_enabled", 1)

strategy = PVSmoothStrategy(
    PVSmoothConfig(capacity=1000, ramp_rate=10),
    pv_service=pv_service,
    params=params,
    param_keys={"capacity": "pv_capacity", "ramp_rate": "pv_ramp"},
    enabled_key="pv_enabled",
)

# EMS 動態調整：
params.set("pv_capacity", 600.0)   # 下次 execute() 自動使用 600.0
params.set("pv_enabled", 0)        # 下次輸出 Command(0, 0)
```

---

## 相關連結

- [[PVDataService]] — 提供歷史功率資料的服務
- [[Strategy]] — 基礎類別
- [[Command]] — execute 回傳值
- [[StrategyContext]] — 使用 `last_command.p_target` 作為 ramp 基準
- [[RuntimeParameters]] — 執行期可變參數容器
