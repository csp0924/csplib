---
tags:
  - type/class
  - layer/modbus-server
  - status/complete
source: csp_lib/modbus_server/simulator/bms.py
created: 2026-04-05
updated: 2026-04-05
version: ">=0.6.2"
---

# BMSSimulator

> 電池管理系統模擬器，追蹤 SOC、電壓、溫度、電流與告警

`BMSSimulator` 模擬電池管理系統的物理行為，可獨立運作或透過 `MicrogridSimulator.link_pcs_bms()` 與 PCS 聯動——由 BMS 管理 SOC，並在每個 tick 同步回 PCS。

Sign convention：**正值 = 放電 (discharge)，負值 = 充電 (charge)**，與 PCS 一致。

---

## Quick Example

```python
from csp_lib.modbus_server.simulator.bms import BMSSimulator
from csp_lib.modbus_server.config import BMSSimConfig

# 建立 BMS（100 kWh，初始 SOC 80%）
bms = BMSSimulator(
    sim_config=BMSSimConfig(capacity_kwh=100.0, initial_soc=80.0),
)

# 模擬放電 50 kW，持續 1 秒
bms.update_power(power_kw=50.0, dt=1.0)

print(bms.get_value("soc"))          # SOC 略降
print(bms.get_value("temperature"))  # 溫度略升
print(bms.get_value("alarm_register"))  # 0 = 無告警
```

---

## BMSSimConfig

BMS 模擬器配置（frozen dataclass，含 `slots=True`）。

| 欄位 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `capacity_kwh` | `float` | `100.0` | 電池容量（kWh），必須 > 0 |
| `initial_soc` | `float` | `50.0` | 初始 SOC (%)，範圍 [0, 100] |
| `nominal_voltage` | `float` | `700.0` | 額定電壓（V），必須 > 0 |
| `cells_in_series` | `int` | `192` | 串聯電芯數，必須 > 0 |
| `min_cell_voltage` | `float` | `2.8` | 電芯最低電壓（V） |
| `max_cell_voltage` | `float` | `4.2` | 電芯最高電壓（V）；必須 > `min_cell_voltage` |
| `thermal_coefficient` | `float` | `0.01` | 熱係數（°C/kW），功率越大溫升越快 |
| `ambient_temperature` | `float` | `25.0` | 環境溫度（°C） |
| `cooling_rate` | `float` | `0.005` | 自然散熱速率（°C/s） |
| `charge_efficiency` | `float` | `0.95` | 充電效率 (0, 1]，影響充電時 SOC 增幅 |
| `tick_interval` | `float` | `1.0` | 模擬步長（秒），用於自主 `update()` |

> [!note] 驗證
> 所有欄位在建立時驗證；不合法值拋出 `ConfigurationError`。

---

## Register 佈局

`default_bms_config()` 產生以下 Modbus 點位（預設從 address 0 起始，所有浮點數使用 Float32 兩個 register）：

| 點位名稱 | 型別 | 預設值 | 說明 |
|----------|------|--------|------|
| `soc` | `Float32` | `50.0` | 電量 (%) |
| `soh` | `Float32` | `100.0` | 電池健康度 (%) |
| `voltage` | `Float32` | `700.0` | Pack 電壓 (V)，由 SOC 線性插值 |
| `current` | `Float32` | `0.0` | 電流 (A)，正值 = 放電，負值 = 充電 |
| `temperature` | `Float32` | `25.0` | Pack 溫度 (°C) |
| `cell_voltage_min` | `Float32` | `3.5` | 最低電芯電壓 (V) |
| `cell_voltage_max` | `Float32` | `3.5` | 最高電芯電壓 (V) |
| `alarm_register` | `UInt16` | `0` | 告警位元遮罩（見下表） |
| `status` | `UInt16` | `0` | 運行狀態：0=standby, 1=charging, 2=discharging |

---

## 告警位元定義

`alarm_register` 為位元遮罩，每個 bit 代表一種告警：

| Bit | 告警類型 | 觸發條件 |
|-----|----------|----------|
| 0 | 過溫 (Over Temperature) | `temperature > 55.0 °C` |
| 1 | 欠壓 (Under Voltage) | `cell_voltage_min < 2.5 V` |
| 2 | 過壓 (Over Voltage) | `cell_voltage_max > 4.25 V` |
| 3 | SOC 過低 (SOC Low) | `soc < 5.0 %` |
| 4 | SOC 過高 (SOC High) | `soc > 95.0 %` |

---

## update_power() 更新流程

`update_power(power_kw, dt)` 是核心物理模擬方法，每次呼叫依序執行：

```
1. SOC 更新
   delta_soc = -power_kw * dt / (capacity_kwh * 3600) * 100
   充電時（power_kw < 0）: delta_soc *= charge_efficiency
   SOC 限制在 [0, 100]

2. 電壓更新（基於 SOC 線性插值）
   v_min = min_cell_voltage × cells_in_series
   v_max = max_cell_voltage × cells_in_series
   pack_voltage = v_min + (v_max - v_min) × soc / 100
   cell_voltage_min = cell_avg - 0.02
   cell_voltage_max = cell_avg + 0.02

3. 電流計算
   current = power_kw × 1000 / pack_voltage

4. 溫度更新
   heating = thermal_coefficient × |power_kw| × dt
   cooling = cooling_rate × max(0, T - T_ambient) × dt
   temperature += heating - cooling

5. 狀態更新
   |power| < 0.1 → standby(0)
   power < 0 → charging(1)
   power > 0 → discharging(2)

6. 告警檢查（更新 alarm_register 位元遮罩）
```

