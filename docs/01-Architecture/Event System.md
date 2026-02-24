---
tags: [type/concept, status/complete]
---
# Event System

> 事件驅動架構 — DeviceEventEmitter 與 9 種事件類型

## 概述

csp_lib 採用事件驅動架構，設備狀態變化透過 [[DeviceEventEmitter]] 通知所有訂閱者。事件系統基於 `asyncio.Queue`，實現非阻塞的發布/訂閱模式。

## DeviceEventEmitter

[[DeviceEventEmitter]] 定義於 `csp_lib.equipment.device.events`，是設備層的核心事件元件。

### 架構特點

- **Queue-based** — 使用 `asyncio.Queue` 作為事件緩衝區（預設最大 10,000 個事件）
- **背景 Worker** — 專用 `asyncio.Task` 持續從佇列取出事件並分派
- **順序處理** — 同一事件的 handlers 依序執行，避免並行競爭
- **非阻塞發射** — `emit()` 使用 `put_nowait()`，不等待處理完成
- **優雅關閉** — `stop()` 時處理完佇列中剩餘事件後才關閉

### 使用方式

```python
emitter = DeviceEventEmitter()
await emitter.start()  # 啟動背景 worker

# 註冊事件處理器
async def on_change(payload: ValueChangePayload):
    print(f"{payload.point_name}: {payload.old_value} -> {payload.new_value}")

cancel = emitter.on("value_change", on_change)

# 發射事件（非阻塞）
emitter.emit("value_change", ValueChangePayload(...))

# 取消訂閱
cancel()

# 停止
await emitter.stop()
```

### API

| 方法 | 說明 |
|------|------|
| `start()` | 啟動事件處理 worker |
| `stop()` | 停止 worker，處理剩餘事件後關閉 |
| `on(event, handler)` | 註冊處理器，回傳取消函數 |
| `emit(event, payload)` | 非阻塞發射事件 |
| `emit_await(event, payload)` | 阻塞發射，等待處理完成 |
| `has_listeners(event)` | 檢查是否有監聽器 |
| `clear(event)` | 清除處理器（None = 全部清除） |
| `queue_size` | 目前佇列中的事件數量 |

## 9 種事件類型

| 事件常數 | 事件名稱 | Payload 類別 | 觸發時機 |
|---------|---------|-------------|---------|
| `EVENT_CONNECTED` | `connected` | `ConnectedPayload` | 設備連線成功 |
| `EVENT_DISCONNECTED` | `disconnected` | `DisconnectPayload` | 設備斷線 |
| `EVENT_READ_COMPLETE` | `read_complete` | `ReadCompletePayload` | 讀取循環完成 |
| `EVENT_READ_ERROR` | `read_error` | `ReadErrorPayload` | 讀取失敗 |
| `EVENT_VALUE_CHANGE` | `value_change` | `ValueChangePayload` | 點位值變化 |
| `EVENT_ALARM_TRIGGERED` | `alarm_triggered` | `DeviceAlarmPayload` | 告警觸發 |
| `EVENT_ALARM_CLEARED` | `alarm_cleared` | `DeviceAlarmPayload` | 告警解除 |
| `EVENT_WRITE_COMPLETE` | `write_complete` | `WriteCompletePayload` | 寫入成功 |
| `EVENT_WRITE_ERROR` | `write_error` | `WriteErrorPayload` | 寫入失敗 |

### Payload 類別

所有 Payload 皆為 `frozen=True` 的 dataclass，確保事件資料不可變：

| Payload | 欄位 |
|---------|------|
| `ConnectedPayload` | `device_id`, `timestamp` |
| `DisconnectPayload` | `device_id`, `reason`, `consecutive_failures`, `timestamp` |
| `ReadCompletePayload` | `device_id`, `values`, `duration_ms`, `timestamp` |
| `ReadErrorPayload` | `device_id`, `error`, `consecutive_failures`, `timestamp` |
| `ValueChangePayload` | `device_id`, `point_name`, `old_value`, `new_value`, `timestamp` |
| `DeviceAlarmPayload` | `device_id`, `alarm_event`, `timestamp` |
| `WriteCompletePayload` | `device_id`, `point_name`, `value`, `timestamp` |
| `WriteErrorPayload` | `device_id`, `point_name`, `value`, `error`, `timestamp` |

## 事件流向

```
AsyncModbusDevice
    │
    ├── emit(CONNECTED)         ──→  DeviceManager (更新連線狀態)
    ├── emit(DISCONNECTED)      ──→  DeviceManager (觸發重連)
    ├── emit(READ_COMPLETE)     ──→  DataUploadManager (→ MongoDB)
    │                           ──→  StateSyncManager (→ Redis)
    ├── emit(READ_ERROR)        ──→  DeviceManager (連續失敗計數)
    ├── emit(VALUE_CHANGE)      ──→  自訂訂閱者
    ├── emit(ALARM_TRIGGERED)   ──→  AlarmPersistenceManager (→ MongoDB)
    │                           ──→  SystemController (Auto-Stop)
    ├── emit(ALARM_CLEARED)     ──→  AlarmPersistenceManager (→ MongoDB)
    │                           ──→  StateSyncManager (→ Redis)
    ├── emit(WRITE_COMPLETE)    ──→  WriteCommandManager (審計記錄)
    └── emit(WRITE_ERROR)       ──→  WriteCommandManager (錯誤記錄)
```

## 事件訂閱基底

[[DeviceEventSubscriber]]（`csp_lib.manager.base`）為 Manager 層的事件訂閱基底類別，提供統一的事件訂閱介面，簡化事件處理器的註冊。

## 設計考量

### 為何使用 Queue 而非直接回呼？

直接在 `emit()` 中 `await handler()` 會阻塞讀取循環。使用 Queue：
1. **解耦**：發射者不需等待處理完成
2. **背壓控制**：佇列滿時丟棄事件，避免記憶體爆炸
3. **順序保證**：同一事件的 handlers 按註冊順序執行

### emit vs emit_await

- `emit()` — 日常使用，非阻塞，適合高頻事件（如 `VALUE_CHANGE`）
- `emit_await()` — 重要事件需確保處理完成時使用（如 `ALARM_TRIGGERED`）

## 相關頁面

- [[DeviceEventEmitter]] — 事件發射器類別頁面
- [[AsyncModbusDevice]] — 事件發射的來源設備
- [[Async Patterns]] — 非同步模式總覽
- [[Data Flow]] — 事件在資料流中的角色
- [[_MOC Equipment]] — 設備模組索引
- [[_MOC Architecture]] — 返回架構索引
