---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/core/point.py
---

# WritePoint

> 寫入點位定義

`WritePoint` 繼承自 `PointDefinition`，是不可變的 frozen dataclass，用於定義 Modbus 設備的寫入點位。支援可選的值驗證器，在寫入前檢查值的合法性。

---

## 參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `name` | `str` | (必填) | 點位名稱（唯一識別） |
| `address` | `int` | (必填) | Modbus 暫存器位址 |
| `data_type` | `ModbusDataType` | (必填) | 資料類型（來自 `csp_lib.modbus`） |
| `function_code` | `FunctionCode \| None` | `WRITE_MULTIPLE_REGISTERS` | Modbus 功能碼 |
| `byte_order` | `ByteOrder` | `BIG_ENDIAN` | 位元組順序 |
| `register_order` | `RegisterOrder` | `HIGH_FIRST` | 暫存器順序 |
| `validator` | `ValueValidator \| None` | `None` | 值驗證器 |

---

## 程式碼範例

```python
from csp_lib.equipment.core import WritePoint, RangeValidator
from csp_lib.modbus import UInt16, FunctionCode

WritePoint(
    name="power_limit",
    address=100,
    data_type=UInt16(),
    function_code=FunctionCode.WRITE_MULTIPLE_REGISTERS,  # default
    validator=RangeValidator(min_value=0, max_value=10000),
)
```

---

## 相關頁面

- [[ReadPoint]] -- 讀取點位定義
- [[Validators]] -- 內建驗證器
- [[_MOC Equipment]] -- 設備模組總覽
