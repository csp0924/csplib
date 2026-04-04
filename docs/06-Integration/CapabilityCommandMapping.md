---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/schema.py
created: 2026-03-06
updated: 2026-04-04
version: ">=0.4.2"
---

# CapabilityCommandMapping

Capability-driven Command → 設備寫入映射定義，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`CapabilityCommandMapping` 是一個 frozen dataclass，用於以 **capability + slot** 取代明確的 `point_name`，讓不同設備自動透過 `CapabilityBinding` 解析各自的實際寫入點位名稱。

與 [[CommandMapping]] 的核心差異：
- 使用 `capability` + `slot` 取代 `point_name`
- 支援 **auto 模式**（`device_id` 和 `trait` 皆為 `None`），自動發現所有具備該能力的設備

### 三種 Scoping 模式

| 模式 | device_id | trait | 行為 |
|------|-----------|-------|------|
| **device_id** | 設定 | `None` | 寫入單一指定設備 |
| **trait** | `None` | 設定 | 廣播寫入同 trait 且具備該 capability 的所有設備 |
| **auto** | `None` | `None` | 自動發現所有具備該 capability 的 responsive 設備並寫入 |

## 欄位

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `command_field` | `str` | 必填 | Command 屬性名稱（`"p_target"` / `"q_target"`） |
| `capability` | `Capability` | 必填 | 目標能力定義 |
| `slot` | `str` | 必填 | capability 的 write slot 名稱（必須存在於 `capability.write_slots`） |
| `device_id` | `str \| None` | `None` | 指定單一設備 ID（與 `trait` 擇一，或皆不設） |
| `trait` | `str \| None` | `None` | 指定 trait 標籤（與 `device_id` 擇一，或皆不設） |
| `transform` | `Callable[[float], Any] \| None` | `None` | 值轉換函式，寫入前套用 |

## 驗證規則

- `device_id` 與 `trait` 不可同時設定（`ValueError`）
- `slot` 必須存在於 `capability.write_slots`（`ValueError`）

## 使用範例

```python
from csp_lib.equipment.device.capability import ACTIVE_POWER_CONTROL, REACTIVE_POWER_CONTROL
from csp_lib.integration import CapabilityCommandMapping

# Auto 模式：自動寫入所有具備 P 控制能力的設備
CapabilityCommandMapping(
    command_field="p_target",
    capability=ACTIVE_POWER_CONTROL,
    slot="p_setpoint",
)

# Trait 模式：廣播寫入 "pcs" trait 中具備 Q 控制的設備
CapabilityCommandMapping(
    command_field="q_target",
    capability=REACTIVE_POWER_CONTROL,
    slot="q_setpoint",
    trait="pcs",
    transform=lambda q: q / 3,  # 均分到 3 台
)

# Device_id 模式：寫入指定設備
CapabilityCommandMapping(
    command_field="p_target",
    capability=ACTIVE_POWER_CONTROL,
    slot="p_setpoint",
    device_id="pcs_01",
)
```

## 寫入安全檢查

[[CommandRouter]] 在寫入前對每台設備執行以下檢查：

1. 設備存在於 [[DeviceRegistry]]
2. `device.is_protected == False`（非告警狀態）
3. `device.is_responsive == True`（通訊正常）
4. `device.has_capability(capability) == True`

任一檢查不通過則跳過該設備（log warning），不影響其他設備。

## 相關頁面

- [[CommandMapping]] -- 明確 point_name 版本的 command 映射
- [[CapabilityContextMapping]] -- Capability-driven context 映射
- [[CommandRouter]] -- 使用 CapabilityCommandMapping 路由寫入
- [[SystemController]] -- 透過 `capability_command_mappings` 配置
- [[CapabilityBinding Integration]] -- 完整架構與流程圖
