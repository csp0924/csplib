---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/unified.py
created: 2026-02-17
updated: 2026-04-23
version: ">=0.10.0"
---

# UnifiedDeviceManager

統一設備管理器，隸屬於 [[_MOC Manager|Manager 模組]]。

## 概述

`UnifiedDeviceManager` 整合 [[DeviceManager]]、[[AlarmPersistenceManager]]、[[WriteCommandManager]]、[[DataUploadManager]]、[[StateSyncManager]]、`StatisticsManager`，提供單一入口點。繼承 `AsyncLifecycleMixin`，支援 `async with` 使用。

註冊設備後自動串接所有已啟用的功能，使用者無需手動 subscribe 各子管理器。

## UnifiedConfig

所有子管理器皆為可選，未配置的功能將自動跳過。

> [!note] v0.7.1 frozen=True
> `UnifiedConfig` 現在使用 `@dataclass(frozen=True, slots=True)`，建立後不可修改。

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `alarm_repository` | `AlarmRepository \| None` | `None` | 告警持久化 Repository |
| `command_repository` | `CommandRepository \| None` | `None` | 寫入指令 Repository |
| `batch_uploader` | [[BatchUploader]] `\| None` | `None` | 批次上傳器（推薦使用） |
| `mongo_uploader` | [[BatchUploader]] `\| None` | `None` | **Deprecated**，請改用 `batch_uploader`；將於 v1.0.0 移除 |
| `redis_client` | [[RedisClient]] `\| None` | `None` | Redis 客戶端 |
| `notification_dispatcher` | `NotificationDispatcher \| None` | `None` | 通知分發器 |
| `statistics_config` | `StatisticsConfig \| None` | `None` | 統計管理器配置 |
| `device_registry` | `DeviceRegistry \| None` | `None` | 設備註冊中心（用於 Integration 層） |

> [!warning] mongo_uploader Deprecated（v0.7.1）
> `mongo_uploader` 欄位已被 `batch_uploader` 取代。使用 `mongo_uploader` 時會觸發 `DeprecationWarning`，將於 v1.0.0 移除。
>
> 遷移方式：
> ```python
> # 舊寫法（觸發 DeprecationWarning）
> config = UnifiedConfig(mongo_uploader=uploader)
>
> # 新寫法
> config = UnifiedConfig(batch_uploader=uploader)
> ```

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `config` | `UnifiedConfig` | 統一管理器配置 |
| `leader_gate` | [[LeaderGate]] `\| None`（kw-only） | Leader 閘門（可選，見下方說明） |

### leader_gate 行為（v0.10.0）

| 情境 | 行為 |
|------|------|
| 未注入 | 視為永遠是 leader（等同 `AlwaysLeaderGate`） |
| 注入後非 leader | `_on_start` 跳過 `device_manager.start()`（不連線/不讀取） |
| 注入後非 leader + `WriteCommandManager` | `execute()` raise `NotLeaderError` |
| 注入後非 leader + `StateSyncManager` | 所有事件 handler 早退，不寫 Redis |

---

## API

### 建構（constructor）

```python
UnifiedDeviceManager(config: UnifiedConfig, *, leader_gate: LeaderGate | None = None)
```

### 註冊

| 方法 | 說明 |
|------|------|
| `register(device, collection_name=None, traits=None, metadata=None, *, outputs=None)` | 註冊獨立設備 + 自動訂閱所有子管理器 |
| `register_group(devices, interval=1.0, collection_name=None, traits=None, metadata=None, *, outputs=None)` | 註冊設備群組 + 自動訂閱 |

#### register 參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `device` | `DeviceProtocol` | 必填 | 任何實作 `DeviceProtocol` 的設備 |
| `collection_name` | `str \| None` | `None` | MongoDB collection 名稱（與 `outputs` 互斥） |
| `traits` | `Sequence[str] \| None` | `None` | 設備 trait 標籤列表（用於 DeviceRegistry） |
| `metadata` | `Mapping[str, Any] \| None` | `None` | 設備靜態資訊（用於 DeviceRegistry） |
| `outputs` | `Sequence[UploadTarget] \| None`（kw-only） | `None` | Fan-out 上傳目標（與 `collection_name` 互斥） |

