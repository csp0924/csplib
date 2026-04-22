---
tags:
  - type/architecture
  - layer/manager
  - status/complete
created: 2026-04-23
updated: 2026-04-23
version: ">=0.10.0"
---

# Manager Layer（管理層總覽）

> Layer 5 — 設備生命週期、事件訂閱、外部儲存整合、Reconciler 對應關係。

本文提供 Manager 層的整體地圖；各 Manager 的 API 細節見 [[_MOC Manager]]。

## 一句話定位

Controller 做決策、Integration 串接一切，**Manager 負責「記錄、同步、整合外部世界」**：把設備讀值送進 MongoDB／Redis，把外部命令送進設備，排程切策略，且能在 HA 部署下由 [[LeaderGate]] 閘門決定誰有資格執行 leader-only I/O。

## 職責邊界

| 做什麼 | 不做什麼 |
|-------|---------|
| 訂閱 [[AsyncModbusDevice]] 事件（value_change、alarm_triggered、capability_added/removed） | 不跑控制策略（策略在 Controller 層） |
| 驅動設備生命週期（start/stop/connect/disconnect） | 不決定寫入值（寫入值由 Controller/外部 API 產生） |
| 把事件／讀值持久化到 MongoDB、即時狀態推到 Redis | 不定義 Modbus point / alarm 規則（定義在 Equipment 層） |
| 輪詢 Schedule repository、觸發策略切換 | 不自己組合 `SystemController`（組合在 Integration 層） |
| 拒絕非 leader 執行 leader-only 動作（cluster／HA 場景） | 不實作 leader election 本身（實作在 Additional 層 `cluster` 模組） |

## 架構總覽

```
                 Controller (L4) --------- Integration (L6)
                     ↓                           ↓
            ┌─────────────────────────────────────────────┐
            │             Manager Layer (L5)              │
            │                                             │
            │   ┌─────────── UnifiedDeviceManager ──────┐ │
            │   │  (Facade；組合下列所有子 manager)      │ │
            │   │                                       │ │
            │   │   ├─ DeviceManager ─────────────┐     │ │
            │   │   │   standalone / group 模式    │     │ │
            │   │   │                              │     │ │
            │   │   └─ DeviceEventSubscriber 子類 ─┤     │ │
            │   │       ├─ AlarmPersistenceManager│     │ │
            │   │       ├─ DataUploadManager      │     │ │
            │   │       ├─ WriteCommandManager    │     │ │
            │   │       └─ StateSyncManager       │     │ │
            │   └───────────────────────────────────┘     │
            │                                             │
            │   ScheduleService  (獨立，非 Unified 內)     │
            │     └─ 實作 Reconciler Protocol             │
            └─────────────────────────────────────────────┘
                           ↓
                 Equipment (L3)        Storage (L7)
                (AsyncModbusDevice)   (MongoDB / Redis)
```

## 依賴方向

- **Manager → Core**：統一用 [[AsyncLifecycleMixin]]、[[RuntimeParameters]]、[[Reconciler]] Protocol
- **Manager → Equipment**：接受 [[DeviceProtocol]]（泛化型別，可注入非 `AsyncModbusDevice` 的設備抽象）
- **Manager → Storage**：MongoDB／Redis client 由呼叫方注入，Manager 自身不建連線
- **Manager ⇄ Integration**：只透過 Protocol 反向呼叫（例：[[ScheduleModeController]]）；Integration 層負責組裝，Manager 層不 import `SystemController`
- **Manager → Controller**：`WriteCommandManager` 接收 [[WriteValidationRule]] Protocol（Equipment 層契約），不直接依賴 controller 具體類別

## 類別拓樸

### 共用基底與 Protocol

