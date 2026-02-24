---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/unified.py
---

# UnifiedDeviceManager

統一設備管理器，隸屬於 [[_MOC Manager|Manager 模組]]。

## 概述

`UnifiedDeviceManager` 整合 [[DeviceManager]]、[[AlarmPersistenceManager]]、[[WriteCommandManager]]、[[DataUploadManager]]、[[StateSyncManager]]，提供單一入口點。繼承 `AsyncLifecycleMixin`，支援 `async with` 使用。

註冊設備後自動串接所有已啟用的功能，使用者無需手動 subscribe 各子管理器。

## UnifiedConfig

所有子管理器皆為可選，未配置的功能將自動跳過。

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `alarm_repository` | `AlarmRepository \| None` | `None` | 告警持久化 Repository |
| `command_repository` | `CommandRepository \| None` | `None` | 寫入指令 Repository |
| `mongo_uploader` | [[MongoBatchUploader]] `\| None` | `None` | MongoDB 批次上傳器 |
| `redis_client` | [[RedisClient]] `\| None` | `None` | Redis 客戶端 |
| `notification_dispatcher` | `NotificationDispatcher \| None` | `None` | 通知分發器 |

## API

### 註冊

| 方法 | 說明 |
|------|------|
| `register(device, collection_name=None)` | 註冊獨立設備 + 自動訂閱所有子管理器 |
| `register_group(devices, interval=1.0, collection_name=None)` | 註冊設備群組 + 自動訂閱 |

### 唯讀屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `device_manager` | [[DeviceManager]] | 設備讀取管理器 |
| `alarm_manager` | [[AlarmPersistenceManager]] `\| None` | 告警持久化管理器 |
| `command_manager` | [[WriteCommandManager]] `\| None` | 寫入指令管理器 |
| `data_manager` | [[DataUploadManager]] `\| None` | 資料上傳管理器 |
| `state_manager` | [[StateSyncManager]] `\| None` | 狀態同步管理器 |
| `is_running` | `bool` | 管理器是否運行中 |

## 使用範例

```python
from csp_lib.manager import UnifiedDeviceManager, UnifiedConfig

config = UnifiedConfig(
    enable_alarm=True,
    enable_command=True,
    enable_data_upload=True,
    enable_state_sync=True,
)
unified = UnifiedDeviceManager(device=device, config=config, ...)
async with unified:
    ...
```

## 相關頁面

- [[DeviceManager]] — 設備讀取管理
- [[AlarmPersistenceManager]] — 告警持久化
- [[DataUploadManager]] — 資料上傳
- [[WriteCommandManager]] — 指令路由
- [[StateSyncManager]] — 狀態同步
