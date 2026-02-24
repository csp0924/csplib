---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/device/manager.py
---

# DeviceManager

設備讀取循環管理器，隸屬於 [[_MOC Manager|Manager 模組]]。

## 概述

`DeviceManager` 統一管理獨立設備與群組設備的生命週期，提供一致的 start/stop 介面。繼承 `AsyncLifecycleMixin`，支援 `async with` 使用。

### 支援模式

| 模式 | 方法 | 說明 | 適用場景 |
|------|------|------|---------|
| 獨立模式 | `register(device)` | 設備自己跑 `read_loop` | 獨立 TCP 連線 |
| 群組模式 | `register_group(devices, interval)` | Manager 順序呼叫 `read_once` | RTU / Shared TCP |

## API

### 註冊

| 方法 | 說明 |
|------|------|
| `register(device)` | 註冊獨立設備 |
| `register_group(devices, interval=1.0)` | 註冊設備群組（建立 [[DeviceGroup]]） |

### 屬性

| 屬性 | 說明 |
|------|------|
| `is_running` | 管理器是否運行中 |
| `standalone_count` | 獨立設備數量 |
| `group_count` | 設備群組數量 |
| `all_devices` | 所有設備的合併列表 |
| `groups` | 所有設備群組 |

## 生命週期

- **啟動**：獨立設備各自啟動 `read_loop`；群組設備先連線再啟動順序讀取。連線失敗不阻止啟動，會在背景自動重試。
- **停止**：停止所有讀取循環並斷開連線。

## 使用範例

```python
from csp_lib.manager import DeviceManager, DeviceGroup

# Standalone
manager = DeviceManager(device)

# Group mode
group = DeviceGroup(devices=[device1, device2, device3])
manager = DeviceManager(group)

async with manager:
    ...  # Auto manages device lifecycle
```

## 相關頁面

- [[DeviceGroup]] — 群組設備順序讀取
- [[UnifiedDeviceManager]] — 整合所有 Manager 的統一入口
