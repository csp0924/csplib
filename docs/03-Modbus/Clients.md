---
tags:
  - type/class
  - layer/modbus
  - status/complete
source: csp_lib/modbus/clients/
created: 2026-02-17
updated: 2026-04-16
version: ">=0.7.2"
---

# Clients

## Modbus 非同步客戶端 (`csp_lib.modbus.clients`)

提供基於 pymodbus 的非同步 Modbus 客戶端實作。所有客戶端皆繼承自 `AsyncModbusClientBase` 抽象介面，支援 `async with` Context Manager 用法。

> [!info] 版本相容性
> 支援 pymodbus >= 3.0.0，自動適配 3.10.0+ API 變更（`slave` -> `device_id`）。

> [!info] pymodbus lazy import
> pymodbus 為 optional dependency（`csp0924_lib[modbus]`），客戶端類別使用模組層級 lazy import，僅在首次建立連線時才載入 pymodbus。伺服器端元件透過 `csp_lib.modbus._pymodbus` 模組統一管理 lazy import。

---

## Quick Example

```python
from csp_lib.modbus import PymodbusTcpClient, ModbusTcpConfig

config = ModbusTcpConfig(host="192.168.1.100")
async with PymodbusTcpClient(config) as client:
    registers = await client.read_holding_registers(0, 10, unit_id=1)
```

---

## 客戶端一覽表

| 客戶端 | 設定類別 | 說明 | 使用時機 |
|--------|---------|------|---------|
| [[PymodbusTcpClient]] | [[ModbusTcpConfig]] | TCP 客戶端，獨立連線 | 一對一設備連線，支援多工 |
| [[PymodbusRtuClient]] | [[ModbusRtuConfig]] | RTU 客戶端，含 [[ModbusRequestQueue]] | Serial port 連線 |
| [[SharedPymodbusTcpClient]] | [[ModbusTcpConfig]] | 共享 TCP 客戶端，共用連線 + [[ModbusRequestQueue]] | 多設備共用同一 TCP-RS485 轉換器 |

---

## PymodbusTcpClient

標準 TCP 客戶端，每個實例建立獨立的 TCP 連線。適用於設備直接透過乙太網路連接的場景。

**建構參數：**

| 參數 | 型別 | 說明 |
|------|------|------|
| `config` | `ModbusTcpConfig` | TCP 連線設定 |

**特性：**
- 每個實例獨立連線
- 支援並行讀寫（多工）
- 不重試（`retries=0`）

> [!note] v0.7.2 重複連線保護（BUG-006）
> `connect()` 以 `asyncio.Lock` 序列化所有併發呼叫，並於 lock 內以底層 `client.connected` 真實狀態決定是否執行連線動作。修復前：多個協程同時呼叫 `connect()` 會重複呼叫底層連線。網路掉線（`client.connected` 自動翻 False）後重連仍可正常運作，不被 sticky flag 卡死。

---

## PymodbusRtuClient

RTU 串口客戶端，採用 **Singleton per port** 模式。同一串口的多個實例共用：
- 同一個 pymodbus `AsyncModbusSerialClient`
- 同一個 [[ModbusRequestQueue]]（優先權排程 + 公平排程 + 斷路器）

> [!info] v0.4.2 新增
> RTU 客戶端改用 `ModbusRequestQueue` 取代 `asyncio.Lock`，提供優先權排程、round-robin 公平排程和 per-unit 斷路器。

**建構參數：**

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `config` | `ModbusRtuConfig` | *必填* | RTU 連線設定 |
| `queue_config` | `RequestQueueConfig \| None` | `None` | 請求佇列設定（`None` 使用預設值） |

**特性：**
- 自動參考計數管理
- 最後一個使用者斷線時自動停止佇列並關閉串口
- 透過 `ModbusRequestQueue` 序列化所有讀寫操作

---

## SharedPymodbusTcpClient

專為 **TCP-RS485 轉換器**設計的共享客戶端。同一 `host:port` 的多個設備共用：
- 同一個 TCP 連線
- 同一個 [[ModbusRequestQueue]]（優先權排程 + 公平排程 + 斷路器）

> [!info] v0.4.2 新增
> 共享 TCP 客戶端改用 `ModbusRequestQueue` 取代 `asyncio.Lock`，提供優先權排程、round-robin 公平排程和 per-unit 斷路器。

**建構參數：**

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `config` | `ModbusTcpConfig` | *必填* | TCP 連線設定 |
| `queue_config` | `RequestQueueConfig \| None` | `None` | 請求佇列設定（`None` 使用預設值） |

**與 PymodbusTcpClient 的差異：**

| 特性 | `PymodbusTcpClient` | `SharedPymodbusTcpClient` |
|------|:-------------------:|:-------------------------:|
| 連線模式 | 獨立連線 | 共享連線（Singleton per endpoint） |
| 並行存取 | 支援多工 | 序列化（`ModbusRequestQueue`） |
| 適用場景 | 直接乙太網路 | TCP-RS485 轉換器 |
| 斷路器 | 無 | 有（per unit_id） |

---

## 共用介面 (AsyncModbusClientBase)

所有客戶端皆實作以下抽象方法：

### 連線管理

| 方法 | 回傳型別 | 說明 |
|------|---------|------|
| `connect()` | `None` | 建立連線 |
| `disconnect()` | `None` | 斷開連線 |
| `is_connected()` | `bool` | 檢查連線狀態 |

### 讀取操作

