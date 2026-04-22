---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/schedule/service.py
created: 2026-03-06
updated: 2026-04-23
version: ">=0.10.0"
---

# ScheduleService

排程服務，週期性輪詢排程規則並驅動策略切換。

> [!info] 回到 [[_MOC Manager]]

## 概述

`ScheduleService` 週期性從 `ScheduleRepository` 查詢目前時間匹配的排程規則，透過 `StrategyFactory` 建立對應的策略實例，再透過 [[ScheduleModeController]] Protocol 走 `ModeManager` 正規路徑進行策略切換。

繼承 `AsyncLifecycleMixin`，支援 `async with` 使用。

### 控制路徑

```
ScheduleService._poll_loop()
    ↓ 每 poll_interval 秒
ScheduleRepository.find_active_rules(site_id, now)
    ↓ 取最高 priority 規則
StrategyFactory.create(strategy_type, strategy_config)
    ↓ 取得策略實例
ScheduleModeController.activate_schedule_mode(strategy)
    ↓ 透過 Protocol 橋接（不直接依賴 Integration 層）
SystemController → ModeManager.update_mode_strategy()
    ↓
StrategyExecutor.set_strategy()
```

> [!important] v0.4.2 破壞性變更
> `ScheduleService.__init__` 的 `schedule_strategy` 參數已改為 `mode_controller`。
> 舊版接受 `ScheduleStrategy` 實例；新版接受實作 [[ScheduleModeController]] Protocol 的物件（通常為 `SystemController`）。

## 概述補充（v0.10.0）

`ScheduleService` 現在實作 [[Reconciler]] Protocol（透過 `ReconcilerMixin`）：

- `reconcile_once()` → 執行一次排程輪詢（`_poll_once`）
- `status` → 回傳 `ReconcilerStatus`（`run_count`、`last_error`、`detail["action"]`）
- `detail["action"]` 為 `ScheduleAction` 字串值：`"no_match"` / `"deactivated"` / `"unchanged"` / `"switched"` / `"factory_failed"`

可納入 `SystemController.describe()` 聚合 Reconciler 狀態，統一對外報告排程輪詢的健康狀況。

---

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `config` | `ScheduleServiceConfig` | 服務配置（site_id、輪詢間隔、時區） |
| `repository` | `ScheduleRepository` | 排程規則資料存取層 |
| `factory` | `StrategyFactory` | 策略工廠 |
| `mode_controller` | `ScheduleModeController` | 排程模式控制器（通常為 `SystemController` 實例） |
| `leader_gate` | [[LeaderGate]] `\| None`（kw-only） | Leader 閘門（v0.10.0）；非 leader 時 `reconcile_once()` 早退不輪詢 |

## ScheduleServiceConfig

`@dataclass(frozen=True)` 的服務配置。

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `site_id` | `str` | （必填） | 站點識別碼（不可為空） |
| `poll_interval` | `float` | `30.0` | 輪詢間隔（秒，必須大於 0） |
| `timezone_name` | `str` | `"Asia/Taipei"` | 時區名稱（`zoneinfo` 格式） |

## 方法與屬性

| 成員 | 說明 |
|------|------|
| `current_rule_key` | 當前生效規則的唯一識別鍵（`None` 表示無活躍規則） |
| `reconcile_once()` | 執行一次排程輪詢，回傳 `ReconcilerStatus`（實作 Reconciler Protocol） |
| `name` | `"schedule-service"`（Reconciler Protocol 識別名） |
| `status` | 最新 `ReconcilerStatus` 快照 |

生命週期繼承自 `AsyncLifecycleMixin`（`async with` / `start()` / `stop()`）。

## ScheduleRule

| 欄位 | 型別 | 說明 |
|------|------|------|
| `name` | `str` | 規則名稱 |
| `site_id` | `str` | 站點識別碼 |
| `schedule_type` | `ScheduleType` | 排程類型（`ONCE` / `DAILY` / `WEEKLY`） |
| `strategy_type` | `StrategyType` | 策略類型（`PQ` / `PV_SMOOTH` / `QV` / `FP` / `ISLAND` / `BYPASS` / `STOP`） |
| `strategy_config` | `dict[str, Any]` | 策略配置字典（傳入 `StrategyFactory.create()`） |
| `start_time` | `str` | 開始時間（`"HH:MM"` 格式） |
| `end_time` | `str` | 結束時間（`"HH:MM"` 格式） |
| `priority` | `int` | 優先順序（數字越大越優先，同時有多條規則時取最高） |
| `enabled` | `bool` | 是否啟用 |
| `days_of_week` | `list[int]` | WEEKLY 排程的星期幾（0=Mon … 6=Sun） |
| `start_date` | `date \| None` | ONCE 排程的開始日期 |
| `end_date` | `date \| None` | ONCE 排程的結束日期 |

## StrategyType 列舉

| 值 | 對應策略 |
|----|---------|
| `PQ` | `PQModeStrategy` |
| `PV_SMOOTH` | `PVSmoothStrategy` |
| `QV` | `QVStrategy` |
| `FP` | `FPStrategy` |
| `ISLAND` | `IslandModeStrategy` |
| `BYPASS` | `BypassStrategy` |
| `STOP` | `StopStrategy` |

## 輪詢邏輯

1. 每 `poll_interval` 秒呼叫一次 `_poll_once()`
2. 以 `timezone_name` 確定當前時間，呼叫 `repository.find_active_rules(site_id, now)`
3. 若**無匹配規則**且當前有活躍規則：呼叫 `mode_controller.deactivate_schedule_mode()`，清除 `current_rule_key`
4. 若**有匹配規則**：取最高 priority 規則，生成 rule_key（`name | type | priority | config_json`）
   - 若 rule_key **未改變**：跳過，避免不必要的策略重建
   - 若 rule_key **已改變**：建立新策略，呼叫 `mode_controller.activate_schedule_mode(strategy, description=...)`，更新 `current_rule_key`

> [!note] 冪等性
> 相同規則連續輪詢不會觸發重複的策略切換，因為 `rule_key` 比對會跳過無變化的情況。

## 使用範例

```python
from csp_lib.manager import ScheduleService, ScheduleServiceConfig
from csp_lib.manager.schedule import StrategyFactory
from csp_lib.integration import SystemController, SystemControllerConfig
from csp_lib.controller.services import PVDataService

# 假設已建立 mongo_repo (MongoScheduleRepository) 與 system_controller
pv_service = PVDataService(max_history=300)
factory = StrategyFactory(pv_service=pv_service)

service = ScheduleService(
    config=ScheduleServiceConfig(
        site_id="plant_001",
        poll_interval=30.0,       # 每 30 秒輪詢一次
        timezone_name="Asia/Taipei",
    ),
    repository=mongo_repo,
    factory=factory,
    mode_controller=system_controller,  # SystemController 實作 ScheduleModeController
)

async with service:
    await asyncio.Event().wait()
```

## 相關頁面

- [[Reconciler]] — 實作的 Protocol（v0.10.0 從 integration 下移 core）
- [[ScheduleModeController]] — 服務使用的協定橋接介面
- [[SystemController]] — 實作 `ScheduleModeController` 的控制器
- [[ModeManager]] — 底層模式管理，`update_mode_strategy()` 由此提供
- [[LeaderGate]] — Leader 閘門 Protocol（v0.10.0）
- [[DeviceEventSubscriber]] — Manager 基底類別
