---
tags:
  - type/class
  - layer/core
  - status/complete
source: csp_lib/core/reconciler.py
created: 2026-04-23
updated: 2026-04-23
version: ">=0.10.0"
---

# Reconciler

Kubernetes 風 Reconciler Protocol — 把 desired state 往 actual state 收斂的抽象介面。

> [!info] 回到 [[_MOC Core]]

## 概述

`csp_lib.core.reconciler` 提供三個公開符號：

| 符號 | 型別 | 說明 |
|------|------|------|
| `Reconciler` | `@runtime_checkable Protocol` | 定義 `name` / `status` / `reconcile_once()` 的最小契約 |
| `ReconcilerStatus` | `@dataclass(frozen=True, slots=True)` | 單次執行後的觀測快照 |
| `ReconcilerMixin` | 共用基底 Mixin | 提供 scaffold：計數、例外捕捉、狀態更新 |

### 設計哲學

- 概念來自 K8s Controller/Operator Pattern：每次 `reconcile_once()` 僅處理「現在和期望的差距」，冪等且不 raise。
- 生命週期（start/stop）不在 Protocol 之內，由 `AsyncLifecycleMixin` 提供。
- 命名為 `Reconciler` 而非 `Operator`，避免與 `csp_lib.equipment.alarm.evaluator.Operator`（Enum）衝突。

> [!note] v0.10.0：Protocol 下移 core
> `Reconciler` / `ReconcilerMixin` / `ReconcilerStatus` 原本在 `csp_lib.integration`，
> PR #113 將其下移至 `csp_lib.core`。`csp_lib.integration` 保留 re-export，舊 import 不受影響。

---

## ReconcilerStatus

```python
@dataclass(frozen=True, slots=True)
class ReconcilerStatus:
    name: str
    last_run_at: float | None = None   # monotonic timestamp；None 代表尚未執行
    last_error: str | None = None       # 最近一次失敗摘要；成功則 None
    run_count: int = 0
    healthy: bool = True
    detail: Mapping[str, Any] = field(default_factory=_empty_mapping)
```

對應 K8s `.status` subresource。`detail` 為 reconciler-specific 唯讀 Mapping（例如 `{"drift_count": 3}`）。

### 工廠方法

| 方法 | 說明 |
|------|------|
| `ReconcilerStatus.empty(name)` | 建立尚未 reconcile 過的初始狀態 |

---

## Reconciler Protocol

```python
@runtime_checkable
class Reconciler(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def status(self) -> ReconcilerStatus: ...

    async def reconcile_once(self) -> ReconcilerStatus: ...
```

### 契約

| 項目 | 說明 |
|------|------|
| `name` | 穩定的 logical identifier（用於 logging / metrics / status 聚合） |
| `status` | 唯讀快照，不觸發 reconcile |
| `reconcile_once()` | 執行一次收斂；**不得 raise**（`CancelledError` 除外）；idempotent |

---

## ReconcilerMixin

提供 `reconcile_once()` 的共用 scaffold，讓子類只需實作 `_reconcile_work()` 即可：

```python
class MyReconciler(ReconcilerMixin, AsyncLifecycleMixin):
    def __init__(self) -> None:
        self._init_reconciler("my-reconciler")

    async def _reconcile_work(self, detail: dict[str, Any]) -> None:
        # 把 diagnostic metadata 寫入 detail
        detail["items_checked"] = 42
        # 執行收斂邏輯 ...
```

### Scaffold 行為

1. 遞增 `_run_count`
2. 呼叫 `_reconcile_work(detail)` — mutable dict，子類邊做邊寫入
3. 吞掉 `Exception`，記錄於 `last_error`；`CancelledError` 仍傳播
4. detail **無論成功或失敗都會快照**（支援 partial failure 觀察）
5. 更新 `self._status`（`ReconcilerStatus`）

### 子類約定

| 項目 | 說明 |
|------|------|
| `__init__` 呼叫 | `self._init_reconciler(name)` |
| 覆寫 | `async def _reconcile_work(detail: dict[str, Any]) -> None` |
| 寫入 detail | 邊做邊寫，失敗前的部分進度仍保留 |

---

## Quick Example

### 實作自訂 Reconciler

```python
from typing import Any

from csp_lib.core import AsyncLifecycleMixin, ReconcilerMixin

class SetpointSyncReconciler(ReconcilerMixin, AsyncLifecycleMixin):
    """每輪比對設備 setpoint，若漂移則重送。"""

    def __init__(self, device, desired_p: float) -> None:
        self._init_reconciler("setpoint-sync")
        self._device = device
        self._desired_p = desired_p

    async def _on_start(self) -> None:
        import asyncio
        while True:
            await self.reconcile_once()
            await asyncio.sleep(5.0)

    async def _reconcile_work(self, detail: dict[str, Any]) -> None:
        current_p = self._device.latest_values.get("active_power", 0.0)
        drift = abs(current_p - self._desired_p)
        detail["drift"] = drift
        if drift > 10.0:
            await self._device.write("setpoint_p", self._desired_p)
            detail["corrected"] = True

async def main():
    reconciler = SetpointSyncReconciler(device, desired_p=500.0)
    async with reconciler:
        pass  # 自動迴圈

    status = reconciler.status
    print(status.run_count, status.healthy, status.detail)
```

### 查詢狀態

```python
from csp_lib.core import ReconcilerStatus

status: ReconcilerStatus = reconciler.status
print(f"執行次數: {status.run_count}")
print(f"健康: {status.healthy}")
print(f"最近錯誤: {status.last_error}")
print(f"詳細: {dict(status.detail)}")
```

### 使用 Protocol 型別檢查

```python
from csp_lib.core import Reconciler

def register_reconciler(r: Reconciler) -> None:
    # @runtime_checkable — 支援 isinstance 檢查
    assert isinstance(r, Reconciler)
    print(f"Registered: {r.name}")
```

---

## Import 路徑

```python
# 建議從 csp_lib.core 直接 import
from csp_lib.core import Reconciler, ReconcilerMixin, ReconcilerStatus

# csp_lib.integration 保留 re-export（向後相容）
from csp_lib.integration import Reconciler, ReconcilerStatus
```

---

## 常見模式

### 納入 SystemController 聚合

`SystemController` 可蒐集實作 `Reconciler` 的服務（如 `ScheduleService`）狀態，
對外透過 `describe()` 統一彙報：

```python
# ScheduleService 實作 Reconciler Protocol
from csp_lib.manager import ScheduleService

service = ScheduleService(...)
# service.status → ReconcilerStatus
# service.reconcile_once() → 執行一次排程輪詢
```

---

## Gotchas / Tips

> [!warning] `CancelledError` 必須傳播
> `ReconcilerMixin` 只吞 `Exception`，`CancelledError` 仍向上拋。
> 自訂 `_reconcile_work` 時不得 `except BaseException` 吞掉取消信號。

> [!tip] detail 是偵錯工具
> 把每輪的診斷資訊寫入 `detail`，失敗時保留 raise 前已寫入的部分，
> 讓 `status.detail` 成為 post-mortem 的第一手資料。

> [!note] 週期性執行不在 Protocol 之內
> `Reconciler` 只定義「執行一次收斂」的介面，迴圈由外層（`AsyncLifecycleMixin` Task）負責。

---

## 相關頁面

- [[AsyncLifecycleMixin]] — 提供週期迴圈與 start/stop 生命週期
- [[_MOC Core]] — Core 模組總覽
- [[ScheduleService]] — `ReconcilerMixin` 實作範例
