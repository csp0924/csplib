---
tags:
  - type/class
  - layer/modbus-server
  - status/complete
source: csp_lib/modbus_server/simulator/
created: 2026-02-17
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
