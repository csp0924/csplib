---
tags:
  - type/guide
  - layer/integration
  - status/complete
created: 2026-04-06
updated: 2026-04-06
version: ">=0.7.1"
---

# Capability-driven 部署驗證

本指南說明如何透過 `Capability` 系統宣告設備能力、定義系統需求，以及在啟動前執行 `preflight_check` 確認部署是否符合最低設備要求。

---

## 概觀

Capability 系統解決了一個常見的痛點：不同廠牌的設備雖然功能相同（例如「可以控制有功功率」），但點位名稱各不相同（一台叫 `set_p`，另一台叫 `p_setpoint`）。

Capability 系統的核心概念：

| 概念 | 作用 |
|------|------|
| `Capability` | 定義語意「能做什麼」（例：`ACTIVE_POWER_CONTROL`），包含 read/write slots |
| `CapabilityBinding` | 設備宣告「怎麼做」，將 slot 映射到實際點位名稱 |
| `CapabilityRequirement` | 系統宣告「需要哪些設備能力」，供 preflight 驗證 |
| `preflight_check` | 啟動前驗證所有能力需求是否已滿足 |

---

## Quick Example

```python
import asyncio
from csp_lib.equipment.device.capability import (
    ACTIVE_POWER_CONTROL,
    HEARTBEAT,
    SOC_READABLE,
    CapabilityBinding,
)
from csp_lib.integration.schema import CapabilityRequirement
from csp_lib.integration import SystemController, SystemControllerConfig

async def main() -> None:
    # 1. 設備宣告自身能力（在建立設備時設定）
    pcs = build_pcs_device()
    pcs.add_capability(CapabilityBinding(
        ACTIVE_POWER_CONTROL,
        {"p_setpoint": "set_active_power", "p_measurement": "active_power_meas"},
    ))

    bms = build_bms_device()
    bms.add_capability(CapabilityBinding(
        SOC_READABLE,
        {"soc": "battery_soc"},
    ))

    # 2. 在 SystemControllerConfig 宣告系統需求
    config = SystemControllerConfig(
        capability_requirements=[
            CapabilityRequirement(ACTIVE_POWER_CONTROL, min_count=1),
            CapabilityRequirement(SOC_READABLE, min_count=1),
        ],
        strict_capability_check=True,   # 不滿足時 raise ConfigurationError
    )

    # 3. 啟動時自動執行 preflight_check
    controller = SystemController(registry, config)
    async with controller:
        # 若能力需求不滿足，_on_start 已拋出 ConfigurationError
        await controller.run()
```

---

## 標準能力定義

csp_lib 預定義了常用的標準能力，可直接匯入使用：

```python
from csp_lib.equipment.device.capability import (
    HEARTBEAT,              # 控制器 watchdog 心跳寫入
    ACTIVE_POWER_CONTROL,   # 有功功率設定點控制（P）
    REACTIVE_POWER_CONTROL, # 無功功率設定點控制（Q）
    SWITCHABLE,             # 開關控制（斷路器、接觸器）
    LOAD_SHEDDABLE,         # 負載卸載（Switchable + 功率量測）
    MEASURABLE,             # 有功功率量測
    FREQUENCY_MEASURABLE,   # 頻率量測
    VOLTAGE_MEASURABLE,     # 電壓量測
    SOC_READABLE,           # 電池 SOC 讀取
)
```

每個標準能力定義了必要的 slots：

| 能力 | write_slots | read_slots | 說明 |
|------|------------|-----------|------|
| `HEARTBEAT` | `heartbeat` | — | 看門狗心跳寫入 |
| `ACTIVE_POWER_CONTROL` | `p_setpoint` | `p_measurement` | 有功功率控制 |
| `REACTIVE_POWER_CONTROL` | `q_setpoint` | — | 無功功率控制 |
| `SWITCHABLE` | `switch_cmd` | `switch_status` | 開關控制 |
| `LOAD_SHEDDABLE` | `switch_cmd` | `active_power`, `switch_status` | 負載卸載 |
| `MEASURABLE` | — | `active_power` | 功率量測 |
| `FREQUENCY_MEASURABLE` | — | `frequency` | 頻率量測 |
| `VOLTAGE_MEASURABLE` | — | `voltage` | 電壓量測 |
| `SOC_READABLE` | — | `soc` | SOC 讀取 |

