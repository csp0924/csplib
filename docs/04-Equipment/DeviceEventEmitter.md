---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/device/events.py
updated: 2026-04-04
version: ">=0.4.2"
---

# DeviceEventEmitter

> 設備事件發射器

`DeviceEventEmitter` 使用 `asyncio.Queue` 進行非阻塞事件處理，避免大量事件阻塞讀取循環。由 [[AsyncModbusDevice]] 內部建立與管理。

---

## 12 種事件類型

| 事件名稱 | 常數 | Payload 類別 | 說明 |
|---------|------|-------------|------|
| `connected` | `EVENT_CONNECTED` | `ConnectedPayload` | 連線成功/恢復 |
| `disconnected` | `EVENT_DISCONNECTED` | `DisconnectPayload` | 斷線 |
| `read_complete` | `EVENT_READ_COMPLETE` | `ReadCompletePayload` | 讀取完成 |
| `read_error` | `EVENT_READ_ERROR` | `ReadErrorPayload` | 讀取錯誤 |
| `value_change` | `EVENT_VALUE_CHANGE` | `ValueChangePayload` | 值變化 |
| `write_complete` | `EVENT_WRITE_COMPLETE` | `WriteCompletePayload` | 寫入成功 |
| `write_error` | `EVENT_WRITE_ERROR` | `WriteErrorPayload` | 寫入失敗 |
| `alarm_triggered` | `EVENT_ALARM_TRIGGERED` | `DeviceAlarmPayload` | 告警觸發 |
| `alarm_cleared` | `EVENT_ALARM_CLEARED` | `DeviceAlarmPayload` | 告警解除 |
| `reconfigured` | `EVENT_RECONFIGURED` | `ReconfiguredPayload` | 動態重新配置完成 |
| `restarted` | `EVENT_RESTARTED` | `RestartedPayload` | 讀取迴圈重啟 |
| `point_toggled` | `EVENT_POINT_TOGGLED` | `PointToggledPayload` | 點位啟用/停用 |

---

## Payload 類別

所有 Payload 都是不可變的 frozen dataclass，包含 `timestamp` 欄位（UTC）。

### ConnectedPayload

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `timestamp` | `datetime` | 事件時間 |

### DisconnectPayload

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `reason` | `str` | 斷線原因 |
| `consecutive_failures` | `int` | 連續失敗次數 |
| `timestamp` | `datetime` | 事件時間 |

### ReadCompletePayload

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `values` | `dict[str, Any]` | 讀取值字典 |
| `duration_ms` | `float` | 讀取耗時（毫秒） |
| `timestamp` | `datetime` | 事件時間 |

### ReadErrorPayload

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `error` | `str` | 錯誤訊息 |
| `consecutive_failures` | `int` | 連續失敗次數 |
| `timestamp` | `datetime` | 事件時間 |

### ValueChangePayload

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `point_name` | `str` | 點位名稱 |
| `old_value` | `Any` | 舊值 |
| `new_value` | `Any` | 新值 |
| `timestamp` | `datetime` | 事件時間 |

### WriteCompletePayload

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `point_name` | `str` | 點位名稱 |
| `value` | `Any` | 寫入值 |
| `timestamp` | `datetime` | 事件時間 |

### WriteErrorPayload

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `point_name` | `str` | 點位名稱 |
| `value` | `Any` | 寫入值 |
| `error` | `str` | 錯誤訊息 |
| `timestamp` | `datetime` | 事件時間 |

### DeviceAlarmPayload

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `alarm_event` | `AlarmEvent` | 告警事件 |
| `timestamp` | `datetime` | 事件時間 |

### ReconfiguredPayload

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `changed_sections` | `tuple[str, ...]` | 已變更的組件名稱列表 |
| `timestamp` | `datetime` | 事件時間 |

### RestartedPayload

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `timestamp` | `datetime` | 事件時間 |

### PointToggledPayload

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `point_name` | `str` | 被切換的點位名稱 |
| `enabled` | `bool` | 切換後的啟用狀態 |
| `timestamp` | `datetime` | 事件時間 |

---

## on / emit 模式

```python
# 註冊非同步處理器
async def on_change(payload: ValueChangePayload):
    print(f"{payload.point_name}: {payload.old_value} -> {payload.new_value}")

cancel = device.on("value_change", on_change)

# 取消訂閱
cancel()
```

### WeakRef Listener

> [!info] v0.5.1 新增

`on()` 方法支援 `weak=True` 參數，以弱引用儲存 handler。當 handler 的 referent 被 GC 回收後，自動從處理器列表移除（lazy purge）。

```python
class MyMonitor:
    def __init__(self, device):
        # bound method 使用 WeakMethod，物件銷毀後自動移除
        device.on("value_change", self.on_change, weak=True)

    async def on_change(self, payload: ValueChangePayload):
        print(payload.new_value)

monitor = MyMonitor(device)
# 當 monitor 被 GC 回收後，handler 自動失效
```

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `event` | `str` | (必填) | 事件名稱 |
| `handler` | `AsyncHandler` | (必填) | 非同步處理函數 |
| `weak` | `bool` | `False` | 是否以弱引用儲存 handler |

> [!warning] Lambda 與 Closure
> Lambda 和 closure 雖可弱引用，但若呼叫端未保留強引用，弱引用會立即失效，handler 永遠不會被呼叫。建議 `weak=True` 僅用於 bound method。

### 發射方式

| 方法 | 說明 |
|------|------|
| `emit(event, payload)` | 非阻塞，放入佇列由 worker 處理。無監聽器時直接跳過 |
| `emit_await(event, payload)` | 阻塞，等待處理完成。用於重要事件（連線、告警） |

### 其他方法

| 方法 | 說明 |
|------|------|
| `has_listeners(event)` | 檢查是否有（存活的）事件監聽器 |
| `clear(event=None)` | 清除事件處理器，`None` 清除所有 |
| `queue_size` | 目前佇列中的事件數量 |

---

## Quick Example

```python
from csp_lib.equipment.device.events import DeviceEventEmitter, ValueChangePayload

emitter = DeviceEventEmitter(max_queue_size=10000)
await emitter.start()

async def on_value(payload: ValueChangePayload):
    print(f"{payload.point_name}: {payload.old_value} -> {payload.new_value}")

cancel = emitter.on("value_change", on_value)
emitter.emit("value_change", ValueChangePayload(
    device_id="dev_001", point_name="voltage", old_value=220, new_value=221,
))

cancel()  # 取消訂閱
await emitter.stop()
```

---

## 相關頁面

- [[AsyncModbusDevice]] -- 核心設備類別
- [[AsyncCANDevice]] -- CAN Bus 設備
- [[_MOC Equipment]] -- 設備模組總覽