---

## PCS-BMS 聯動整合

透過 `MicrogridSimulator` 建立 PCS-BMS 連結後，每個 tick BMS 接管 PCS 的 SOC 管理：

```python
from csp_lib.modbus_server import MicrogridSimulator, MicrogridConfig
from csp_lib.modbus_server.simulator.bms import BMSSimulator
from csp_lib.modbus_server.simulator.pcs import PCSSimulator
from csp_lib.modbus_server.config import BMSSimConfig, PCSSimConfig
from csp_lib.modbus_server.simulator.bms import default_bms_config
from csp_lib.modbus_server.simulator.pcs import default_pcs_config

# 建立 PCS 與 BMS（相同容量）
pcs = PCSSimulator(
    default_pcs_config("pcs_1", unit_id=1),
    PCSSimConfig(capacity_kwh=200.0),
)
bms = BMSSimulator(
    default_bms_config("bms_1", unit_id=20),
    BMSSimConfig(capacity_kwh=200.0, initial_soc=60.0),
)

# 組裝微電網
microgrid = MicrogridSimulator(MicrogridConfig())
microgrid.add_pcs(pcs)
microgrid.add_bms(bms)
microgrid.link_pcs_bms("pcs_1", "bms_1")

# 每個 tick：BMS 根據 PCS 的 p_actual 計算 SOC，再同步回 PCS
await microgrid.update(tick_interval=1.0)
```

聯動後的 tick 順序（Step 5 內）：

```
PCS.update() → p_actual 更新（setpoint ramp）
  ↓
BMS.update_power(p_actual, dt) → SOC/電壓/溫度/告警更新
  ↓
PCS.set_value("soc", bms.soc) → PCS 的 SOC 讀數由 BMS 接管
```

> [!note] 未連結 PCS 的 SOC
> 沒有連結 BMS 的 PCS 仍使用內建 `update_soc()` 方法（基於 PCSSimConfig.capacity_kwh 計算），行為與 v0.6.1 以前相同。

---

## API Reference

### 建構子

```python
BMSSimulator(
    config: SimulatedDeviceConfig | None = None,
    sim_config: BMSSimConfig | None = None,
    capacity_kwh: float = 100.0,
    initial_soc: float = 50.0,
    nominal_voltage: float = 700.0,
    cells_in_series: int = 192,
    min_cell_voltage: float = 2.8,
    max_cell_voltage: float = 4.2,
    thermal_coefficient: float = 0.01,
    ambient_temperature: float = 25.0,
    cooling_rate: float = 0.005,
    charge_efficiency: float = 0.95,
    tick_interval: float = 1.0,
) -> None
```

- `config` 為 `None` 時，自動使用 `default_bms_config()` 產生預設 Register 佈局。
- `sim_config` 為 `None` 時，從個別關鍵字參數建立 `BMSSimConfig`。
- 同時傳入 `sim_config` 與個別參數時，`sim_config` 優先。

### 方法

| 方法 | 簽名 | 說明 |
|------|------|------|
| `update_power()` | `(power_kw: float, dt: float) → None` | 根據外部功率更新 BMS 狀態（由 MicrogridSimulator 呼叫） |
| `update()` | `async () → None` | 自主更新：自然散熱 + 告警檢查（無外部功率輸入時） |

### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `capacity_kwh` | `float` | 電池容量（kWh） |
| `device_id` | `str` | 設備識別碼（繼承自 `BaseDeviceSimulator`） |

### 輔助函式

```python
from csp_lib.modbus_server.simulator.bms import default_bms_config

config = default_bms_config(
    device_id="bms_1",   # 預設
    unit_id=20,          # 預設
    base_address=0,      # 預設
) -> SimulatedDeviceConfig
```

---

## Gotchas / Tips

- **`update_power()` 是同步方法**，而 `update()` 是非同步方法。`MicrogridSimulator` 在 Step 5 中以同步方式呼叫 `update_power()`，`update()` 只在無 PCS 連結的獨立 BMS 場景使用。
- **SOC 邊界**：SOC 強制限制在 [0, 100]，不會因持續充放電而溢出。
- **`soh` 欄位不會自動更新**：`BMSSimulator` 目前不實作 SOH 劣化模型，`soh` 維持初始值 100.0，如需模擬需手動呼叫 `set_value("soh", ...)`。
- **告警為純模擬用途**：`alarm_register` 只影響 Modbus register 讀數，不會觸發 `csp_lib` 的告警系統（需透過 `AsyncModbusDevice` 層整合）。

---

## 相關頁面

- [[MicrogridSimulator]] — `add_bms()` 與 `link_pcs_bms()` 說明
- [[PCSSimulator]] — PCS 模擬器（與 BMS 聯動的對象）
- [[Device Interconnection]] — 多電表路由、設備連結架構
- [[_MOC Modbus Server]] — 模組總覽