#### register_group 參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `devices` | `Sequence[DeviceProtocol]` | 必填 | 設備列表（必須共用同一 Client） |
| `interval` | `float` | `1.0` | 完整讀取一輪的間隔時間（秒） |
| `collection_name` | `str \| None` | `None` | MongoDB collection 名稱（群組共用） |
| `traits` | `Sequence[str] \| None` | `None` | 設備 trait 標籤列表（套用到群組所有設備） |
| `metadata` | `Mapping[str, Any] \| None` | `None` | 設備靜態資訊（套用到群組所有設備） |
| `outputs` | `Sequence[UploadTarget] \| None`（kw-only） | `None` | Fan-out 上傳目標（群組共用） |

### 解除註冊（v0.10.0 新增）

| 方法 | 說明 |
|------|------|
| `await unregister(device_id)` | 解除單一獨立設備；級聯清除所有子 manager 訂閱與 registry；回傳 `True`（找到）或 `False`（未找到） |
| `await unregister_group(device_ids)` | 解除整個群組；需提供完整 device_ids 集合（順序無關）；回傳 `True`/`False` |

### 觀測（v0.10.0 新增）

| 方法 | 說明 |
|------|------|
| `describe()` | 回傳 `UnifiedManagerStatus` 快照（O(1)~O(n)，不 await、不做 I/O） |

### 唯讀屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `device_manager` | [[DeviceManager]] | 設備讀取管理器 |
| `alarm_manager` | [[AlarmPersistenceManager]] `\| None` | 告警持久化管理器 |
| `command_manager` | [[WriteCommandManager]] `\| None` | 寫入指令管理器 |
| `data_manager` | [[DataUploadManager]] `\| None` | 資料上傳管理器 |
| `state_manager` | [[StateSyncManager]] `\| None` | 狀態同步管理器 |
| `statistics_manager` | `StatisticsManager \| None` | 統計管理器 |
| `is_running` | `bool` | 管理器是否運行中 |

## Capability Refresh 自動化（v0.10.0）

當 `UnifiedConfig.device_registry` 已配置時，`register()` / `register_group()` 會：

1. 呼叫 `registry.refresh_capability_traits(device_id)` — 立即同步現有 capability 到 `cap:*` trait 索引
2. 訂閱 `EVENT_CAPABILITY_ADDED` / `EVENT_CAPABILITY_REMOVED` — capability 變動時自動再次 refresh

解除註冊（`unregister`）時自動清除 capability refresh 訂閱，避免 event leak。

---

## Quick Example

### 基本使用

```python
import asyncio
from csp_lib.manager import UnifiedDeviceManager, UnifiedConfig

config = UnifiedConfig(
    alarm_repository=mongo_alarm_repo,
    command_repository=mongo_cmd_repo,
    batch_uploader=uploader,
    redis_client=redis_client,
)

manager = UnifiedDeviceManager(config)

# 註冊時指定 collection_name
manager.register(meter_device, collection_name="meter")
manager.register(io_device, collection_name="io")

# 群組註冊（含 DeviceRegistry traits）
manager.register_group(
    [rtu1, rtu2],
    collection_name="rtu_data",
    traits=["inverter"],
    metadata={"site": "plant_001"},
)

async with manager:
    await asyncio.sleep(3600)
```

### Cluster / HA 部署（注入 leader_gate）

```python
from csp_lib.manager import UnifiedDeviceManager, AlwaysLeaderGate

# 單節點：明確傳 AlwaysLeaderGate
manager = UnifiedDeviceManager(config, leader_gate=AlwaysLeaderGate())

# Cluster 節點：注入 EtcdLeaderGate（自訂實作）
manager = UnifiedDeviceManager(config, leader_gate=cluster_gate)

async with manager:
    # follower：_on_start 跳過 device_manager.start()
    # leader：正常啟動
    await asyncio.sleep(3600)
```

### 查詢觀測狀態（describe）

```python
status = manager.describe()
print(f"設備數: {status.devices_count}, leader: {status.is_leader}")
print(f"活躍告警: {status.alarms_active_count}")
```

### 解除設備註冊

```python
# 解除單一設備（async）
removed = await manager.unregister("pcs_01")

# 解除群組（傳入完整 device_ids 集合）
removed = await manager.unregister_group(["rtu_01", "rtu_02"])
```

---

## 相關頁面

- [[DeviceManager]] — 設備讀取管理
- [[AlarmPersistenceManager]] — 告警持久化
- [[DataUploadManager]] — 資料上傳
- [[WriteCommandManager]] — 指令路由
- [[StateSyncManager]] — 狀態同步
- [[BatchUploader]] — 上傳器 Protocol
- [[LeaderGate]] — Leader 閘門 Protocol（v0.10.0）
- [[ManagerDescribable]] — `describe()` Protocol 與 `UnifiedManagerStatus`（v0.10.0）
