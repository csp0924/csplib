---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/unified.py
updated: 2026-04-04
---

# UnifiedDeviceManager

統一設備管理器，隸屬於 [[_MOC Manager|Manager 模組]]。

## 概述

`UnifiedDeviceManager` 整合 [[DeviceManager]]、[[AlarmPersistenceManager]]、[[WriteCommandManager]]、[[DataUploadManager]]、[[StateSyncManager]]、`StatisticsManager`，提供單一入口點。繼承 `AsyncLifecycleMixin`，支援 `async with` 使用。

註冊設備後自動串接所有已啟用的功能，使用者無需手動 subscribe 各子管理器。

## UnifiedConfig

所有子管理器皆為可選，未配置的功能將自動跳過。

> [!warning] v0.6.0 Changed
> `mongo_uploader` 欄位型別從 `MongoBatchUploader` 放寬為 [[BatchUploader]] Protocol。既有程式碼傳入 `MongoBatchUploader` 仍然相容。

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `alarm_repository` | `AlarmRepository \| None` | `None` | 告警持久化 Repository |
| `command_repository` | `CommandRepository \| None` | `None` | 寫入指令 Repository |
| `mongo_uploader` | [[BatchUploader]] `\| None` | `None` | 批次上傳器（命名保留 `mongo_uploader` 以維持向後相容） |
| `redis_client` | [[RedisClient]] `\| None` | `None` | Redis 客戶端 |
| `notification_dispatcher` | `NotificationDispatcher \| None` | `None` | 通知分發器 |
| `statistics_config` | `StatisticsConfig \| None` | `None` | 統計管理器配置 |
| `device_registry` | `DeviceRegistry \| None` | `None` | 設備註冊中心（用於 Integration 層） |

> [!note] `mongo_uploader` 命名
> 此欄位名稱保留 `mongo_uploader` 以維持向後相容，但實際型別已放寬為 `BatchUploader` Protocol，可注入任何符合介面的實作。

## API

### 註冊

| 方法 | 說明 |
|------|------|
| `register(device, collection_name=None, traits=None, metadata=None)` | 註冊獨立設備 + 自動訂閱所有子管理器 |
| `register_group(devices, interval=1.0, collection_name=None, traits=None, metadata=None)` | 註冊設備群組 + 自動訂閱 |

#### register 參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `device` | `AsyncModbusDevice` | 必填 | Modbus 設備 |
| `collection_name` | `str \| None` | `None` | MongoDB collection 名稱（Data Upload 用） |
| `traits` | `Sequence[str] \| None` | `None` | 設備 trait 標籤列表（用於 DeviceRegistry） |
| `metadata` | `dict[str, Any] \| None` | `None` | 設備靜態資訊（用於 DeviceRegistry） |

#### register_group 參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `devices` | `Sequence[AsyncModbusDevice]` | 必填 | 設備列表（必須共用同一 Client） |
| `interval` | `float` | `1.0` | 完整讀取一輪的間隔時間（秒） |
| `collection_name` | `str \| None` | `None` | MongoDB collection 名稱（群組共用） |
| `traits` | `Sequence[str] \| None` | `None` | 設備 trait 標籤列表（套用到群組所有設備） |
| `metadata` | `dict[str, Any] \| None` | `None` | 設備靜態資訊（套用到群組所有設備） |

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

## Quick Example

```python
from csp_lib.manager import UnifiedDeviceManager, UnifiedConfig
from csp_lib.mongo import MongoBatchUploader

config = UnifiedConfig(
    alarm_repository=mongo_alarm_repo,
    command_repository=mongo_cmd_repo,
    mongo_uploader=uploader,        # BatchUploader Protocol
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

## 相關頁面

- [[DeviceManager]] — 設備讀取管理
- [[AlarmPersistenceManager]] — 告警持久化
- [[DataUploadManager]] — 資料上傳
- [[WriteCommandManager]] — 指令路由
- [[StateSyncManager]] — 狀態同步
- [[BatchUploader]] — 上傳器 Protocol
