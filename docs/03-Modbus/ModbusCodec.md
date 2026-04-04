---
tags:
  - type/class
  - layer/modbus
  - status/complete
source: csp_lib/modbus/codec.py
created: 2026-02-17
updated: 2026-04-04
version: 0.6.0
---

# ModbusCodec

## Modbus 編解碼器 (`csp_lib.modbus.ModbusCodec`)

`ModbusCodec` 是高階編解碼器，提供簡潔的 `encode()` / `decode()` API。建構時無需參數，`byte_order` 與 `register_order` 在每次呼叫時傳入（可選，皆有預設值）。

---

## Quick Example

```python
from csp_lib.modbus import ModbusCodec, UInt32

codec = ModbusCodec()
regs = codec.encode(UInt32(), 0x12345678)  # -> [0x1234, 0x5678]
val = codec.decode(UInt32(), regs)          # -> 305419896
```

---

## 建構

`ModbusCodec()` 不接受建構參數。`byte_order` 與 `register_order` 為 `encode()` / `decode()` 的選用參數，未提供時使用預設值：

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `byte_order` | `ByteOrder \| None` | `BIG_ENDIAN` | 單一暫存器內的位元組排列方式 |
| `register_order` | `RegisterOrder \| None` | `HIGH_FIRST` | 多暫存器資料的排列方式 |

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

codec = ModbusCodec()

# 編碼（使用預設 BIG_ENDIAN / HIGH_FIRST）
encoded = codec.encode(Float32(), 123.45)
# encoded: [0x42F6, 0xE666]

# 解碼
decoded = codec.decode(Float32(), encoded)
# decoded: 123.45

# 明確指定順序
encoded = codec.encode(
    Float32(), 123.45,
    byte_order=ByteOrder.BIG_ENDIAN,
    register_order=RegisterOrder.HIGH_FIRST,
)
```

---

## 相關頁面

- [[Data Types]] — 所有可用的資料型別定義
- [[Enums]] — ByteOrder、RegisterOrder 列舉定義
- [[_MOC Modbus]] — Modbus 模組總覽
