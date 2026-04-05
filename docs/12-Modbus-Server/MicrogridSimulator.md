---
tags:
  - type/class
  - layer/modbus-server
  - status/complete
source: csp_lib/modbus_server/microgrid.py
created: 2026-02-17
updated: 2026-04-05
version: ">=0.6.2"
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
| `add_meter(meter, meter_id=None)` | 新增電表（v0.6.2）；第一個自動成為 default |
| `get_meter(meter_id)` | 取得指定 ID 電表（v0.6.2） |
| `set_meter(meter)` | 向後相容：等同 `add_meter()` 並設為 default |
| `add_pcs(pcs)` | 加入 PCS 模擬器 |
| `add_solar(solar)` | 加入太陽能模擬器 |
| `add_load(load)` | 加入負載模擬器 |
| `add_generator(gen)` | 加入發電機模擬器 |
| `add_bms(bms)` | 加入 BMS 模擬器（v0.6.2）；`device_id` 重複時拋 `ConfigurationError` |
| `link_pcs_bms(pcs_id, bms_id)` | 連結 PCS 與 BMS（v0.6.2）；之後由 BMS 管理該 PCS 的 SOC |
| `add_device_link(link)` | 新增設備到電表的功率路由（v0.6.2） |
| `add_meter_aggregation(agg)` | 新增電表聚合樹（v0.6.2） |

---

## 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `config` | `MicrogridConfig` | 微電網配置 |
| `meter` | `PowerMeterSimulator \| None` | 向後相容：回傳 default 電表 |
| `meters` | `dict[str, PowerMeterSimulator]` | 所有已註冊電表的唯讀副本（v0.6.2） |
| `accumulated_energy` | `float` | 累積電量（kWh） |
| `all_simulators` | `list[BaseDeviceSimulator]` | 所有已註冊的模擬器 |

---

## Tick 更新順序

`update(tick_interval)` 每次 tick 依序執行：

1. **系統電壓/頻率** -- 標稱值 + 隨機擾動
2. **更新 Solar** -- 產出功率，注入系統 V/F
3. **更新 Generator** -- 產出功率
4. **更新 Load** -- 消耗功率，注入系統 V/F
5. **更新 PCS** -- setpoint ramp + SOC 計算，注入系統 V/F；若有 BMS 連結，由 BMS 計算 SOC 並同步回 PCS（v0.6.2）
6. **重置連結電表累加器**（v0.6.2）
7. **設備連結** -- device.P × (1 - loss_factor) → target_meter（v0.6.2）；未連結設備淨功率 → default 電表
8. **電表聚合樹** -- 拓撲排序後累加（v0.6.2）
9. **更新能量累積** -- 積分 P * dt / 3600（所有電表）

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
- [[Device Interconnection]] -- 多電表配置、DeviceLinkConfig、MeterAggregationConfig（v0.6.2）
- [[Simulators]] -- 內建設備模擬器
- [[_MOC Modbus Server]] -- 模組總覽
