---
tags:
  - type/class
  - layer/modbus
  - status/complete
source: csp_lib/modbus/clients/
created: 2026-02-17
---

# Clients

## Modbus 非同步客戶端 (`csp_lib.modbus.clients`)

提供基於 pymodbus 的非同步 Modbus 客戶端實作。所有客戶端皆繼承自 `AsyncModbusClientBase` 抽象介面，支援 `async with` Context Manager 用法。

> [!info] 版本相容性
> 支援 pymodbus >= 3.0.0，自動適配 3.10.0+ API 變更（`slave` -> `device_id`）。

---

## 客戶端一覽表

| 客戶端 | 設定類別 | 說明 | 使用時機 |
|--------|---------|------|---------|
| `PymodbusTcpClient` | `ModbusTcpConfig` | TCP 客戶端，獨立連線 | 一對一設備連線，支援多工 |
| `PymodbusRtuClient` | `ModbusRtuConfig` | RTU 客戶端，含 `asyncio.Lock` | Serial port 連線 |
| `SharedPymodbusTcpClient` | `ModbusTcpConfig` | 共享 TCP 客戶端，共用連線 + Lock | 多設備共用同一 TCP-RS485 轉換器 |

---

## PymodbusTcpClient

標準 TCP 客戶端，每個實例建立獨立的 TCP 連線。適用於設備直接透過乙太網路連接的場景。

**特性：**
- 每個實例獨立連線
- 支援並行讀寫（多工）
- 不重試（`retries=0`）

---

## PymodbusRtuClient

RTU 串口客戶端，採用 **Singleton per port** 模式。同一串口的多個實例共用：
- 同一個 pymodbus `AsyncModbusSerialClient`
- 同一個 `asyncio.Lock`（確保串列通訊原子性）

**特性：**
- 自動參考計數管理
- 最後一個使用者斷線時自動關閉串口
- 透過 Lock 序列化所有讀寫操作

---

## SharedPymodbusTcpClient

專為 **TCP-RS485 轉換器**設計的共享客戶端。同一 `host:port` 的多個設備共用：
- 同一個 TCP 連線
- 同一個 `asyncio.Lock`（確保 RS485 匯流排不衝突）

**與 PymodbusTcpClient 的差異：**

| 特性 | `PymodbusTcpClient` | `SharedPymodbusTcpClient` |
|------|:-------------------:|:-------------------------:|
| 連線模式 | 獨立連線 | 共享連線 |
| 並行存取 | 支援多工 | 序列化（Lock） |
| 適用場景 | 直接乙太網路 | TCP-RS485 轉換器 |

---

## 共用介面 (AsyncModbusClientBase)

所有客戶端皆實作以下抽象方法：

### 連線管理

| 方法 | 說明 |
|------|------|
| `connect()` | 建立連線 |
| `disconnect()` | 斷開連線 |
| `is_connected()` | 檢查連線狀態 |

### 讀取操作

| 方法 | 功能碼 | 說明 |
|------|:------:|------|
| `read_coils(address, count, unit_id)` | 0x01 | 讀取線圈狀態 |
| `read_discrete_inputs(address, count, unit_id)` | 0x02 | 讀取離散輸入 |
| `read_holding_registers(address, count, unit_id)` | 0x03 | 讀取保持暫存器 |
| `read_input_registers(address, count, unit_id)` | 0x04 | 讀取輸入暫存器 |

### 寫入操作

| 方法 | 功能碼 | 說明 |
|------|:------:|------|
| `write_single_coil(address, value, unit_id)` | 0x05 | 寫入單一線圈 |
| `write_single_register(address, value, unit_id)` | 0x06 | 寫入單一暫存器 |
| `write_multiple_coils(address, values, unit_id)` | 0x0F | 寫入多個線圈 |
| `write_multiple_registers(address, values, unit_id)` | 0x10 | 寫入多個暫存器 |

> [!note]
> 所有讀寫方法皆接受 `unit_id` 參數（預設 `1`），由呼叫端（設備層級）提供，讓多個設備可共用同一個 Client 連線。

---

## 使用範例

### 基本連線與讀取

```python
from csp_lib.modbus import PymodbusTcpClient, ModbusTcpConfig

client = PymodbusTcpClient(ModbusTcpConfig(host="192.168.1.100"))
await client.connect()
registers = await client.read_holding_registers(0, 2, unit_id=1)
await client.disconnect()
```

### 使用 Context Manager

```python
from csp_lib.modbus import PymodbusTcpClient, ModbusTcpConfig

config = ModbusTcpConfig(host="192.168.1.100")
async with PymodbusTcpClient(config) as client:
    registers = await client.read_holding_registers(0, 10)
```

### RTU 客戶端

```python
from csp_lib.modbus import PymodbusRtuClient, ModbusRtuConfig

config = ModbusRtuConfig(port="COM1")
async with PymodbusRtuClient(config) as client:
    registers = await client.read_holding_registers(0, 10, unit_id=1)
```

### 共享 TCP 客戶端（TCP-RS485 轉換器）

```python
from csp_lib.modbus import SharedPymodbusTcpClient, ModbusTcpConfig

config = ModbusTcpConfig(host="192.168.1.12")

# 多個設備共用同一連線
async with SharedPymodbusTcpClient(config) as client:
    # 讀取設備 1
    regs_dev1 = await client.read_holding_registers(0, 10, unit_id=1)
    # 讀取設備 2
    regs_dev2 = await client.read_holding_registers(0, 10, unit_id=2)
```

---

## 相關頁面

- [[Configuration]] — 連線設定類別（ModbusTcpConfig、ModbusRtuConfig）
- [[_MOC Modbus]] — Modbus 模組總覽
