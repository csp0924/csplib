---
tags:
  - type/config
  - layer/equipment
  - status/complete
source: csp_lib/equipment/device/config.py
---

# DeviceConfig

> 設備設定

`DeviceConfig` 是不可變的 frozen dataclass，定義 [[AsyncModbusDevice]] 的設定參數。建構時會自動驗證參數合法性，不合法則拋出 `ConfigurationError`。

---

## 參數

| 參數 | 型別 | 預設值 | 驗證規則 | 說明 |
|------|------|--------|----------|------|
| `device_id` | `str` | (必填) | 不可為空 | 設備唯一識別碼 |
| `unit_id` | `int` | `1` | 0-255 | Modbus 設備位址 (Slave ID) |
| `address_offset` | `int` | `0` | -- | 位址偏移（PLC 1-based 定址時設為 1） |
| `read_interval` | `float` | `1.0` | > 0 | 讀取間隔（秒） |
| `reconnect_interval` | `float` | `5.0` | -- | 重連間隔（秒） |
| `disconnect_threshold` | `int` | `5` | >= 1 | 連續失敗次數閾值，達到後視為斷線 |
| `max_concurrent_reads` | `int` | `1` | >= 0 | 最大並行讀取數（0 = 不限制） |

---

## 程式碼範例

```python
from csp_lib.equipment.device import DeviceConfig

# 標準 TCP 設備
config = DeviceConfig(
    device_id="inverter_001",
    unit_id=1,
    read_interval=1.0,
)

# PLC 1-based 定址
config = DeviceConfig(
    device_id="plc_001",
    unit_id=1,
    address_offset=1,  # 位址偏移 +1
)

# 高頻讀取 + 快速斷線偵測
config = DeviceConfig(
    device_id="sensor_001",
    unit_id=2,
    read_interval=0.5,
    disconnect_threshold=3,
)
```

---

## 相關頁面

- [[AsyncModbusDevice]] -- 核心設備類別
- [[_MOC Equipment]] -- 設備模組總覽
