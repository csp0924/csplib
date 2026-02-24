---
tags:
  - type/class
  - layer/modbus-server
  - status/complete
source: csp_lib/modbus_server/microgrid.py
created: 2026-02-17
---

# MicrogridSimulator

> 微電網功率平衡協調器

`MicrogridSimulator` 管理所有設備模擬器之間的物理關係，協調功率平衡、SOC 追蹤、電壓/頻率同步與累積電量計算。

---

## MicrogridConfig

微電網聯動配置（frozen dataclass）：

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `grid_voltage` | `float` | `380.0` | 電網標稱電壓（V） |
| `grid_frequency` | `float` | `60.0` | 電網標稱頻率（Hz） |
| `voltage_noise` | `float` | `2.0` | 電壓擾動範圍（+/- V） |
| `frequency_noise` | `float` | `0.02` | 頻率擾動範圍（+/- Hz） |

---

## 功率平衡公式

```
P_grid = P_load - P_solar - P_pcs - P_generator
```

- 正值 = 從電網取電
- 負值 = 輸出到電網

### Sign Convention

| 設備 | 正號意義 | 負號意義 |
|------|----------|----------|
| PCS | 放電 (discharge) | 充電 (charge) |
| Solar / Generator | 發電量（恆正） | -- |
| Load | 用電量（恆正） | -- |
| Meter | 依 `power_sign` 配置決定 | -- |

---

## 設備註冊方法

| 方法 | 說明 |
|------|------|
| `set_meter(meter)` | 設定電表模擬器 |
| `add_pcs(pcs)` | 加入 PCS 模擬器 |
| `add_solar(solar)` | 加入太陽能模擬器 |
| `add_load(load)` | 加入負載模擬器 |
| `add_generator(gen)` | 加入發電機模擬器 |

---

## 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `config` | `MicrogridConfig` | 微電網配置 |
| `meter` | `PowerMeterSimulator \| None` | 電表模擬器 |
| `accumulated_energy` | `float` | 累積電量（kWh） |
| `all_simulators` | `list[BaseDeviceSimulator]` | 所有已註冊的模擬器 |

---

## Tick 更新順序

`update(tick_interval)` 每次 tick 依序執行：

1. **系統電壓/頻率** -- 標稱值 + 隨機擾動
2. **更新 Solar** -- 產出功率，注入系統 V/F
3. **更新 Generator** -- 產出功率
4. **更新 Load** -- 消耗功率，注入系統 V/F
5. **更新 PCS** -- setpoint ramp + SOC 計算，注入系統 V/F
6. **聯動更新 Meter** -- 計算淨功率流 (P_grid)
7. **更新能量累積** -- 積分 P * dt / 3600

---

## 程式碼範例

```python
from csp_lib.modbus_server import MicrogridSimulator, MicrogridConfig

microgrid = MicrogridSimulator(MicrogridConfig(
    grid_voltage=380.0,
    grid_frequency=60.0,
))

microgrid.add_solar(solar_sim)
microgrid.add_pcs(pcs_sim)
microgrid.add_load(load_sim)
microgrid.set_meter(meter_sim)

# 搭配 SimulationServer 使用
server.set_microgrid(microgrid)
```

---

## 相關頁面

- [[SimulationServer]] -- 使用 `set_microgrid()` 啟用聯動模式
- [[Simulators]] -- 內建設備模擬器
- [[_MOC Modbus Server]] -- 模組總覽