---

## CapabilityBinding：設備宣告能力

`CapabilityBinding` 將 Capability 的語意 slots 映射到設備的實際點位名稱。

```python
from csp_lib.equipment.device.capability import ACTIVE_POWER_CONTROL, CapabilityBinding

# 不同廠牌 PCS 的點位名稱不同，但都透過同一個 Capability 抽象化
sungrow_pcs_binding = CapabilityBinding(
    capability=ACTIVE_POWER_CONTROL,
    point_map={
        "p_setpoint":    "active_power_setpoint",  # Sungrow 的點位名
        "p_measurement": "active_power_fb",
    },
)

huawei_pcs_binding = CapabilityBinding(
    capability=ACTIVE_POWER_CONTROL,
    point_map={
        "p_setpoint":    "p_cmd",                  # Huawei 的點位名
        "p_measurement": "p_measured",
    },
)

# 在設備上宣告
sungrow_device.add_capability(sungrow_pcs_binding)
huawei_device.add_capability(huawei_pcs_binding)
```

> [!warning] slot 必須完整
> `CapabilityBinding` 會驗證所有 `all_slots`（read_slots ∪ write_slots）都已在 `point_map` 中提供。
> 若有缺漏，初始化時會拋出 `ConfigurationError`。

### 自訂能力

可建立專案專屬的自訂 Capability：

```python
from csp_lib.equipment.device.capability import Capability, CapabilityBinding

# 自訂：BESS 設備的充放電切換能力
CHARGE_DISCHARGE_CONTROL = Capability(
    name="charge_discharge_control",
    write_slots=("charge_cmd", "discharge_cmd"),
    read_slots=("charge_status",),
    description="Charge/discharge mode control",
)

binding = CapabilityBinding(
    CHARGE_DISCHARGE_CONTROL,
    {
        "charge_cmd":    "cmd_charge",
        "discharge_cmd": "cmd_discharge",
        "charge_status": "status_charge",
    },
)
```

---

## CapabilityRequirement：定義系統需求

`CapabilityRequirement` 用於告訴 `preflight_check` 系統需要哪些能力、最少幾台設備。

```python
from csp_lib.integration.schema import CapabilityRequirement
from csp_lib.equipment.device.capability import ACTIVE_POWER_CONTROL, SOC_READABLE

requirements = [
    # 必須有至少 1 台可控有功功率的設備（任意 trait）
    CapabilityRequirement(
        capability=ACTIVE_POWER_CONTROL,
        min_count=1,
    ),
    # 必須有至少 2 台可讀 SOC 的 BMS（限定 trait="bms"）
    CapabilityRequirement(
        capability=SOC_READABLE,
        min_count=2,
        trait_filter="bms",
    ),
]
```

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `capability` | `Capability` | 必填 | 要求的能力 |
| `min_count` | `int` | `1` | 最少需要幾台設備具備此能力 |
| `trait_filter` | `str \| None` | `None` | 限定特定 trait（None = 搜尋所有設備） |

---

## preflight_check：啟動前驗證

### 手動呼叫

可以在啟動 `SystemController` 前手動呼叫 `preflight_check`，提前得知缺少哪些能力：

```python
controller = SystemController(registry, config)

# 手動執行（不會 raise，回傳失敗描述列表）
failures = controller.preflight_check()
if failures:
    print("能力不足：")
    for f in failures:
        print(f"  - {f}")
    # 可選擇降級或等待設備就緒
```

### 自動執行（async with 啟動時）

`SystemController` 的 `_on_start()` 會自動呼叫 `preflight_check()`：

```python
config = SystemControllerConfig(
    capability_requirements=[...],
    strict_capability_check=True,   # 失敗時 raise ConfigurationError
)

try:
    async with SystemController(registry, config) as ctrl:
        await ctrl.run()
except ConfigurationError as e:
    print(f"部署驗證失敗：{e}")
    # 系統不啟動
```

