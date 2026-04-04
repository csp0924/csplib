---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/schema.py
---

# CapabilityRequirement

能力需求定義，隸屬於 [[_MOC Integration|Integration 模組]]。

> [!info] v0.6.0 新增

## 概述

`CapabilityRequirement` 是一個 frozen dataclass（`@dataclass(frozen=True, slots=True)`），用於宣告系統啟動前（preflight）所需的設備能力需求。搭配 [[DeviceRegistry]] 的 `validate_capabilities()` 方法，可在控制迴圈啟動前驗證已註冊設備是否滿足最低需求。

### 使用場景

- 確保系統中至少有 N 台具備特定能力的設備（例如至少 2 台 PCS 具備 `ACTIVE_POWER_CONTROL`）
- 可限定特定 trait 範圍內的設備（例如 `trait_filter="bess"` 只檢查 BESS 設備）
- 搭配 [[SystemController]] 的 `strict_capability_check` 可在啟動時 raise `ConfigurationError`

## 欄位

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `capability` | `Capability` | 必填 | 必要的設備能力 |
| `min_count` | `int` | `1` | 最少設備數量 |
| `trait_filter` | `str \| None` | `None` | 限定特定 trait 的設備（`None` = 搜尋所有設備） |

## 驗證流程

`DeviceRegistry.validate_capabilities(requirements)` 的檢查邏輯：

1. 若設定 `trait_filter`：取得該 trait 的設備，再過濾具備 capability 的
2. 若未設定 `trait_filter`：直接取得所有具備 capability 的設備
3. 比對設備數量與 `min_count`，不足時加入失敗清單

## Quick Example

```python
from csp_lib.equipment.device.capability import ACTIVE_POWER_CONTROL, SOC_READABLE
from csp_lib.integration import DeviceRegistry
from csp_lib.integration.schema import CapabilityRequirement

# 定義需求
requirements = [
    CapabilityRequirement(capability=ACTIVE_POWER_CONTROL, min_count=2),
    CapabilityRequirement(
        capability=SOC_READABLE, min_count=1, trait_filter="bess",
    ),
]

# 驗證
failures = registry.validate_capabilities(requirements)
if failures:
    for msg in failures:
        print(f"FAIL: {msg}")
# FAIL: Capability 'active_power_control' requires 2 device(s), found 1
```

### 搭配 SystemControllerConfigBuilder

```python
from csp_lib.integration import SystemControllerConfig
from csp_lib.integration.schema import CapabilityRequirement

config = (
    SystemControllerConfig.builder()
    .require_capability(CapabilityRequirement(
        capability=ACTIVE_POWER_CONTROL, min_count=2,
    ))
    .strict_capability(True)  # 啟動時 raise ConfigurationError
    .build()
)
```

## AggregationResult

> [!info] v0.6.0 新增

`AggregationResult` 是一個 frozen dataclass（`@dataclass(frozen=True, slots=True)`），用於封裝聚合運算的結果與品質資訊。由 [[ContextBuilder]] 在 capability 聚合路徑中內部使用。

### 欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `value` | `Any` | 聚合計算結果 |
| `device_count` | `int` | 實際參與聚合的設備數 |
| `expected_count` | `int` | 預期設備數（Registry 中該 capability 的總設備數） |

### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `quality_ratio` | `float` | `device_count / expected_count`，`expected_count <= 0` 時回傳 `1.0` |

### 與 min_device_ratio 的關係

[[CapabilityContextMapping]] 的 `min_device_ratio` 欄位用於設定品質門檻。當 `quality_ratio` 低於此值時，聚合結果被丟棄並回傳 `default`，同時發出警告日誌。

## 相關頁面

- [[DeviceRegistry]] — `validate_capabilities()` 方法執行驗證
- [[SystemController]] — `preflight_check()` 方法在啟動時自動驗證
- [[CapabilityContextMapping]] — `min_device_ratio` 品質門檻
- [[CapabilityBinding Integration]] — 完整架構與流程圖
