---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/device/events.py
---

# DeviceEventEmitter

> 設備事件發射器

`DeviceEventEmitter` 使用 `asyncio.Queue` 進行非阻塞事件處理，避免大量事件阻塞讀取循環。由 [[AsyncModbusDevice]] 內部建立與管理。

---

## 9 種事件類型

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

### 發射方式

| 方法 | 說明 |
|------|------|
| `emit(event, payload)` | 非阻塞，放入佇列由 worker 處理。無監聽器時直接跳過 |
| `emit_await(event, payload)` | 阻塞，等待處理完成。用於重要事件（連線、告警） |

---

## 相關頁面

- [[AsyncModbusDevice]] -- 核心設備類別
- [[_MOC Equipment]] -- 設備模組總覽