| 方法 | 功能碼 | 回傳型別 | 說明 |
|------|:------:|---------|------|
| `read_coils(address, count, unit_id=1)` | 0x01 | `list[bool]` | 讀取線圈狀態 |
| `read_discrete_inputs(address, count, unit_id=1)` | 0x02 | `list[bool]` | 讀取離散輸入 |
| `read_holding_registers(address, count, unit_id=1)` | 0x03 | `list[int]` | 讀取保持暫存器 |
| `read_input_registers(address, count, unit_id=1)` | 0x04 | `list[int]` | 讀取輸入暫存器 |

### 寫入操作

| 方法 | 功能碼 | 回傳型別 | 說明 |
|------|:------:|---------|------|
| `write_single_coil(address, value, unit_id=1)` | 0x05 | `None` | 寫入單一線圈 |
| `write_single_register(address, value, unit_id=1)` | 0x06 | `None` | 寫入單一暫存器 |
| `write_multiple_coils(address, values, unit_id=1)` | 0x0F | `None` | 寫入多個線圈 |
| `write_multiple_registers(address, values, unit_id=1)` | 0x10 | `None` | 寫入多個暫存器 |

> [!note]
> 所有讀寫方法皆接受 `unit_id` 參數（預設 `1`），由呼叫端（設備層級）提供，讓多個設備可共用同一個 Client 連線。讀寫失敗時拋出 [[ModbusError]]，攜帶 `address`、`unit_id`、`function_code` 上下文資訊。

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
from csp_lib.modbus import PymodbusRtuClient, ModbusRtuConfig, RequestQueueConfig

config = ModbusRtuConfig(port="COM1")
queue_config = RequestQueueConfig(default_timeout=3.0)

async with PymodbusRtuClient(config, queue_config=queue_config) as client:
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

## ModbusRequestQueue

> [!info] v0.4.2 新增

[[ModbusRequestQueue]] 提供請求佇列 + 背景 Worker 架構，取代 `asyncio.Lock`，適用於需要精確排程和多設備公平排程的場景。由 `PymodbusRtuClient` 和 `SharedPymodbusTcpClient` 內部使用。

> [!note] 此類別屬於進階用法，一般情況下由客戶端內部使用，不需要直接操作。

### RequestQueueConfig

> [!info] v0.4.2 新增

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `default_timeout` | `float` | `5.0` | 每個請求的預設逾時（秒） |
| `circuit_breaker_threshold` | `int` | `5` | 連續失敗次數達到此值後觸發斷路器 |
| `circuit_breaker_cooldown` | `float` | `30.0` | 斷路器開啟後的冷卻時間（秒） |
| `max_queue_size` | `int` | `1000` | 佇列最大容量（0 = 無限制） |
| `drain_timeout` | `float` | `10.0` | 關閉時等待佇列排空的逾時（秒） |

### RequestPriority

> [!info] v0.4.2 新增

| 值 | 說明 |
|----|------|
| `WRITE = 0` | 寫入請求（較高優先權） |
| `READ = 1` | 讀取請求（較低優先權） |

### ModbusRequestQueue API

| 方法 | 說明 |
|------|------|
| `start()` | 啟動背景 worker |
| `stop()` | 停止背景 worker 並排空佇列 |
| `submit(unit_id, priority, coroutine_factory, timeout=None)` | 提交請求到佇列 |
| `total_size` | 佇列中的總請求數（唯讀屬性） |

#### submit() 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `unit_id` | `int` | 設備位址 |
| `priority` | `RequestPriority` | 請求優先權 |
| `coroutine_factory` | `Callable[[], Coroutine]` | 產生 coroutine 的工廠函式 |
| `timeout` | `float \| None` | 此請求的逾時（`None` 使用 `default_timeout`） |

#### submit() 例外

| 例外 | 觸發條件 |
|------|---------|
| [[ModbusQueueFullError]] | 佇列已達 `max_queue_size` |
| [[ModbusCircuitBreakerError]] | 斷路器開啟（該 unit_id 連續失敗達閾值） |
| [[ModbusError]] | 佇列未啟動 |
| `asyncio.TimeoutError` | 請求逾時 |

### UnitCircuitBreaker

每個 `unit_id` 獨立維護一個斷路器，繼承自 Core 層的 `CircuitBreaker`。

狀態轉換：
- `CLOSED` → 連續失敗達閾值 → `OPEN`
- `OPEN` → 冷卻時間過後 → `HALF_OPEN`
- `HALF_OPEN` → 成功 → `CLOSED`
- `HALF_OPEN` → 失敗 → `OPEN`

> [!note] 向後相容
> `CircuitBreakerState` 為 `CircuitState` 的別名，保留向後相容。

### 排程策略

`ModbusRequestQueue` 採用**優先權 + Round-Robin** 公平排程：

1. 掃描所有 unit_id（round-robin 順序）
2. 跳過斷路器 OPEN 的 unit
3. 選擇最高優先權的請求；同優先權時以 round-robin 位置決勝
4. 彈出請求，已服務的 unit 移到 deque 尾端

---

## pymodbus 版本相容層

`csp_lib.modbus.clients.compat` 模組提供 pymodbus 版本偵測與參數適配：

| 函式 | 說明 |
|------|------|
| `is_new_api()` | 回傳 `True` 若 pymodbus >= 3.10.0 |
| `slave_kwarg(unit_id)` | 回傳 `{"device_id": unit_id}` 或 `{"slave": unit_id}`（依版本） |

> [!note] 內部 API
> `compat` 模組為內部使用，一般使用者不需要直接呼叫。

---

## 相關頁面

- [[Configuration]] — 連線設定類別（[[ModbusTcpConfig]]、[[ModbusRtuConfig]]）
- [[Exceptions]] — [[ModbusQueueFullError]]、[[ModbusCircuitBreakerError]]
- [[_MOC Modbus]] — Modbus 模組總覽
