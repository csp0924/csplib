---
tags:
  - type/class
  - layer/can
  - status/complete
source: csp_lib/can/exceptions.py
created: 2026-03-06
updated: 2026-04-06
version: ">=0.7.1"
---

# CAN Exceptions

> CAN Bus 例外類別階層

---

## 例外樹

```
CANError                    CAN Bus 基礎例外
├── CANConnectionError      連線錯誤（Bus 建立失敗、python-can 未安裝）
├── CANTimeoutError         逾時錯誤（request-response 逾時）
└── CANSendError            發送錯誤（未連線、發送失敗）
```

---

## Error Context（v0.7.1 新增）

`CANError`（以及所有子類別）的建構子支援兩個 keyword-only 參數，提供更豐富的錯誤訊息。

```python
CANError(message, *, can_id: int | None = None, bus_index: int | None = None)
```

| 參數 | 型別 | 說明 |
|------|------|------|
| `can_id` | `int \| None` | CAN frame ID，自動格式化為 `0xNNN` 十六進位 |
| `bus_index` | `int \| None` | CAN Bus 索引號 |

設定後，錯誤訊息會自動加上 `[bus=N, can_id=0xNNN]` 前綴：

```python
raise CANTimeoutError("請求無回應", can_id=0x300, bus_index=0)
# str(e) -> "[bus=0, can_id=0x300] 請求無回應"

raise CANSendError("佇列已滿", bus_index=1)
# str(e) -> "[bus=1] 佇列已滿"
```

所有子類別自動繼承此行為，不需要額外覆寫 `__init__`。

> [!tip] 屬性存取
> 例外物件上可直接讀取 `e.can_id` 和 `e.bus_index`，方便在 except 區塊內做進一步處理（如統計、告警）。

---

## Quick Example

```python
from csp_lib.can import CANError, CANConnectionError, CANTimeoutError, CANSendError

try:
    await client.connect()
except CANConnectionError as e:
    print(f"連線失敗: {e}")

try:
    response = await client.request(0x300, data, 0x301, timeout=1.0)
except CANTimeoutError as e:
    print(f"請求逾時: {e}")          # 若有 can_id 會顯示 "[bus=0, can_id=0x300] 請求逾時"
    print(f"can_id={e.can_id:#05x}") # 0x300

try:
    await client.send(0x200, data)
except CANSendError as e:
    print(f"發送失敗: {e}")

# 統一攔截所有 CAN 錯誤
try:
    ...
except CANError as e:
    print(f"CAN 錯誤 [bus={e.bus_index}]: {e}")
```

---

## 相關頁面

- [[CAN Clients]] — 客戶端方法會拋出這些例外
- [[_MOC CAN]] — CAN 模組總覽