### strict 模式 vs. 寬鬆模式

| `strict_capability_check` | 行為 |
|---------------------------|------|
| `False`（預設） | 不滿足需求時僅記錄 WARNING，系統繼續啟動 |
| `True` | 不滿足需求時拋出 `ConfigurationError`，系統不啟動 |

> [!tip] 建議做法
> - 開發 / 測試環境：`strict_capability_check=False`，方便用 mock 設備除錯
> - 正式部署：`strict_capability_check=True`，防止設備接線錯誤導致控制指令送達錯誤點位

---

## 常見部署模式

### PCS 部署

```python
from csp_lib.equipment.device.capability import (
    ACTIVE_POWER_CONTROL,
    REACTIVE_POWER_CONTROL,
    HEARTBEAT,
    CapabilityBinding,
)

# PCS 設備宣告能力
pcs.add_capability(CapabilityBinding(
    ACTIVE_POWER_CONTROL,
    {"p_setpoint": "p_cmd", "p_measurement": "p_feedback"},
))
pcs.add_capability(CapabilityBinding(
    REACTIVE_POWER_CONTROL,
    {"q_setpoint": "q_cmd"},
))
pcs.add_capability(CapabilityBinding(
    HEARTBEAT,
    {"heartbeat": "watchdog_reg"},
))

# 系統需求
requirements = [
    CapabilityRequirement(ACTIVE_POWER_CONTROL, min_count=1),
    CapabilityRequirement(REACTIVE_POWER_CONTROL, min_count=1),
    CapabilityRequirement(HEARTBEAT, min_count=1),
]
```

### BMS 部署

```python
from csp_lib.equipment.device.capability import SOC_READABLE, CapabilityBinding

bms.add_capability(CapabilityBinding(
    SOC_READABLE,
    {"soc": "soc_value"},
))

requirements = [
    CapabilityRequirement(SOC_READABLE, min_count=1, trait_filter="bms"),
]
```

### 智慧電表部署（頻率 + 電壓量測）

```python
from csp_lib.equipment.device.capability import (
    FREQUENCY_MEASURABLE,
    VOLTAGE_MEASURABLE,
    MEASURABLE,
    CapabilityBinding,
)

meter.add_capability(CapabilityBinding(FREQUENCY_MEASURABLE, {"frequency": "freq_hz"}))
meter.add_capability(CapabilityBinding(VOLTAGE_MEASURABLE, {"voltage": "volt_v"}))
meter.add_capability(CapabilityBinding(MEASURABLE, {"active_power": "p_kw"}))

requirements = [
    CapabilityRequirement(FREQUENCY_MEASURABLE, min_count=1, trait_filter="meter"),
    CapabilityRequirement(MEASURABLE, min_count=1),
]
```

---

## 與 CapabilityCommandMapping 搭配使用

一旦設備宣告了能力，可以在 `SystemControllerConfig` 中使用 `CapabilityCommandMapping` 進行 capability-driven 路由，讓控制器自動發現並路由到具備該能力的設備：

```python
from csp_lib.integration.schema import CapabilityCommandMapping, CapabilityContextMapping

config = SystemControllerConfig(
    capability_context_mappings=[
        CapabilityContextMapping(
            capability=SOC_READABLE,
            slot="soc",
            context_field="soc",
            trait="bms",
            aggregate=AggregateFunc.AVERAGE,
        ),
    ],
    capability_command_mappings=[
        CapabilityCommandMapping(
            command_field="p_target",
            capability=ACTIVE_POWER_CONTROL,
            slot="p_setpoint",
            trait="pcs",
        ),
    ],
    capability_requirements=[
        CapabilityRequirement(ACTIVE_POWER_CONTROL, min_count=1),
        CapabilityRequirement(SOC_READABLE, min_count=1),
    ],
    strict_capability_check=True,
)
```

---

## 相關頁面

- [[SystemController]] — preflight_check 完整 API
- [[DeviceRegistry]] — 設備 trait 系統
- [[CapabilityBinding Integration]] — 架構說明
- [[Full System Integration]] — 完整系統整合指南
- [[_MOC Integration]] — Integration 層索引
