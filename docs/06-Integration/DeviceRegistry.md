---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/registry.py
---

# DeviceRegistry

Trait-based 設備查詢索引，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`DeviceRegistry` 維護 `device_id` 與 `trait` 之間的雙向索引，提供高效的設備查詢能力。它不管理設備生命週期，僅負責索引與查詢。所有依 trait 查詢的結果皆按 `device_id` 排序，確保確定性。

### 內部索引結構

- `device_id` → `AsyncModbusDevice`（設備實例）
- `device_id` → `set[trait]`（該設備的所有 trait）
- `trait` → `set[device_id]`（擁有該 trait 的所有設備）

## API

### 註冊與移除

| 方法 | 說明 |
|------|------|
| `register(device, traits=None)` | 註冊設備與可選的 traits；`device_id` 已存在時拋出 `ValueError` |
| `unregister(device_id)` | 移除設備及其所有 trait 關聯；不存在時靜默忽略 |

### Trait 管理

| 方法 | 說明 |
|------|------|
| `add_trait(device_id, trait)` | 為已註冊設備新增 trait；未註冊時拋出 `KeyError` |
| `remove_trait(device_id, trait)` | 移除設備的 trait；未註冊時拋出 `KeyError` |

### 查詢

| 方法 | 說明 |
|------|------|
| `get_device(device_id)` | 依 ID 查詢設備，不存在回傳 `None` |
| `get_devices_by_trait(trait)` | 依 trait 查詢所有設備（按 `device_id` 排序） |
| `get_responsive_devices_by_trait(trait)` | 依 trait 查詢所有 `is_responsive=True` 的設備 |
| `get_first_responsive_device_by_trait(trait)` | 依 trait 取得第一台 responsive 設備 |
| `get_traits(device_id)` | 取得設備的所有 traits |

### 屬性

| 屬性 | 說明 |
|------|------|
| `all_devices` | 所有已註冊設備（按 `device_id` 排序） |
| `all_traits` | 所有已知的 trait 標籤（排序） |

## 使用範例

```python
from csp_lib.integration import DeviceRegistry

registry = DeviceRegistry()
registry.register(device, traits=["pcs", "battery"])
registry.add_trait("inverter_001", "grid_forming")

# Query
device = registry.get("inverter_001")
pcs_devices = registry.get_by_trait("pcs")                    # All PCS devices
responsive = registry.get_by_trait("pcs", responsive_only=True) # Only responsive
```

## 相關頁面

- [[ContextBuilder]] — 使用 registry 查詢設備並讀取值
- [[CommandRouter]] — 使用 registry 查詢設備並執行寫入
- [[DeviceDataFeed]] — 使用 registry 解析 PV 資料來源設備
- [[GroupControllerManager]] — 從 master registry 建立子 registry 進行多群組控制
