---
tags:
  - type/protocol
  - layer/controller
  - status/complete
source: csp_lib/controller/system/schedule_mode.py
created: 2026-03-06
updated: 2026-04-04
version: ">=0.4.2"
---

# ScheduleModeController

排程模式控制協定，橋接 ScheduleService (Layer 5) 與 SystemController (Layer 6)。

> [!info] 回到 [[_MOC Controller]]

## 概述

`ScheduleModeController` 是一個 `@runtime_checkable Protocol`，定義排程模式的啟停介面。設計目的是讓 `ScheduleService`（Manager 層，Layer 5）能夠驅動模式切換，而**無需直接依賴** `SystemController`（Integration 層，Layer 6），從而遵守架構分層依賴方向。

```
ScheduleService (L5 Manager)
    ↓ 透過 ScheduleModeController Protocol
SystemController (L6 Integration)  ←  實作 ScheduleModeController
    ↓
ModeManager.update_mode_strategy()
    ↓
StrategyExecutor.set_strategy()
    ↓
心跳 / 級聯策略等正常運作
```

> [!important] 設計決策 D2
> `ScheduleModeController` 定義在 **Layer 4（Controller）**，因此 Layer 5 Manager 可以合法 import 它，而不需要直接依賴 Layer 6 Integration。這是橋接協定（Protocol Bridge）模式。

## 介面定義

```python
from typing import Protocol, runtime_checkable
from csp_lib.controller.core import Strategy

@runtime_checkable
class ScheduleModeController(Protocol):
    async def activate_schedule_mode(
        self,
        strategy: Strategy,
        *,
        description: str = "",
    ) -> None: ...

    async def deactivate_schedule_mode(self) -> None: ...
```

## 方法

### `activate_schedule_mode(strategy, *, description="")`

啟用排程模式。

- 首次呼叫時：在 `ModeManager` 中以 `"__schedule__"` 為名稱**自動註冊**模式，並設為 base mode
- 後續呼叫時：呼叫 `ModeManager.update_mode_strategy()`，**原子替換**策略並觸發 `on_strategy_change`，無需重新移除再新增

| 參數 | 型別 | 說明 |
|------|------|------|
| `strategy` | `Strategy` | 要啟用的排程策略實例 |
| `description` | `str` | 模式描述（審計用，通常為規則名稱，選填） |

### `deactivate_schedule_mode()`

停用排程模式。

從 base mode 列表中移除 `"__schedule__"` 模式。若目前排程模式不在 base mode 中，靜默不做任何動作。系統回退至其他仍在 base mode 的模式（如有）。

> [!note] 設計決策 D6
> 無匹配規則時呼叫 `deactivate_schedule_mode()`，而非 `unregister()`。這保留了 `__schedule__` 的模式定義，方便下次 `activate_schedule_mode()` 直接走 `update_mode_strategy()` 路徑，避免重新 register 的鎖序問題。

## 模式常數

`SystemController` 使用固定的 `__schedule__` 模式名稱（設計決策 D1），而非每條規則一個模式。這確保：

- 在任何時間點最多只有一個排程模式活躍
- 策略切換走 `update_mode_strategy()`（原子操作，含生命週期 hooks）
- 不需要 unregister → re-register 的繁瑣流程

## Import 路徑

```python
from csp_lib.controller.system.schedule_mode import ScheduleModeController
# 或透過 controller 頂層匯出
from csp_lib.controller import ScheduleModeController
```

## 實作

`SystemController` 已實作此協定，提供 `activate_schedule_mode()` 與 `deactivate_schedule_mode()` 兩個方法。詳見 [[SystemController#排程模式控制]]。

```python
from csp_lib.integration import SystemController

controller = SystemController(registry, config)
# isinstance 檢查有效（@runtime_checkable）
from csp_lib.controller import ScheduleModeController
assert isinstance(controller, ScheduleModeController)  # True
```

## 使用範例

### ScheduleService 的典型用法

```python
from csp_lib.manager import ScheduleService, ScheduleServiceConfig
from csp_lib.integration import SystemController

# SystemController 實作 ScheduleModeController Protocol
controller = SystemController(registry, config)

service = ScheduleService(
    config=ScheduleServiceConfig(site_id="site_001"),
    repository=mongo_repo,
    factory=StrategyFactory(pv_service=pv_svc),
    mode_controller=controller,   # 傳入 ScheduleModeController 實作
)

async with service:
    # ScheduleService 週期輪詢排程規則
    # 有匹配規則時 → mode_controller.activate_schedule_mode(strategy)
    # 無匹配規則時 → mode_controller.deactivate_schedule_mode()
    await asyncio.Event().wait()
```

### 自訂實作

若不使用 `SystemController`，可自行實作此 Protocol：

```python
class MyScheduleModeController:
    async def activate_schedule_mode(
        self, strategy: Strategy, *, description: str = ""
    ) -> None:
        # 自訂模式切換邏輯
        await self._mode_manager.update_mode_strategy("__schedule__", strategy)

    async def deactivate_schedule_mode(self) -> None:
        await self._mode_manager.remove_base_mode("__schedule__")
```

## 相關連結

- [[ModeManager]] — 底層模式管理，`update_mode_strategy()` / `async_unregister()` 由此提供
- [[SystemController]] — 內建的 `ScheduleModeController` 實作
- [[ScheduleStrategy]] — 排程策略類別（向後相容保留）
- [[Strategy]] — 策略抽象基底
