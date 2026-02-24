---
tags: [type/class, layer/core, status/complete]
source: csp_lib/core/lifecycle.py
---
# AsyncLifecycleMixin

> 非同步生命週期管理基底類別

回到 [[_MOC Core]]

## 概述

`AsyncLifecycleMixin` 提供標準的非同步 `start`/`stop` 生命週期框架，並實作 `async with` 語法（async context manager）。子類別只需覆寫 `_on_start()` 與 `_on_stop()` 模板方法即可自訂啟停邏輯。

此模式廣泛應用於所有需要生命週期管理的元件，包含設備管理器、控制迴路、資料上傳器等。

## 類別介面

| 方法 | 說明 |
|------|------|
| `async start()` | 啟動服務，內部呼叫 `_on_start()` |
| `async stop()` | 停止服務，內部呼叫 `_on_stop()` |
| `async _on_start()` | 模板方法 — 子類別覆寫以實作啟動邏輯 |
| `async _on_stop()` | 模板方法 — 子類別覆寫以實作停止邏輯 |
| `async __aenter__()` | 呼叫 `start()` 並回傳 `self` |
| `async __aexit__()` | 呼叫 `stop()` |

## 使用範例

```python
from csp_lib.core import AsyncLifecycleMixin

class MyService(AsyncLifecycleMixin):
    async def _on_start(self) -> None:
        ...  # 啟動邏輯

    async def _on_stop(self) -> None:
        ...  # 清理邏輯

async with MyService() as svc:
    ...  # 服務運行中
```

## 設計模式

此類別運用了**模板方法模式（Template Method Pattern）**：

1. 基底類別定義骨架流程（`start` -> `_on_start`、`stop` -> `_on_stop`）
2. 子類別覆寫 hook 方法來填入具體實作
3. `async with` 語法保證資源正確釋放

詳見 [[Design Patterns]]。

## 使用此 Mixin 的元件

- `AsyncModbusDevice`（設備層）
- `GridControlLoop`（整合層控制迴路）
- `UnifiedDeviceManager`（管理層統一管理器）
- 各種 Manager 類別（`DeviceManager`、`AlarmPersistenceManager` 等）
