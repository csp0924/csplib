---
tags:
  - type/class
  - layer/modbus
  - status/complete
source: csp_lib/modbus/types/
created: 2026-02-17
---

# Data Types

## Modbus 資料型別 (`csp_lib.modbus.types`)

所有 Modbus 資料型別皆繼承自抽象基底類別 `ModbusDataType`，必須實作以下介面：

- `register_count` — 所需的暫存器數量（每個暫存器 16 bits）
- `encode(value, byte_order, register_order)` — 將 Python 值編碼為暫存器列表
- `decode(registers, byte_order, register_order)` — 將暫存器列表解碼為 Python 值

---

## 型別一覽表

### 固定長度數值型別

| 型別 | Register 數 | 說明 | 值範圍 |
|------|:-----------:|------|--------|
| `Int16` | 1 | 帶號 16-bit 整數 | -32,768 ~ 32,767 |
| `UInt16` | 1 | 無號 16-bit 整數 | 0 ~ 65,535 |
| `Int32` | 2 | 帶號 32-bit 整數 | -2,147,483,648 ~ 2,147,483,647 |
| `UInt32` | 2 | 無號 32-bit 整數 | 0 ~ 4,294,967,295 |
| `Int64` | 4 | 帶號 64-bit 整數 | -9.2 x 10^18 ~ 9.2 x 10^18 |
| `UInt64` | 4 | 無號 64-bit 整數 | 0 ~ 1.8 x 10^19 |
| `Float32` | 2 | IEEE 754 單精度浮點數 | — |
| `Float64` | 4 | IEEE 754 雙精度浮點數 | — |

### 動態長度型別

| 型別 | Register 數 | 說明 |
|------|:-----------:|------|
| `DynamicInt(bit_width)` | bit_width / 16 | 動態長度帶號整數，bit_width 須為 16 的倍數 |
| `DynamicUInt(bit_width)` | bit_width / 16 | 動態長度無號整數，bit_width 須為 16 的倍數 |

### 字串型別

| 型別 | Register 數 | 說明 |
|------|:-----------:|------|
| `ModbusString(max_length, encoding)` | ceil(max_length / 2) | 字串型別，預設 ASCII 編碼，支援 UTF-8 |

---

## 使用範例

### 基本編碼/解碼

```python
from csp_lib.modbus import Float32

data_type = Float32()
registers = data_type.encode(123.45)  # -> [0x42F6, 0xE666]
value = data_type.decode(registers)   # -> 123.45
```

### 動態長度型別

```python
from csp_lib.modbus import DynamicUInt

# 48-bit 無號整數，需要 3 個暫存器
uint48 = DynamicUInt(48)
print(uint48.register_count)  # 3
```

### 字串型別

```python
from csp_lib.modbus import ModbusString

# 最大 16 bytes，需要 8 個暫存器
name = ModbusString(16)
print(name.register_count)  # 8
```

---

## 類別繼承結構

```
ModbusDataType (ABC)
├── Int16
├── UInt16
├── Int32
├── UInt32
├── Int64
├── UInt64
├── Float32
├── Float64
├── DynamicInt
├── DynamicUInt
└── ModbusString
```

---

## 相關頁面

- [[ModbusCodec]] — 高階編解碼器，簡化 encode/decode 呼叫
- [[_MOC Modbus]] — Modbus 模組總覽
