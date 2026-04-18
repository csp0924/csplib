---
tags:
  - type/class
  - layer/manager
  - status/stale
source: csp_lib/manager/device/manager.py
updated: 2026-04-04
version: ">=0.5.0"
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

## 建構參數

無參數。`DeviceManager()` 即可建立。

## API

### 註冊

| 方法 | 說明 |
|------|------|
| `register(device)` | 註冊獨立設備（device_id 重複時拋出 `ValueError`） |
| `register_group(devices, interval=1.0)` | 註冊設備群組（建立 [[DeviceGroup]]，device_id 重複時拋出 `ValueError`） |

### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `is_running` | `bool` | 管理器是否運行中 |
| `standalone_count` | `int` | 獨立設備數量 |
| `group_count` | `int` | 設備群組數量 |
| `all_devices` | `list[AsyncModbusDevice]` | 所有設備的合併列表（獨立 + 群組） |
| `groups` | `list[DeviceGroup]` | 所有設備群組 |

## 生命週期

- **啟動**：獨立設備各自 `connect()` + `start()`；群組設備先 `connect()` 再 `group.start()`。連線失敗不阻止啟動（`DeviceConnectionError` 被捕獲），會在背景自動重試。
- **停止**：獨立設備 `stop()` + `disconnect()`；群組設備 `group.stop()` + 各設備 `disconnect()`。

## Quick Example

```python
from csp_lib.manager.device import DeviceManager

manager = DeviceManager()

# 獨立 TCP 設備
manager.register(tcp_device_1)
manager.register(tcp_device_2)

# RTU 群組（共用 Client）
manager.register_group([rtu_1, rtu_2], interval=1.0)

async with manager:
    await asyncio.sleep(60)  # 運行 60 秒
```

## 相關頁面

- [[DeviceGroup]] — 群組設備順序讀取
- [[UnifiedDeviceManager]] — 整合所有 Manager 的統一入口
