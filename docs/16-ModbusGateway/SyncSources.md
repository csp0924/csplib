---
tags:
  - type/class
  - layer/modbus-gateway
  - status/complete
source: csp_lib/modbus_gateway/sync_sources.py
updated: 2026-04-04
version: ">=0.5.0"
---

# SyncSources

> [!info] v0.5.0 新增

DataSyncSource 將外部資料來源的數據同步到 Gateway 的暫存器空間（通常是 Input Registers）。模組提供兩種內建實作：**RedisSubscriptionSource**（Redis Pub/Sub 訂閱）與 **PollingCallbackSource**（定時輪詢回呼）。

---

## DataSyncSource Protocol

```python
@runtime_checkable
class DataSyncSource(Protocol):
    async def start(self, update_callback: UpdateRegisterCallback) -> None:
        """開始產生資料，透過 update_callback 推送到 Gateway。"""
        ...

    async def stop(self) -> None:
        """停止資料產生並釋放資源。"""
        ...
```

`UpdateRegisterCallback` 型別：`Callable[[str, Any], Awaitable[None]]`

當 [[ModbusGatewayServer]] 啟動時，會對每個 DataSyncSource 呼叫 `start(callback)`，將內部的 `_update_register_callback` 注入。DataSyncSource 使用此 callback 更新暫存器值。

來源：`csp_lib/modbus_gateway/protocol.py`

---

## RedisSubscriptionSource

訂閱 Redis channel，將接收到的 JSON 訊息解析後更新暫存器。

### 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `redis_client` | `redis.asyncio.Redis` 或 `RedisClient` | -- | Redis 連線實例 |
| `channel` | `str` | `"gateway:sync"` | Redis channel 名稱 |
| `batch_mode` | `bool` | `True` | 是否啟用 key-value 簡潔模式 |

### 支援的訊息格式

**單筆格式：**
```json
{"register": "soc", "value": 75.5}
```

**批次格式：**
```json
[
  {"register": "soc", "value": 75.5},
  {"register": "soh", "value": 98.0}
]
```

**Key-value 簡潔模式（`batch_mode=True`）：**
```json
{"soc": 75.5, "soh": 98.0}
```

> [!note] 訊息解析優先順序
> 若 payload 是 dict 且包含 `"register"` 和 `"value"` key，會優先匹配為單筆格式，不會被 batch_mode 的 key-value 模式吞掉。

### Quick Example

```python
from csp_lib.modbus_gateway import RedisSubscriptionSource

source = RedisSubscriptionSource(
    redis_client=redis,
    channel="bms:status",
    batch_mode=True,
)

async with ModbusGatewayServer(config, registers, sync_sources=[source]) as gw:
    await gw.serve()

# 從另一端發布更新：
# await redis.publish("bms:status", '{"soc": 80.0, "soh": 97.5}')
```

---

## PollingCallbackSource

定時呼叫使用者提供的 async function 取得暫存器值，適用於無法使用 Redis 的場景或需要直接從設備物件讀取的情況。

### 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `callback` | `Callable[[], Awaitable[dict[str, Any]]]` | -- | 回傳 `{name: value}` 的 async function |
| `interval` | `float` | `1.0` | 輪詢間隔（秒） |

Callback 回傳值中 `None` 值會被忽略，不會更新到暫存器。未知的暫存器名稱會被靜默跳過（log at DEBUG）。

### Quick Example

```python
from csp_lib.modbus_gateway import PollingCallbackSource

async def read_device_status() -> dict[str, float]:
    """從設備物件讀取最新狀態。"""
    return {
        "soc": device.soc,
        "soh": device.soh,
        "voltage": device.voltage,
    }

source = PollingCallbackSource(read_device_status, interval=2.0)

async with ModbusGatewayServer(config, registers, sync_sources=[source]) as gw:
    await gw.serve()
```

---

## 自訂 DataSyncSource

實作 `DataSyncSource` protocol 即可建立自訂同步來源：

```python
class MqttSyncSource:
    """MQTT 訂閱同步來源（範例）。"""

    def __init__(self, broker: str, topic: str) -> None:
        self._broker = broker
        self._topic = topic
        self._update_cb: UpdateRegisterCallback | None = None

    async def start(self, update_callback: UpdateRegisterCallback) -> None:
        self._update_cb = update_callback
        # 連接 MQTT broker，訂閱 topic...

    async def stop(self) -> None:
        # 取消訂閱，斷開連線...
        pass
```

---

## 相關頁面

- [[ModbusGatewayServer]] -- 管理 SyncSource 生命週期
- [[RegisterMap]] -- SyncSource 透過 callback 更新的暫存器空間
- [[GatewayConfig]] -- 暫存器定義