| 符號 | 類型 | 層級位置 | 角色 |
|------|------|---------|------|
| [[DeviceEventSubscriber]] | class | `csp_lib.manager.base` | 所有事件訂閱 Manager 的基底，提供 `subscribe(device)` + `_register_events` 骨架 |
| [[LeaderGate]] | `@runtime_checkable` Protocol | `csp_lib.manager.base` | HA/cluster 閘門；`AlwaysLeaderGate` 為單節點 no-op |
| [[ManagerDescribable]] | `@runtime_checkable` Protocol | `csp_lib.manager.base` | 統一觀測狀態介面；回傳 frozen `*Status` dataclass |
| [[MongoRepositoryBase]] | class | `csp_lib.manager.base` | 三個 Mongo Repository 共用樣板（ping/ensure_indexes 骨架） |
| [[BatchUploader]] | Protocol | `csp_lib.manager.base` | 批次上傳器介面，解耦 `MongoBatchUploader` 具體類別 |
| [[Reconciler]] | `@runtime_checkable` Protocol | `csp_lib.core.reconciler` | K8s 風 reconcile_once() 契約（Core 層；v0.10.0 從 integration 下移） |

### 子 Manager（Facade 之下）

| Manager | 訂閱事件 | 下游副作用 | leader_gate 支援 | describe() 支援 |
|---------|---------|-----------|-----------------|----------------|
| [[DeviceManager]] | 無（管生命週期，不訂閱值） | `device.start/stop/connect/disconnect`；部分失敗 resilient（`gather(return_exceptions=True)`） | — | P3 待補 |
| [[AlarmPersistenceManager]] | `alarm_triggered` / `alarm_cleared` / `capability_added` / `capability_removed` | `AlarmRepository.save_event`；`CAPABILITY_DEGRADED` 告警 | — | P3 待補 |
| [[DataUploadManager]] | `value_change` | 批次寫入 `MongoBatchUploader`（或 `buffered_uploader` opt-in） | — | 透過 `UnifiedDeviceManager.describe().upload_queue_depth` 聚合 |
| [[WriteCommandManager]] | 無（接受外部命令） | 跑 [[WriteValidationRule]] 鏈 → `device.write()`；`CommandRepository` 審計 | ✅（非 leader raise `NotLeaderError`） | 透過 `UnifiedDeviceManager.describe().command_queue_depth` 聚合 |
| [[StateSyncManager]] | `value_change` / `connected` / `disconnected` / `alarm_triggered` / `alarm_cleared` | Redis hset + expire + publish（v0.10.0 pipeline 批次） | ✅（非 leader 所有 handler 早退） | — |

### 統一入口 + 排程

| 類別 | 職責 | leader_gate | 實作 Protocol |
|------|------|-------------|--------------|
| [[UnifiedDeviceManager]] | 組合上述所有子 manager；提供 `register` / `register_group` / `unregister` 單一入口；outputs fan-out；capability traits 動態 refresh | ✅（非 leader 跳過 `device_manager.start()`；自動傳遞給 command/state 子 manager） | [[ManagerDescribable]]（回傳 `UnifiedManagerStatus`） |
| [[ScheduleService]] | 週期輪詢 schedule rule，透過 [[ScheduleModeController]] 驅動策略切換 | ✅（非 leader `_poll_loop` 跳過 `_poll_once`） | [[Reconciler]]（`reconcile_once` + `ReconcilerStatus`） |

## Reconciler 對應關係

Reconciler 模式的核心是**「把 desired state 往 actual state 收斂，每次呼叫冪等、不 raise」**。Manager 層目前的 Reconciler 分佈：

### 已實作 Reconciler Protocol（v0.10.0）

| 實作類別 | `reconcile_once()` 在做什麼 | `status.detail` 欄位 |
|---------|------------------------------|---------------------|
| [[ScheduleService]] | 查詢 active rule → 比對 `current_rule_key` → 呼叫 `mode_controller.activate/deactivate_schedule_mode` | `action`：`no_match` / `deactivated` / `unchanged` / `switched` / `factory_failed` |

### 概念上對應但未實作 Protocol

| Manager | 「若做成 Reconciler」的 desired vs actual | 為何目前不做 |
|---------|------------------------------------------|-------------|
| `DeviceManager` | desired = `device_registry` 的 device list；actual = `_started_devices` 集合 | 啟動只跑一次；不是週期 loop |
| `AlarmPersistenceManager` | desired = `device.alarm_state_manager.active_alarms`；actual = Mongo 上 active 告警 | 純事件驅動，無需主動輪詢收斂 |
| `DataUploadManager` / `StateSyncManager` | desired = 最新 `value_change` 事件；actual = Mongo/Redis 上的值 | 同上，事件驅動，沒有 drift 檢測 |
| `WriteCommandManager` | desired = 命令 queue；actual = 設備 register | 已由 Integration 層 [[CommandRefreshService]] 處理 drift，不在 Manager 層重做 |

