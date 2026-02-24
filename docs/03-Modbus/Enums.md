---
tags:
  - type/enum
  - layer/modbus
  - status/complete
source: csp_lib/modbus/enums.py
created: 2026-02-17
---

# Enums

## Modbus 列舉定義 (`csp_lib.modbus.enums`)

定義 Modbus 通訊所需的常數與列舉，包含位元組順序、暫存器順序、串口校驗位元及功能碼。

---

## ByteOrder

位元組順序，定義多位元組資料在**單一暫存器內**的排列方式。

| 值 | 內部表示 | 說明 |
|----|---------|------|
| `BIG_ENDIAN` | `">"` | 大端序，高位元組在前（Modbus 預設） |
| `LITTLE_ENDIAN` | `"<"` | 小端序，低位元組在前 |

---

## RegisterOrder

暫存器順序，定義**多暫存器資料**的排列方式。例如 32-bit 整數需要 2 個暫存器，此設定決定高低位暫存器的先後順序。

| 值 | 內部表示 | 說明 |
|----|---------|------|
| `HIGH_FIRST` | `"high"` | 高位暫存器在前（常見，如 AB CD） |
| `LOW_FIRST` | `"low"` | 低位暫存器在前（如 CD AB） |

---

## Parity

串口校驗位元，用於 RTU 模式的串口通訊設定。

| 值 | 內部表示 | 說明 |
|----|---------|------|
| `NONE` | `"N"` | 無校驗 |
| `EVEN` | `"E"` | 偶校驗 |
| `ODD` | `"O"` | 奇校驗 |

---

## FunctionCode

Modbus 功能碼（繼承自 `IntEnum`），定義標準 Modbus 請求類型。

### 讀取功能碼

| 值 | 十六進位 | 說明 |
|----|---------|------|
| `READ_COILS` | `0x01` | 讀取線圈狀態 |
| `READ_DISCRETE_INPUTS` | `0x02` | 讀取離散輸入 |
| `READ_HOLDING_REGISTERS` | `0x03` | 讀取保持暫存器 |
| `READ_INPUT_REGISTERS` | `0x04` | 讀取輸入暫存器 |

### 寫入功能碼

| 值 | 十六進位 | 說明 |
|----|---------|------|
| `WRITE_SINGLE_COIL` | `0x05` | 寫入單一線圈 |
| `WRITE_SINGLE_REGISTER` | `0x06` | 寫入單一暫存器 |
| `WRITE_MULTIPLE_COILS` | `0x0F` | 寫入多個線圈 |
| `WRITE_MULTIPLE_REGISTERS` | `0x10` | 寫入多個暫存器 |

---

## 相關頁面

- [[_MOC Modbus]] — Modbus 模組總覽
