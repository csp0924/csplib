---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/registry.py
updated: 2026-04-04
version: ">=0.4.2"
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
| `register(device, traits=None, metadata=None)` | 註冊設備與可選的 traits 及靜態 metadata；`device_id` 已存在時拋出 `ValueError` |
| `register_with_capabilities(device, extra_traits=None, metadata=None)` | 自動從設備 capabilities 產生 `cap:xxx` traits 後註冊（見下方說明） |
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
| `get_metadata(device_id)` | 取得設備的靜態 metadata dict，不存在回傳 `{}` |

### Metadata 支援

`register()` 的 `metadata` 參數接受任意 `dict[str, Any]`，用於儲存設備的靜態屬性（如額定功率、序號等）。此資訊會在建構 `DeviceSnapshot` 時被 [[PowerDistributor]] 使用，以進行比例或 SOC 平衡分配。

```python
registry.register(
    bess_device,
    traits=["bess"],
    metadata={"rated_p": 500.0, "rated_s": 600.0, "serial": "BESS-A01"},
)

# 查詢 metadata
meta = registry.get_metadata("bess_a")  # {"rated_p": 500.0, ...}
```

### Capability 查詢

> [!info] v0.6.0 新增

| 方法 | 說明 |
|------|------|
| `get_devices_with_capability(capability)` | 取得具備指定能力的所有設備（按 `device_id` 排序） |
| `get_responsive_devices_with_capability(capability)` | 取得具備指定能力且 responsive 的設備 |
| `validate_capabilities(requirements)` | 驗證能力需求列表，回傳不滿足的描述列表（空 = 全部通過） |

`validate_capabilities()` 搭配 [[CapabilityRequirement]] 使用，為 [[SystemController]] 的 `preflight_check()` 提供底層驗證邏輯。

```python
from csp_lib.integration.schema import CapabilityRequirement
from csp_lib.equipment.device.capability import ACTIVE_POWER_CONTROL

failures = registry.validate_capabilities([
    CapabilityRequirement(capability=ACTIVE_POWER_CONTROL, min_count=2),
])
# failures: ["Capability 'active_power_control' requires 2 device(s), found 1"]
```

### register_with_capabilities()

> [!info] v0.6.0 新增

自動從設備的 `capabilities` 屬性產生 `cap:xxx` 格式的 traits，再合併 `extra_traits`。

```python
# 自動發現：設備具備 active_power_control 和 soc_readable
# → traits: ["bess", "cap:active_power_control", "cap:soc_readable"]
registry.register_with_capabilities(
    bess_device, extra_traits=["bess"], metadata={"rated_p": 500.0},
)
```

### 屬性

| 屬性 | 說明 |
|------|------|
| `all_devices` | 所有已註冊設備（按 `device_id` 排序） |
| `all_traits` | 所有已知的 trait 標籤（排序） |

## 使用範例

```python
from csp_lib.integration import DeviceRegistry

registry = DeviceRegistry()

# 基本註冊（含 traits）
registry.register(device, traits=["pcs", "battery"])
registry.add_trait("inverter_001", "grid_forming")

# 含 metadata 的註冊（供 PowerDistributor 使用）
registry.register(bess_a, traits=["bess"], metadata={"rated_p": 500.0})
registry.register(bess_b, traits=["bess"], metadata={"rated_p": 1000.0})

# 查詢
device = registry.get_device("inverter_001")
pcs_devices = registry.get_devices_by_trait("pcs")              # All PCS devices
responsive = registry.get_responsive_devices_by_trait("pcs")    # Only responsive

# 查詢 metadata
meta = registry.get_metadata("bess_a")  # {"rated_p": 500.0}
```

## 相關頁面

- [[ContextBuilder]] — 使用 registry 查詢設備並讀取值
- [[CommandRouter]] — 使用 registry 查詢設備並執行寫入
- [[DeviceDataFeed]] — 使用 registry 解析 PV 資料來源設備
- [[PowerDistributor]] — 使用 metadata 進行比例或 SOC 平衡分配
- [[GroupControllerManager]] — 從 master registry 建立子 registry 進行多群組控制
- [[CapabilityRequirement]] — 能力需求定義，搭配 `validate_capabilities()` 使用