> 設計取向：**Reconciler 模式只用在有明確「期望態 vs 實際態差距可能漂移」的地方**。純事件驅動的 manager 硬套 reconciler 只會增加樣板，不會提升正確性。

### 和 Integration 層 Reconciler 的關係

| Reconciler | 層級 | 解決的 drift |
|-----------|------|-------------|
| [[ScheduleService]] | Manager (L5) | 時間／規則變更未觸發策略切換 |
| [[CommandRefreshService]] | Integration (L6) | 設備 register 被斷線／外部寫入污染，與 `_last_written` 不符 |
| `HeartbeatService` | Integration (L6) | 心跳信號未持續寫入外部看門狗 |
| `SetpointDriftReconciler` | Integration (L6) | PCS 類設定值讀回不等於寫入值時重寫 |

所有 Reconciler 都實作同一個 [[Reconciler]] Protocol（Core 層），可以被 `SystemController.describe()` 統一聚合健康狀態（後續 [[Operator Pattern]] 主題會擴充）。

## LeaderGate 閘門點

HA 部署下，**寫外部世界的 I/O 必須 leader 化**，避免雙主（split-brain）同時寫 Redis / 同時送寫命令給設備。Manager 層的閘門落點：

```
                 ┌───────────────────────────────┐
                 │ UnifiedDeviceManager._on_start│
 is_leader = F ─►│ 跳過 device_manager.start()   │─► 設備不連線／不讀取
                 └───────────────────────────────┘

                 ┌───────────────────────────────┐
                 │ WriteCommandManager.execute() │
 is_leader = F ─►│ raise NotLeaderError          │─► 呼叫端（Gateway API）回 4xx
                 └───────────────────────────────┘

                 ┌───────────────────────────────┐
                 │ StateSyncManager._on_*        │
 is_leader = F ─►│ 全 handler 早退               │─► 不寫 Redis、不發 Pub/Sub
                 └───────────────────────────────┘

                 ┌───────────────────────────────┐
                 │ ScheduleService._poll_loop    │
 is_leader = F ─►│ 跳過 _poll_once，迴圈持續     │─► 升格後立刻恢復輪詢
                 └───────────────────────────────┘
```

實作物放在 Additional 層 `cluster`（Redis-backed `RedisLeaderGate`）；單節點部署用 `AlwaysLeaderGate`（或 `leader_gate=None`，與 `AlwaysLeaderGate` 等價）。

## ManagerDescribable 觀測介面

v0.10.0 引入 [[ManagerDescribable]] Protocol，統一 Manager 對外觀測狀態的回傳格式：

```python
class ManagerDescribable(Protocol):
    def describe(self) -> Mapping[str, Any]: ...
```

目前首個落地為 [[UnifiedDeviceManager]] → `UnifiedManagerStatus`（frozen dataclass）：

| 欄位 | 型別 | 含義 |
|------|------|------|
| `devices_count` | `int` | 目前註冊設備總數 |
| `running` | `bool` | `_on_start` 是否已完成 |
| `is_leader` | `bool \| None` | `None` 代表無 leader_gate（單節點） |
| `alarms_active_count` | `int` | 活躍告警總數 |
| `command_queue_depth` | `int \| None` | 尚待執行命令數；未啟用 WriteCommandManager 時為 None |
| `upload_queue_depth` | `int \| None` | 批次上傳 queue 長度；未啟用時為 None |
| `state_sync_enabled` | `bool` | StateSyncManager 是否啟用 |
| `statistics_enabled` | `bool` | StatisticsManager 是否啟用 |

後續規劃（P3）：子 manager 各自補 `describe()` 以精確填充 `command_queue_depth` / `upload_queue_depth`；目前先回 `None` 佔位，由 `UnifiedDeviceManager.describe()` 聚合。

## MongoRepositoryBase 收斂

