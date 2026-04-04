---
tags:
  - type/class
  - layer/can
  - status/complete
source: csp_lib/can/config.py
created: 2026-03-06
updated: 2026-04-04
version: ">=0.4.2"
---

# CAN Configuration

> CAN Bus 連線設定與訊框資料結構

---

## Quick Example

```python
from csp_lib.can import CANBusConfig, CANFrame

# 建立 SocketCAN 配置
config = CANBusConfig(interface="socketcan", channel="can0")

# 建立 CAN 訊框
frame = CANFrame(can_id=0x100, data=b"\x01\x02\x03")
print(f"CAN ID: 0x{frame.can_id:03X}, Data: {frame.data.hex()}")
```

---

## CANBusConfig

```python
from csp_lib.can import CANBusConfig

config = CANBusConfig(
    interface="socketcan",       # python-can 介面名稱
    channel="can0",              # 通道
    bitrate=500_000,             # 位元率（預設 500kbps）
    receive_own_messages=False,  # 是否接收自己發送的訊息
)
```

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `interface` | `str` | *必填* | python-can 介面（`"socketcan"`, `"virtual"`, `"tcp"`） |
| `channel` | `str` | *必填* | 通道名稱（`"can0"`, `"192.168.1.100:5000"`） |
| `bitrate` | `int` | `500_000` | CAN 位元率 |
| `receive_own_messages` | `bool` | `False` | 是否接收自己發送的訊息 |

### 常見介面配置

```python
# SocketCAN (Linux)
CANBusConfig(interface="socketcan", channel="can0")

# CAN-over-TCP 閘道器
CANBusConfig(interface="tcp", channel="192.168.1.100:5000")

# 虛擬介面（測試用）
CANBusConfig(interface="virtual", channel="vcan0")
```

---

## CANFrame

```python
from csp_lib.can import CANFrame

frame = CANFrame(
    can_id=0x100,
    data=b"\xD5\xDD\x0E\x00\x00\x00\x00\x00",
    timestamp=1709712000.0,
    is_remote=False,
)
```

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `can_id` | `int` | *必填* | CAN 訊框 ID |
| `data` | `bytes` | *必填* | 訊框資料（最多 8 bytes） |
| `timestamp` | `float` | `0.0` | 時間戳 |
| `is_remote` | `bool` | `False` | 是否為遠端請求訊框 |

---

## 相關頁面

- [[CAN Clients]] — 使用 CANBusConfig 建立客戶端
- [[CAN Exceptions]] — 錯誤處理
- [[_MOC CAN]] — CAN 模組總覽
