---
tags:
  - type/class
  - layer/modbus
  - status/complete
source: csp_lib/modbus/exceptions.py
created: 2026-02-17
---

# Exceptions

## Modbus 例外類別 (`csp_lib.modbus.exceptions`)

定義 Modbus 模組專用的例外類別階層，方便統一捕捉與細粒度錯誤處理。

---

## 繼承結構

```
Exception
└── ModbusError (基礎例外)
    ├── ModbusEncodeError (編碼錯誤)
    ├── ModbusDecodeError (解碼錯誤)
    └── ModbusConfigError (設定錯誤)
```

---

## 例外一覽表

| 例外 | 說明 | 常見原因 |
|------|------|---------|
| `ModbusError` | Modbus 基礎例外，所有 Modbus 相關例外的父類別 | 連線失敗、讀寫操作失敗 |
| `ModbusEncodeError` | 編碼錯誤 | 值超出資料類型允許範圍（如 Int16 超過 32767）；型別不符（如傳入字串給數值型別） |
| `ModbusDecodeError` | 解碼錯誤 | 暫存器資料長度不足；資料格式錯誤（如無效的 IEEE 754 格式） |
| `ModbusConfigError` | 設定錯誤 | 無效的連線參數（如負的 port 號）；無效的資料型別參數（如 bit_width 非 16 的倍數） |

---

## 使用範例

### 統一捕捉所有 Modbus 例外

```python
from csp_lib.modbus import ModbusError

try:
    registers = await client.read_holding_registers(0, 10)
except ModbusError as e:
    print(f"Modbus 操作失敗: {e}")
```

### 細粒度錯誤處理

```python
from csp_lib.modbus import (
    ModbusEncodeError,
    ModbusDecodeError,
    ModbusConfigError,
)

try:
    encoded = data_type.encode(value)
except ModbusEncodeError as e:
    print(f"編碼失敗: {e}")
except ModbusDecodeError as e:
    print(f"解碼失敗: {e}")
except ModbusConfigError as e:
    print(f"設定錯誤: {e}")
```

---

## 相關頁面

- [[_MOC Modbus]] — Modbus 模組總覽
