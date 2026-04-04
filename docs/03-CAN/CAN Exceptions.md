---
tags:
  - type/class
  - layer/can
  - status/complete
source: csp_lib/can/exceptions.py
created: 2026-03-06
updated: 2026-04-04
version: ">=0.4.2"
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

## 使用範例

```python
from csp_lib.can import CANError, CANConnectionError, CANTimeoutError, CANSendError

try:
    await client.connect()
except CANConnectionError as e:
    print(f"連線失敗: {e}")

try:
    response = await client.request(0x300, data, 0x301, timeout=1.0)
except CANTimeoutError:
    print("請求逾時")

try:
    await client.send(0x200, data)
except CANSendError as e:
    print(f"發送失敗: {e}")

# 統一攔截所有 CAN 錯誤
try:
    ...
except CANError as e:
    print(f"CAN 錯誤: {e}")
```

---

## 相關頁面

- [[CAN Clients]] — 客戶端方法會拋出這些例外
- [[_MOC CAN]] — CAN 模組總覽
