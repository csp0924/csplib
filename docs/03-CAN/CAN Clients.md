---
tags:
  - type/class
  - layer/can
  - status/complete
source: csp_lib/can/clients/
created: 2026-03-06
updated: 2026-04-04
version: ">=0.4.2"
---

# CAN Clients

> CAN Bus 非同步客戶端

---

## AsyncCANClientBase（ABC）

所有 CAN 客戶端必須實作的抽象介面。

```python
from csp_lib.can.clients.base import AsyncCANClientBase
```

### 介面方法

| 分類 | 方法 | 回傳 | 說明 |
|------|------|------|------|
| **連線管理** | `async connect()` | `None` | 建立連線 |
| | `async disconnect()` | `None` | 斷開連線 |
| | `async is_connected()` | `bool` | 檢查是否已連線 |
| **被動監聽** | `async start_listener()` | `None` | 啟動背景接收 |
| | `async stop_listener()` | `None` | 停止背景接收 |
| | `subscribe(can_id: int, handler: Callable[[CANFrame], Any])` | `Callable[[], None]` | 訂閱指定 CAN ID，回傳取消函數 |
| **主動發送** | `async send(can_id: int, data: bytes)` | `None` | 發送 CAN 訊框 |
| **請求-回應** | `async request(can_id: int, data: bytes, response_id: int, timeout: float = 1.0)` | `CANFrame` | 發送並等回應，逾時拋出 [[CAN Exceptions\|CANTimeoutError]] |

---

## PythonCANClient

基於 [python-can](https://python-can.readthedocs.io/) 的實作。

```python
from csp_lib.can import PythonCANClient, CANBusConfig

client = PythonCANClient(CANBusConfig(
    interface="socketcan",
    channel="can0",
))
```

### 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `config` | [[CAN Configuration\|CANBusConfig]] | CAN Bus 連線設定 |

### Quick Example

```python
# 1. 連線
await client.connect()
await client.start_listener()

# 2. 被動監聽
def on_bms(frame):
    print(f"BMS: {frame.data.hex()}")

cancel = client.subscribe(0x100, on_bms)

# 3. 主動發送
await client.send(0x200, b"\x88\x13\x00\x00\x00\x00\x00\x00")

# 4. 請求-回應
response = await client.request(
    can_id=0x300,
    data=b"\x01",
    response_id=0x301,
    timeout=1.0,
)

# 5. 清理
cancel()  # 取消訂閱
await client.stop_listener()
await client.disconnect()
```

### 內部機制

```mermaid
graph TB
    subgraph PythonCANClient
        Bus["can.Bus<br/>(python-can)"]
        Loop["_listen_loop()<br/>asyncio.Task"]
        Handlers["handlers<br/>dict[can_id → list]"]
        Pending["pending_responses<br/>dict[can_id → Future]"]
    end

    Bus -->|"to_thread(recv)"| Loop
    Loop -->|"按 CAN ID 分發"| Handlers
    Loop -->|"匹配 request"| Pending

    App -->|subscribe| Handlers
    App -->|request| Pending
    App -->|"to_thread(send)"| Bus
```

- 所有阻塞 I/O（`recv()`、`send()`）都透過 `asyncio.to_thread()` 避免阻塞事件迴圈
- 背景 listener task 持續接收，按 CAN ID 分發到 handlers
- `request()` 使用 `asyncio.Future` 實現請求-回應配對

---

## 相關頁面

- [[CAN Configuration]] — CANBusConfig 設定
- [[CAN Exceptions]] — 錯誤處理
- [[AsyncCANDevice]] — 使用客戶端的設備類別
- [[_MOC CAN]] — CAN 模組總覽
