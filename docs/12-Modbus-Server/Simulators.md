---
tags:
  - type/class
  - layer/modbus-server
  - status/complete
source: csp_lib/modbus_server/simulator/
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
---

# Simulators

> 內建設備模擬器

所有模擬器繼承自 `BaseDeviceSimulator`，提供 register block 管理、值操作、寫入回調等共用邏輯。子類實作 `update()` 方法定義模擬行為。

---

## BaseDeviceSimulator

設備模擬器抽象基類（`csp_lib/modbus_server/simulator/base.py`）。

### 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `config` | `SimulatedDeviceConfig` | 模擬設備配置 |

### 方法

| 方法 | 說明 |
|------|------|
| `set_value(name, value)` | 設定 point 的值（同步更新 register block） |
| `get_value(name)` | 取得 point 的值 |
| `on_write(name, old_value, new_value)` | Client 寫入回調（子類可覆寫） |
| `update()` | 模擬更新（`@abstractmethod`，由 tick loop 定期呼叫） |
| `reset()` | 重置到初始狀態 |

### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備識別碼 |
| `unit_id` | `int` | Modbus slave ID |
| `config` | `SimulatedDeviceConfig` | 設備配置 |
| `register_block` | `RegisterBlock` | 暫存器區塊 |

---

## 內建模擬器一覽

| 模擬器 | 來源檔案 | 說明 |
|--------|----------|------|
| `SolarSimulator` | `simulator/solar.py` | 太陽能發電模擬（日照曲線） |
| `GeneratorSimulator` | `simulator/generator.py` | 發電機模擬 |
| `LoadSimulator` | `simulator/load.py` | 負載模擬 |
| `PCSSimulator` | `simulator/pcs.py` | 儲能系統 PCS 模擬（含 SOC 追蹤） |
| `PowerMeterSimulator` | `simulator/power_meter.py` | 電表模擬（淨功率量測） |

---

## 模擬器專用配置

各模擬器有各自的配置 dataclass（均為 frozen）：

### PCSSimConfig

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `capacity_kwh` | `float` | `100.0` | 電池容量（kWh） |
| `p_ramp_rate` | `float` | `100.0` | 有功功率斜率（kW/s） |
| `q_ramp_rate` | `float` | `100.0` | 無功功率斜率（kVar/s） |
| `tick_interval` | `float` | `1.0` | 模擬更新間隔（秒） |

### SolarSimConfig

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `efficiency` | `float` | `0.95` | DC -> AC 轉換效率（0~1） |
| `power_noise` | `float` | `0.5` | 功率擾動振幅（kW） |
| `tick_interval` | `float` | `1.0` | 模擬更新間隔（秒） |

### GeneratorSimConfig

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `startup_delay` | `float` | `5.0` | 啟動延遲（秒） |
| `ramp_rate` | `float` | `50.0` | 功率斜率（kW/s） |
| `shutdown_delay` | `float` | `3.0` | 停機延遲（秒） |
| `rated_rpm` | `float` | `1800.0` | 額定轉速（RPM） |
| `power_factor` | `float` | `0.8` | 功率因數（0~1） |
| `tick_interval` | `float` | `1.0` | 模擬更新間隔（秒） |

### LoadSimConfig

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `controllability` | `ControllabilityMode` | `CONTROLLABLE` | 可控性模式 |
| `power_factor` | `float` | `0.9` | 功率因數（0~1） |
| `ramp_rate` | `float` | `50.0` | 功率斜率（kW/s） |
| `base_load` | `float` | `0.0` | 基礎負載（kW） |
| `load_noise` | `float` | `2.0` | 負載擾動振幅（kW） |
| `tick_interval` | `float` | `1.0` | 模擬更新間隔（秒） |

### PowerMeterSimConfig

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `power_sign` | `float` | `1.0` | 功率正負號配置（+1.0 或 -1.0） |
| `voltage_noise` | `float` | `2.0` | 電壓擾動振幅（V） |
| `frequency_noise` | `float` | `0.02` | 頻率擾動振幅（Hz） |

### ControllabilityMode

| 值 | 說明 |
|----|------|
| `CONTROLLABLE` | 回應 setpoint 寫入 |
| `UNCONTROLLABLE` | 忽略寫入，自行變化 |

---

## 模擬器與 MicrogridSimulator 的關係

在 [[MicrogridSimulator]] 聯動模式下，各模擬器的 `update()` 由 microgrid 統一呼叫，並注入系統電壓/頻率：

```
MicrogridSimulator.update()
  ├── SolarSimulator.update()     ← 注入 ac_voltage, frequency
  ├── GeneratorSimulator.update()
  ├── LoadSimulator.update()      ← 注入 voltage, frequency
  ├── PCSSimulator.update()       ← 注入 voltage, frequency + SOC 更新
  └── PowerMeterSimulator         ← 接收淨功率 (P_grid)
```

---

## 相關頁面

- [[SimulationServer]] -- 模擬伺服器（管理模擬器生命週期）
- [[MicrogridSimulator]] -- 微電網功率平衡
- [[Behaviors]] -- 可組合行為模組
- [[_MOC Modbus Server]] -- 模組總覽
