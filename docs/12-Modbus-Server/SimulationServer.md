---
tags:
  - type/class
  - layer/modbus-server
  - status/complete
source: csp_lib/modbus_server/server.py
created: 2026-02-17
---

# SimulationServer

> Modbus TCP 模擬伺服器

`SimulationServer` 封裝 pymodbus TCP server，繼承自 `AsyncLifecycleMixin`，提供多設備模擬器管理、定期 tick loop、以及 [[MicrogridSimulator]] 聯動模式。

---

## ServerConfig

伺服器配置（frozen dataclass）：

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `host` | `str` | `"127.0.0.1"` | 監聽位址 |
| `port` | `int` | `5020` | 監聽埠號 |
| `tick_interval` | `float` | `1.0` | tick loop 間隔（秒） |

---

## SimulatedPoint

模擬點位定義（frozen dataclass）：

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `name` | `str` | (必填) | 點位名稱 |
| `address` | `int` | (必填) | Register 起始位址 |
| `data_type` | `ModbusDataType` | (必填) | Modbus 資料型別 |
| `initial_value` | `Any` | `0` | 初始值 |
| `writable` | `bool` | `False` | 是否可寫入 |
| `byte_order` | `ByteOrder` | `BIG_ENDIAN` | 位元組順序 |
| `register_order` | `RegisterOrder` | `HIGH_FIRST` | 暫存器順序 |

---

## SimulatedDeviceConfig

模擬設備配置（frozen dataclass）：

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `device_id` | `str` | (必填) | 設備識別碼 |
| `unit_id` | `int` | (必填) | Modbus slave ID (1-247) |
| `points` | `tuple[SimulatedPoint, ...]` | `()` | 點位定義 |
| `alarm_points` | `tuple[AlarmPointConfig, ...]` | `()` | 告警點位配置 |
| `update_interval` | `float` | `1.0` | 更新間隔（秒） |

---

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `config` | `ServerConfig \| None` | `None` | 伺服器配置（預設使用 `ServerConfig()`） |

---

## 方法

| 方法 | 說明 |
|------|------|
| `add_simulator(simulator)` | 註冊設備模擬器（per unit_id） |
| `set_microgrid(microgrid)` | 設定 MicrogridSimulator 聯動模式 |
| `start()` | 啟動 pymodbus TCP server 與 tick loop |
| `stop()` | 停止 server |
| `serve()` | 持續運行直到被停止 |

---

## SimulatorDataBlock

自訂 Modbus DataBlock，橋接 pymodbus datastore 與 `RegisterBlock`。寫入時偵測 writable points 並呼叫 `simulator.on_write()`，讓模擬器感知外部寫入事件。

---

## 程式碼範例

```python
from csp_lib.modbus_server import (
    SimulatedPoint, SimulatedDeviceConfig, ServerConfig,
    SimulationServer,
)
from csp_lib.modbus import Float32, UInt16

# 定義模擬點位
points = (
    SimulatedPoint(name="power", address=0, data_type=Float32(), writable=True),
    SimulatedPoint(name="status", address=2, data_type=UInt16(), initial_value=1),
)

# 設備配置
device_config = SimulatedDeviceConfig(
    device_id="sim_pcs",
    unit_id=1,
    points=points,
    update_interval=1.0,
)

# 伺服器配置
server_config = ServerConfig(host="0.0.0.0", port=5020)

# 啟動伺服器
server = SimulationServer(config=server_config)
server.add_simulator(pcs_sim)

async with server:
    await asyncio.Event().wait()
```

---

## 相關頁面

- [[MicrogridSimulator]] -- 微電網聯動模式
- [[Simulators]] -- 內建設備模擬器
- [[Behaviors]] -- 可組合行為模組
- [[_MOC Modbus Server]] -- 模組總覽
