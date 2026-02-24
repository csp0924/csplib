---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/device/group.py
---

# DeviceGroup

設備群組（純順序讀取器），隸屬於 [[_MOC Manager|Manager 模組]]。

## 概述

`DeviceGroup` 是一個 dataclass，用於管理需要順序讀取的設備集合。依序呼叫每個設備的 `read_once()`，確保不會同時讀取造成衝突。

### 適用場景

- **RTU 通訊**：多設備共用 RS485 線路
- **Shared TCP**：多設備共用 TCP Client（如 Gateway）
- 任何需要順序讀取的場景

### 設計理念

- `DeviceGroup` 只負責「順序讀取」
- 連線/斷線/重連由各 Device 自己管理
- 不限制設備是否共用 Client

## 欄位

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `devices` | `list[AsyncModbusDevice]` | 必填 | 群組內設備列表 |
| `interval` | `float` | `1.0` | 完整讀取一輪的間隔時間（秒） |
| `step_interval` | `float` | `0.05` | 設備間的讀取間隔時間（秒） |

## API

| 方法 | 說明 |
|------|------|
| `start()` | 啟動順序讀取循環（建立背景任務） |
| `stop()` | 停止順序讀取循環（取消背景任務） |

### 屬性

| 屬性 | 說明 |
|------|------|
| `is_running` | 讀取循環是否運行中 |
| `device_ids` | 群組內所有設備的 ID |

## 讀取循環邏輯

1. 依序呼叫每個設備的 `read_once()`
2. 每台設備讀取後等待 `step_interval`
3. 一輪完成後計算剩餘等待時間，補齊至 `interval`
4. 單一設備的讀取錯誤不影響其他設備

## 相關頁面

- [[DeviceManager]] — 使用 DeviceGroup 管理群組設備
- [[UnifiedDeviceManager]] — 統一入口的群組註冊
