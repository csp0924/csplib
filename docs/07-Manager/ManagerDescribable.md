---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/unified.py
created: 2026-04-23
updated: 2026-04-23
version: ">=0.10.0"
---

# ManagerDescribable

統一 Manager 對外暴露觀測狀態的介面 Protocol，以及 `UnifiedDeviceManager` 的觀測快照 `UnifiedManagerStatus`。

> [!info] 回到 [[_MOC Manager]]

## 概述

`ManagerDescribable` 是 `@runtime_checkable Protocol`，要求實作 `describe() -> object` 方法，回傳當前 manager 的不可變觀測快照，供外部 GUI / Monitor / Cluster 狀態報告使用。

`UnifiedManagerStatus` 是 `UnifiedDeviceManager.describe()` 的具體回傳型別。

---

## ManagerDescribable Protocol

```python
@runtime_checkable
class ManagerDescribable(Protocol):
    def describe(self) -> object: ...
```

### 契約

| 項目 | 說明 |
|------|------|
| `describe()` | 必須是 O(1)~O(n_devices) 的快照讀取；**不得 I/O、不得 await** |
| 回傳值 | 應為 frozen dataclass 或 immutable Mapping；caller 不得改動 |
| 非 leader / 未啟動 | 仍應回傳合法結構（欄位可 0 或 False） |

---

## UnifiedManagerStatus

`UnifiedDeviceManager.describe()` 的回傳型別。

```python
@dataclass(frozen=True, slots=True)
class UnifiedManagerStatus:
    devices_count: int
    running: bool
    is_leader: bool | None
    alarms_active_count: int | None
    command_queue_depth: int | None
    upload_queue_depth: int | None
    state_sync_enabled: bool
    statistics_enabled: bool
```

### 欄位說明

| 欄位 | 型別 | 說明 |
|------|------|------|
| `devices_count` | `int` | 目前註冊的設備總數（standalone + group 內） |
| `running` | `bool` | Manager 是否處於執行中 |
| `is_leader` | `bool \| None` | 當前 leader 狀態；`None` 代表未注入 `leader_gate` |
| `alarms_active_count` | `int \| None` | 活躍告警數量；`None` 代表未配置 alarm_manager |
| `command_queue_depth` | `int \| None` | 寫入指令佇列深度（暫時回 `None`，待子 manager 補 describe） |
| `upload_queue_depth` | `int \| None` | 上傳佇列深度（同上） |
| `state_sync_enabled` | `bool` | 是否啟用 StateSyncManager |
| `statistics_enabled` | `bool` | 是否啟用 StatisticsManager |

---

## Quick Example

### 取得 UnifiedDeviceManager 觀測快照

```python
from csp_lib.manager import UnifiedDeviceManager, UnifiedConfig

manager = UnifiedDeviceManager(config, leader_gate=gate)

# 查詢觀測狀態（不 await，O(1) 快照）
status = manager.describe()
print(f"設備數: {status.devices_count}")
print(f"執行中: {status.running}")
print(f"是 leader: {status.is_leader}")
print(f"活躍告警: {status.alarms_active_count}")
```

### 在 Monitor 中週期回報

```python
import asyncio
from csp_lib.manager.base import ManagerDescribable

async def report_status(manager: ManagerDescribable, interval: float = 30.0) -> None:
    while True:
        status = manager.describe()
        # 傳送到監控系統
        await send_metrics({"devices": status.devices_count, "healthy": status.running})
        await asyncio.sleep(interval)
```

### runtime_checkable 型別判斷

```python
from csp_lib.manager.base import ManagerDescribable

assert isinstance(manager, ManagerDescribable)  # UnifiedDeviceManager 實作此 Protocol
```

---

## Import 路徑

```python
from csp_lib.manager.base import ManagerDescribable
from csp_lib.manager import UnifiedDeviceManager, UnifiedManagerStatus
```

---

## 相關頁面

- [[UnifiedDeviceManager]] — 實作 `ManagerDescribable` 的統一入口
- [[LeaderGate]] — `is_leader` 狀態來源
- [[_MOC Manager]] — 回到模組總覽
