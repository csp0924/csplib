---
tags:
  - type/config
  - layer/modbus
  - status/complete
source: csp_lib/modbus/config.py
created: 2026-02-17
---

# Configuration

## Modbus 連線設定 (`csp_lib.modbus.config`)

提供 TCP 與 RTU 模式的連線設定類別，皆使用 `frozen dataclass` 確保設定建立後不可變。

> [!note] unit_id 說明
> `unit_id`（Slave ID）已移至設備層級（`DeviceConfig`），讓多個設備可共用同一個 Client 連線。

---

## ModbusTcpConfig

Modbus TCP/IP 連線設定。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `host` | `str` | *必填* | 目標主機位址 |
| `port` | `int` | `502` | 連接埠號（1-65535） |
| `timeout` | `float` | `0.5` | 通訊逾時秒數（須為正數） |
| `byte_order` | `ByteOrder` | `BIG_ENDIAN` | 位元組順序 |
| `register_order` | `RegisterOrder` | `HIGH_FIRST` | 暫存器順序 |

### 驗證規則

- `host` 不可為空
- `port` 必須在 1-65535 範圍內
- `timeout` 必須為正數

### 使用範例

```python
from csp_lib.modbus import ModbusTcpConfig

# 基本用法
tcp_config = ModbusTcpConfig(host="192.168.1.100", port=502)

# 自訂逾時
tcp_config = ModbusTcpConfig(
    host="192.168.1.100",
    port=502,
    timeout=1.0,
)
```

---

## ModbusRtuConfig

Modbus RTU 串口連線設定。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `port` | `str` | *必填* | 串口名稱（如 `"COM1"`、`"/dev/ttyUSB0"`） |
| `baudrate` | `int` | `9600` | 鮑率（須為正整數） |
| `parity` | `Parity` | `NONE` | 校驗位元 |
| `stopbits` | `int` | `1` | 停止位元數（1 或 2） |
| `bytesize` | `int` | `8` | 資料位元數（5、6、7 或 8） |
| `timeout` | `float` | `0.5` | 通訊逾時秒數（須為正數） |
| `byte_order` | `ByteOrder` | `BIG_ENDIAN` | 位元組順序 |
| `register_order` | `RegisterOrder` | `HIGH_FIRST` | 暫存器順序 |

### 驗證規則

- `port` 不可為空
- `baudrate` 必須為正整數
- `stopbits` 必須為 1 或 2
- `bytesize` 必須為 5、6、7 或 8
- `timeout` 必須為正數

### 使用範例

```python
from csp_lib.modbus import ModbusRtuConfig, Parity

# 基本用法
rtu_config = ModbusRtuConfig(port="COM1", baudrate=9600)

# 完整設定
rtu_config = ModbusRtuConfig(
    port="/dev/ttyUSB0",
    baudrate=19200,
    parity=Parity.EVEN,
    stopbits=1,
    bytesize=8,
    timeout=1.0,
)
```

---

## 相關頁面

- [[Clients]] — 使用設定類別建立非同步客戶端
- [[_MOC Modbus]] — Modbus 模組總覽