三個 Mongo Repository（`MongoAlarmRepository` / `MongoCommandRepository` / `MongoScheduleRepository`）原本 `__init__` 樣板完全相同、`health_check()` 實作完全相同。v0.10.0 引入 [[MongoRepositoryBase]] 收斂：

```python
class MongoRepositoryBase:
    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str) -> None:
        self._db = db
        self._collection = db[collection_name]

    async def health_check(self) -> HealthReport:
        await self._db.command("ping")
        return HealthReport(status="ok", ...)

    async def ensure_indexes(self) -> None:  # abstractmethod
        raise NotImplementedError
```

三個既有 repo 改繼承此基底，刪除重複樣板。`MongoCommandRepository.__init__(..., collection: str = ...)` kwarg 與另外兩個不一致，保留 `collection=` 為 deprecated alias，v1.0 統一 → 已加進 Breaking Pipeline。

## 設計慣例

### 型別鬆綁：接受 DeviceProtocol

v0.9.1 起所有 Manager `register(device)` 參數改為 [[DeviceProtocol]]（而非 `AsyncModbusDevice`），讓 `DerivedDevice`、`RemoteSnapshotDevice`、mock device 都能注入。

### 部分失敗 resilient（bug-lesson: partial-failure-gather）

`DeviceManager._on_start` / `_on_stop` 使用 `asyncio.gather(return_exceptions=True)` per-device，單台失敗不阻擋其他設備；`CancelledError` 仍向上傳播。

### capability 追蹤

`UnifiedDeviceManager` 訂閱 `device.events.capability_added/removed`，自動呼叫 [[DeviceRegistry]]`.refresh_capability_traits(device_id)`；同時 `AlarmPersistenceManager` 寫 `CAPABILITY_DEGRADED` WARNING 告警，capability 恢復時解除。

### 命令寫入鏈

[[WriteCommandManager]].`execute()` 的完整鏈路（v0.10.0）：

```
leader_gate.is_leader? ──► repository.create(PENDING)
                              ↓
                       device_id 解析
                              ↓
                       WriteValidationRule 鏈
                              ├─ reject → VALIDATION_FAILED
                              └─ accept/clamp ↓
                       EXECUTING → device.write(effective_value)
                              ├─ success → COMPLETED
                              └─ exception → FAILED
```

## 快速入門

### 單節點最簡例

```python
from csp_lib.manager import UnifiedDeviceManager, UnifiedConfig
from csp_lib.manager import UploadTarget  # fan-out 目標

async with UnifiedDeviceManager(
    devices=[pcs_device, meter_device],
    config=UnifiedConfig(...),
) as udm:
    status = udm.describe()
    print(f"running={status.running}, devices={status.devices_count}")
```

### HA 部署加 leader_gate

```python
from csp_lib.cluster import RedisLeaderGate  # cluster extra 需先 install

gate = RedisLeaderGate(redis_client, site_id="plant_001")

async with UnifiedDeviceManager(
    devices=[...],
    config=UnifiedConfig(...),
    leader_gate=gate,   # 自動傳給 command / state 子 manager
) as udm:
    ...
```

### 加排程

```python
from csp_lib.manager import ScheduleService, ScheduleServiceConfig

async with ScheduleService(
    config=ScheduleServiceConfig(site_id="plant_001", poll_interval=30.0),
    repository=mongo_schedule_repo,
    factory=strategy_factory,
    mode_controller=system_controller,
    leader_gate=gate,
) as svc:
    # svc 實作 Reconciler Protocol
    print(svc.status)   # ReconcilerStatus(run_count=3, last_error=None, detail={"action": "switched"})
```

## 相關頁面

- [[_MOC Manager]] — Manager 模組完整索引
- [[Layered Architecture]] — 八層分層總覽
- [[Reconciliation Pattern]] — Reconciler 模式深入解析（`CommandRefreshService` 案例）
- [[Reconciler]] — Core 層 Protocol 定義
- [[Operator Pattern]] — Kubernetes Operator 式組裝（`SystemControllerConfigBuilder.from_manifest()`）
- [[Data Flow]] — 跨層資料流（設備讀值 → Manager → Storage）
- [[Event System]] — `AsyncModbusDevice` 事件系統（Manager 訂閱來源）
