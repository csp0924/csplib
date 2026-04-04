---
tags:
  - type/class
  - layer/modbus
  - status/complete
source: csp_lib/modbus/exceptions.py
created: 2026-02-17
updated: 2026-04-04
version: 0.6.0
---

# Exceptions

## Modbus 例外類別 (`csp_lib.modbus.exceptions`)

定義 Modbus 模組專用的例外類別階層，方便統一捕捉與細粒度錯誤處理。

---

## Quick Example

```python
from csp_lib.modbus import ModbusError, ModbusCircuitBreakerError

try:
    registers = await client.read_holding_registers(0, 10, unit_id=1)
except ModbusCircuitBreakerError as e:
    print(f"斷路器開啟: unit_id={e.unit_id}")
except ModbusError as e:
    print(f"Modbus 操作失敗: {e} (addr={e.address}, unit={e.unit_id})")
```

---

## 繼承結構

```
Exception
└── ModbusError (基礎例外)
    ├── ModbusEncodeError (編碼錯誤)
    ├── ModbusDecodeError (解碼錯誤)
    ├── ModbusConfigError (設定錯誤)
    ├── ModbusCircuitBreakerError (斷路器開啟)    # v0.4.2 新增
    └── ModbusQueueFullError (請求佇列已滿)       # v0.4.2 新增
```

---

## ModbusError

所有 Modbus 相關例外的父類別，方便統一捕捉。

> [!info] v0.5.1 變更
> `ModbusError` 新增 `address`、`unit_id`、`function_code` 三個 keyword-only 屬性，提供更豐富的錯誤上下文。所有子類別皆繼承此介面。

### 建構簽名

```python
ModbusError(
    message: str = "",
    *,
    address: int | None = None,
    unit_id: int | None = None,
    function_code: str | None = None,
)
```

### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `address` | `int \| None` | Modbus 暫存器起始位址 |
| `unit_id` | `int \| None` | 設備位址（Slave ID） |
| `function_code` | `str \| None` | Modbus 功能碼（如 `"FC03"`） |

上下文資訊會自動附加到錯誤訊息中，格式如：`"讀取失敗 [addr=100, unit=1, fc=FC03]"`。

---

## 例外一覽表

| 例外 | 說明 | 常見原因 |
|------|------|---------|
| [[ModbusError]] | 基礎例外，所有 Modbus 相關例外的父類別 | 連線失敗、讀寫操作失敗 |
| [[ModbusEncodeError]] | 編碼錯誤 | 值超出資料類型允許範圍（如 Int16 超過 32767）；型別不符（如傳入字串給數值型別） |
| [[ModbusDecodeError]] | 解碼錯誤 | 暫存器資料長度不足；資料格式錯誤（如無效的 IEEE 754 格式） |
| [[ModbusConfigError]] | 設定錯誤 | 無效的連線參數（如負的 port 號）；無效的資料型別參數（如 bit_width 非 16 的倍數） |
| [[ModbusCircuitBreakerError]] | 斷路器開啟錯誤 | 某個 unit_id 連續失敗次數達到 `circuit_breaker_threshold` |
| [[ModbusQueueFullError]] | 請求佇列已滿錯誤 | 請求佇列達到 `max_queue_size` 上限 |

---

## ModbusCircuitBreakerError

> [!info] v0.4.2 新增

當某個 `unit_id` 的斷路器處於 OPEN 狀態時拋出，表示該設備連續失敗次數已達閾值，暫時停止請求。

### 建構簽名

```python
ModbusCircuitBreakerError(unit_id: int, message: str | None = None)
```

### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `unit_id` | `int` | 觸發斷路器的設備位址 |

---

## ModbusQueueFullError

> [!info] v0.4.2 新增

當請求佇列達到 `max_queue_size` 上限時拋出。繼承自 [[ModbusError]]，可透過 `ModbusError` 統一捕捉。

---

## 使用範例

### 統一捕捉所有 Modbus 例外

```python
from csp_lib.modbus import ModbusError

try:
    registers = await client.read_holding_registers(0, 10)
except ModbusError as e:
    print(f"Modbus 操作失敗: {e}")
    # v0.5.1+：可存取上下文屬性
    if e.address is not None:
        print(f"  位址: {e.address}")
    if e.unit_id is not None:
        print(f"  設備: {e.unit_id}")
```

### 細粒度錯誤處理

```python
from csp_lib.modbus import (
    ModbusEncodeError,
    ModbusDecodeError,
    ModbusConfigError,
    ModbusCircuitBreakerError,
    ModbusQueueFullError,
)

try:
    await client.read_holding_registers(0, 10, unit_id=1)
except ModbusCircuitBreakerError as e:
    print(f"設備 {e.unit_id} 斷路器已開啟，暫停請求")
except ModbusQueueFullError:
    print("請求佇列已滿，請稍後重試")
except ModbusEncodeError as e:
    print(f"編碼失敗: {e}")
except ModbusDecodeError as e:
    print(f"解碼失敗: {e}")
except ModbusConfigError as e:
    print(f"設定錯誤: {e}")
```

---

## 相關頁面

- [[Clients]] — 客戶端讀寫操作拋出 [[ModbusError]] 及其子類別
- [[ModbusCodec]] — 編解碼器拋出 [[ModbusEncodeError]] / [[ModbusDecodeError]]
- [[_MOC Modbus]] — Modbus 模組總覽
