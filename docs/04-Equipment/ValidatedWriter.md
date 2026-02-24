---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/transport/writer.py
---

# ValidatedWriter

> 驗證寫入器

`ValidatedWriter` 提供寫入前驗證與可選的寫後讀回確認，確保寫入操作的安全性。與 [[GroupReader]] 對稱，共同提供完整的 I/O 讀寫能力。

---

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `client` | `AsyncModbusClientBase` | (必填) | Modbus 客戶端 |
| `unit_id` | `int` | `1` | 設備位址 (Slave ID) |
| `address_offset` | `int` | `0` | 位址偏移 |

---

## 寫入流程

1. **驗證**：若 [[WritePoint]] 有 `validator`，先呼叫 `validate()` 檢查值
2. **編碼**：呼叫 `data_type.encode()` 將值編碼為暫存器資料
3. **寫入**：根據 `function_code` 呼叫對應的 Modbus 寫入函數
4. **讀回驗證**（可選）：寫入後讀回暫存器值，比對是否一致

---

## WriteStatus 列舉

| 狀態 | 說明 |
|------|------|
| `SUCCESS` | 寫入成功 |
| `VALIDATION_FAILED` | 驗證器驗證失敗 |
| `WRITE_FAILED` | Modbus 寫入失敗 |
| `VERIFICATION_FAILED` | 寫後讀回值不匹配 |

---

## WriteResult

| 欄位 | 型別 | 說明 |
|------|------|------|
| `status` | `WriteStatus` | 寫入狀態 |
| `point_name` | `str` | 點位名稱 |
| `value` | `Any` | 寫入值 |
| `error_message` | `str` | 錯誤訊息（成功時為空） |

---

## 程式碼範例

```python
from csp_lib.equipment.transport import ValidatedWriter

writer = ValidatedWriter(client=client)
result = await writer.write(point, value, verify=True)

if result.status == WriteStatus.SUCCESS:
    print("寫入成功")
elif result.status == WriteStatus.VERIFICATION_FAILED:
    print(f"讀回不匹配: {result.error_message}")
```

---

## 相關頁面

- [[WritePoint]] -- 寫入點位定義
- [[_MOC Equipment]] -- 設備模組總覽
