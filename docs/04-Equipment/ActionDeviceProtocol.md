---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/device/protocol.py
created: 2026-04-23
updated: 2026-04-23
version: ">=0.10.0"
---

# ActionDeviceProtocol

支援高階動作執行（`execute_action`）的設備協定，`DeviceProtocol` 的延伸。

> [!info] 回到 [[_MOC Equipment]]

## 概述

`ActionDeviceProtocol` 繼承 `DeviceProtocol`，額外宣告 `execute_action(action, **params)` 契約。

orchestrator / maintenance procedure 等需要觸發 action（如 `"start"`、`"stop"`、`"reset"`）的流程使用此型別，而非直接依賴 `AsyncModbusDevice` 具體類別。

`AsyncModbusDevice` 透過 `WriteMixin.execute_action` 結構性滿足此協定；`AsyncCANDevice` 等其他裝置可自行實作 `execute_action`。

> [!note] v0.10.0（PR #109）
> `orchestrator._execute_device_action` 從直接依賴 `AsyncModbusDevice` 改為接受
> `ActionDeviceProtocol`，允許 CAN 設備與其他裝置也能被 orchestrator 納管。

---

## Protocol 定義

```python
@runtime_checkable
class ActionDeviceProtocol(DeviceProtocol, Protocol):
    async def execute_action(self, action: str, **params: Any) -> Any: ...
```

`DeviceProtocol` 的完整介面（`device_id`, `is_connected`, `write`, `on` 等）全部繼承，詳見 [[DeviceProtocol]]。

### 額外方法

| 方法 | 說明 |
|------|------|
| `execute_action(action, **params)` | 執行高階動作（如 `"start"`, `"stop"`, `"reset"`）；回傳型別由實作決定 |

---

## Quick Example

### 在 orchestrator 中使用

```python
from csp_lib.equipment.device.protocol import ActionDeviceProtocol
from typing import Any

async def execute_device_action(
    device: ActionDeviceProtocol,
    action: str,
    **params: Any,
) -> Any:
    """型別安全地執行設備動作。"""
    assert isinstance(device, ActionDeviceProtocol)
    return await device.execute_action(action, **params)

# AsyncModbusDevice 結構性滿足 ActionDeviceProtocol
result = await execute_device_action(modbus_device, "start", timeout=5.0)
```

### runtime_checkable 型別判斷

```python
from csp_lib.equipment.device.protocol import ActionDeviceProtocol

devices = registry.get_devices_by_trait("actionable")
for device in devices:
    if isinstance(device, ActionDeviceProtocol):
        await device.execute_action("reset")
    else:
        logger.warning(f"{device.device_id} 不支援 execute_action，跳過")
```

### 自訂 ActionDeviceProtocol 實作

```python
from csp_lib.equipment.device.protocol import ActionDeviceProtocol
from typing import Any

class MockActionDevice:
    """測試用最小實作（結構性 satisfy ActionDeviceProtocol）。"""

    def __init__(self, device_id: str) -> None:
        self._device_id = device_id

    @property
    def device_id(self) -> str:
        return self._device_id

    # ... 其他 DeviceProtocol 成員 ...

    async def execute_action(self, action: str, **params: Any) -> Any:
        return {"status": "ok", "action": action}

assert isinstance(MockActionDevice("test"), ActionDeviceProtocol)
```

---

## Import 路徑

```python
from csp_lib.equipment.device.protocol import ActionDeviceProtocol

# 或從頂層匯入
from csp_lib.equipment.device import ActionDeviceProtocol
```

---

## 相關頁面

- [[DeviceProtocol]] — 基底 Protocol（`ActionDeviceProtocol` 繼承自此）
- [[AsyncModbusDevice]] — 結構性滿足 `ActionDeviceProtocol`
- [[DOActions]] — DO 動作配置（`execute_do_action`）
- [[_MOC Equipment]] — 回到模組總覽
