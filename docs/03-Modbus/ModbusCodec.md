---
tags:
  - type/class
  - layer/modbus
  - status/complete
source: csp_lib/modbus/codec.py
created: 2026-02-17
---

# ModbusCodec

## Modbus 編解碼器 (`csp_lib.modbus.ModbusCodec`)

`ModbusCodec` 是高階編解碼器，封裝 `ByteOrder` 與 `RegisterOrder` 參數，提供簡潔的 `encode()` / `decode()` API。透過此類別，呼叫端無需每次手動傳入位元組順序和暫存器順序。

---

## 建構參數

`ModbusCodec` 的 `encode()` 和 `decode()` 方法接受選用的 `byte_order` 與 `register_order` 參數，若未提供則使用預設值：

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `byte_order` | `ByteOrder` | `BIG_ENDIAN` | 單一暫存器內的位元組排列方式 |
| `register_order` | `RegisterOrder` | `HIGH_FIRST` | 多暫存器資料的排列方式 |

---

## 方法

### `encode(data_type, value, byte_order?, register_order?) -> list[int]`

將 Python 值編碼為暫存器值列表。

- **data_type** — `ModbusDataType` 實例（如 `Float32()`、`UInt16()`）
- **value** — 要編碼的 Python 值
- **回傳** — 暫存器值列表，每個元素為 0-65535 範圍的整數
- **例外** — 編碼失敗時拋出 `ModbusEncodeError`

### `decode(data_type, registers, byte_order?, register_order?) -> Any`

將暫存器值列表解碼為 Python 值。

- **data_type** — `ModbusDataType` 實例
- **registers** — 暫存器值列表
- **回傳** — 解碼後的 Python 值
- **例外** — 解碼失敗時拋出 `ModbusDecodeError`

---

## 使用範例

```python
from csp_lib.modbus import ModbusCodec, Float32, ByteOrder, RegisterOrder

codec = ModbusCodec(
    byte_order=ByteOrder.BIG_ENDIAN,
    register_order=RegisterOrder.HIGH_FIRST,
)

# 編碼
encoded = codec.encode(Float32(), 123.45)
# encoded: [0x42F6, 0xE666]

# 解碼
decoded = codec.decode(Float32(), encoded)
# decoded: 123.45
```

### 搭配不同位元組順序

```python
from csp_lib.modbus import ModbusCodec, UInt32

codec = ModbusCodec()

# 使用預設順序 (BIG_ENDIAN, HIGH_FIRST)
registers = codec.encode(UInt32(), 0x12345678)
# registers: [0x1234, 0x5678]

value = codec.decode(UInt32(), registers)
# value: 305419896
```

---

## 相關頁面

- [[Data Types]] — 所有可用的資料型別定義
- [[Enums]] — ByteOrder、RegisterOrder 列舉定義
- [[_MOC Modbus]] — Modbus 模組總覽
