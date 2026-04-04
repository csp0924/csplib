---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/base.py
updated: 2026-04-04
version: ">=0.4.2"
---

# DeviceEventSubscriber

所有 Manager 的基底類別，隸屬於 [[_MOC Manager|Manager 模組]]。

## 概述

`DeviceEventSubscriber` 提供通用的設備事件訂閱管理框架。子類別只需覆寫 `_register_events()` 即可定義要訂閱的事件，取消訂閱時可覆寫 `_on_unsubscribe()` 進行額外清理。

內部維護一個 `dict[str, list[Callable]]`，以 `device_id` 為 key 管理各設備的取消訂閱 callback。

## AsyncRepository Protocol

`csp_lib/manager/base.py` 同時定義了 `AsyncRepository` — 所有 Repository 介面的共同基底，定義健康檢查方法。

```python
@runtime_checkable
class AsyncRepository(Protocol):
    async def health_check(self) -> bool:
        """檢查 Repository 連線是否正常"""
        ...
```

`AlarmRepository`、`CommandRepository`、`ScheduleRepository` 皆符合此 Protocol。

## API

| 方法 | 說明 |
|------|------|
| `subscribe(device)` | 訂閱設備事件；已訂閱時不重複訂閱 |
| `unsubscribe(device)` | 取消訂閱設備事件；尚未訂閱時不做任何操作 |

### 子類別需覆寫

| 方法 | 說明 |
|------|------|
| `_register_events(device) -> list[Callable]` | 註冊設備事件，回傳取消訂閱的 callback 列表（必須覆寫） |
| `_on_unsubscribe(device_id)` | 取消訂閱後的額外清理（可選覆寫） |

## 使用範例

```python
class MyManager(DeviceEventSubscriber):
    def _register_events(self, device: AsyncModbusDevice) -> list[Callable[[], None]]:
        return [
            device.on("event_a", self._on_event_a),
            device.on("event_b", self._on_event_b),
        ]
```

## 繼承關係

以下 Manager 皆繼承自 `DeviceEventSubscriber`：

- [[AlarmPersistenceManager]]
- [[DataUploadManager]]
- [[StateSyncManager]]

## 相關頁面

- [[_MOC Manager]] — Manager 模組總覽
