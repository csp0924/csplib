---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/core/point.py
---

# ReadPoint

> 讀取點位定義

`ReadPoint` 繼承自 `PointDefinition`，是不可變的 frozen dataclass，用於定義 Modbus 設備的讀取點位。每個 ReadPoint 對應一個暫存器位址，並可附加資料處理管線。

---

## 參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `name` | `str` | (必填) | 點位名稱（唯一識別） |
| `address` | `int` | (必填) | Modbus 暫存器位址 |
| `data_type` | `ModbusDataType` | (必填) | 資料類型（來自 `csp_lib.modbus`） |
| `function_code` | `FunctionCode \| None` | `READ_HOLDING_REGISTERS` | Modbus 功能碼 |
| `byte_order` | `ByteOrder` | `BIG_ENDIAN` | 位元組順序 |
| `register_order` | `RegisterOrder` | `HIGH_FIRST` | 暫存器順序 |
| `pipeline` | `ProcessingPipeline \| None` | `None` | 資料處理管線 |
| `read_group` | `str` | `""` | 讀取分組名稱（空字串參與自動合併） |
| `metadata` | `PointMetadata \| None` | `None` | 點位元資料（單位、描述） |

---

## 程式碼範例

```python
from csp_lib.equipment.core import ReadPoint
from csp_lib.modbus import Float32, FunctionCode

ReadPoint(
    name="voltage",
    address=0,
    data_type=Float32(),
    function_code=FunctionCode.READ_HOLDING_REGISTERS,  # default
    pipeline=None,
    read_group="",
)
```

---

## 相關頁面

- [[WritePoint]] -- 寫入點位定義
- [[ProcessingPipeline]] -- 資料處理管線
- [[_MOC Equipment]] -- 設備模組總覽
