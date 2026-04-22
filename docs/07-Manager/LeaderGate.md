---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/base.py
created: 2026-04-23
updated: 2026-04-23
version: ">=0.10.0"
---

# LeaderGate

Leader 閘門 Protocol — 供 Manager 在 cluster / HA 部署下判斷是否應執行 leader-only 動作。

> [!info] 回到 [[_MOC Manager]]

## 概述

`LeaderGate` 是 `@runtime_checkable Protocol`，定義兩個成員：

| 成員 | 說明 |
|------|------|
| `is_leader: bool`（property） | 快速、非阻塞快照；**必須 O(1)**，不得有 I/O |
| `wait_until_leader()` | 啟動路徑用；非 leader 時 await 直到升格；允許 `CancelledError` |

所有接受 `leader_gate` 的 Manager（`UnifiedDeviceManager`、`WriteCommandManager`、`StateSyncManager`）都依賴此 Protocol。

### AlwaysLeaderGate

單節點部署用的 no-op 實作，`is_leader` 永遠為 `True`，`wait_until_leader()` 立刻返回。

```python
class AlwaysLeaderGate:
    @property
    def is_leader(self) -> bool:
        return True

    async def wait_until_leader(self) -> None:
        return None
```

---

## 各 Manager 的 leader_gate 行為

| Manager | 非 leader 時行為 |
|---------|----------------|
| `UnifiedDeviceManager` | `_on_start` 跳過 `device_manager.start()`（不連線/不讀取） |
| `WriteCommandManager` | `execute()` raise `NotLeaderError` |
| `StateSyncManager` | 所有事件 handler 早退，不寫 Redis、不發 Pub/Sub |

---

## Quick Example

### 單節點部署（不需 leader gate）

```python
from csp_lib.manager import UnifiedDeviceManager, UnifiedConfig

# 不傳 leader_gate → 視為永遠是 leader（等同 AlwaysLeaderGate）
manager = UnifiedDeviceManager(config)
```

### 注入 AlwaysLeaderGate（明確聲明）

```python
from csp_lib.manager import UnifiedDeviceManager, UnifiedConfig, AlwaysLeaderGate

manager = UnifiedDeviceManager(config, leader_gate=AlwaysLeaderGate())
```

### 自訂 LeaderGate（cluster 部署）

```python
from csp_lib.manager.base import LeaderGate
import asyncio

class EtcdLeaderGate:
    """以 etcd lease 實作的 LeaderGate（示意）。"""

    def __init__(self) -> None:
        self._is_leader = False
        self._became_leader = asyncio.Event()

    @property
    def is_leader(self) -> bool:
        return self._is_leader  # 背景 task 更新此旗標

    async def wait_until_leader(self) -> None:
        await self._became_leader.wait()

    def _on_leader_acquired(self) -> None:
        self._is_leader = True
        self._became_leader.set()

    def _on_leader_lost(self) -> None:
        self._is_leader = False
        self._became_leader.clear()

# 使用
gate = EtcdLeaderGate()
manager = UnifiedDeviceManager(config, leader_gate=gate)

async with manager:
    await asyncio.sleep(3600)
```

### 捕捉 NotLeaderError

```python
from csp_lib.core import NotLeaderError

try:
    result = await command_manager.execute(command)
except NotLeaderError as e:
    # 非 leader 節點收到寫入請求時
    logger.warning(f"指令 {e.operation} 被拒絕：{e}")
    # 可重路由到 leader 節點
```

---

## Protocol 型別檢查

```python
from csp_lib.manager.base import LeaderGate

gate = EtcdLeaderGate()
assert isinstance(gate, LeaderGate)  # @runtime_checkable
```

---

## Import 路徑

```python
from csp_lib.manager.base import LeaderGate, AlwaysLeaderGate

# 或從頂層 manager 匯入
from csp_lib.manager import AlwaysLeaderGate
```

---

## 相關頁面

- [[Error Hierarchy]] — `NotLeaderError`（leader gate 守門失敗時拋出）
- [[UnifiedDeviceManager]] — `leader_gate` kw-only 參數
- [[WriteCommandManager]] — `leader_gate` kw-only 參數
- [[StateSyncManager]] — `leader_gate` kw-only 參數
- [[_MOC Manager]] — 回到模組總覽
