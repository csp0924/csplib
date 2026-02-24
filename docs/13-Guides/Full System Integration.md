---
tags:
  - type/guide
  - layer/integration
  - status/complete
created: 2026-02-17
---

# 完整系統整合指南

本指南說明如何使用 Integration 模組將設備層 (Equipment) 與控制器層 (Controller) 整合為完整的控制系統。

## 架構概覽

```
設備 (AsyncModbusDevice)
    |
    v
DeviceRegistry (trait-based 查詢索引)
    |
    v
ContextBuilder ---> StrategyContext
    |                    |
    |                    v
    |              StrategyExecutor
    |                    |
    |                    v
    |                 Command
    |                    |
    v                    v
DeviceDataFeed     CommandRouter ---> 設備寫入
```

---

## 步驟總覽

1. 註冊設備到 [[DeviceRegistry]]
2. 定義映射 Schema
3. 選擇 [[GridControlLoop]] 或 [[SystemController]]
4. 執行控制迴圈

---

## 1. 註冊設備

使用 [[DeviceRegistry]] 管理設備，並透過 trait 進行分類查詢。

```python
from csp_lib.integration import DeviceRegistry

registry = DeviceRegistry()

# 註冊設備並指定 trait
registry.register(meter_device, traits=["meter"])
registry.register(pcs_device, traits=["pcs", "battery"])
registry.register(bms_device, traits=["bms"])

# 新增 trait
registry.add_trait("inverter_001", "grid_forming")

# 查詢
device = registry.get("inverter_001")
pcs_devices = registry.get_by_trait("pcs")
responsive = registry.get_by_trait("pcs", responsive_only=True)
```

---

## 2. 定義映射 Schema

### ContextMapping

使用 [[ContextMapping]] 將設備值映射到 [[StrategyContext]]：

```python
from csp_lib.integration import ContextMapping, AggregateFunc

mappings = [
    # 單一設備模式
    ContextMapping(
        point_name="soc",
        context_field="soc",  # -> context.soc
        device_id="bms_001",
    ),
    # Trait 模式 + 聚合
    ContextMapping(
        point_name="power",
        context_field="extra.meter_power",  # -> context.extra["meter_power"]
        trait="meter",
        aggregate=AggregateFunc.SUM,
        default=0.0,
    ),
]
```

| [[AggregateFunc]] | 說明 |
|-------------------|------|
| `AVERAGE` | 平均值 |
| `SUM` | 加總 |
| `MIN` | 最小值 |
| `MAX` | 最大值 |
| `FIRST` | 取第一台設備的值 |

### CommandMapping

使用 [[CommandMapping]] 將 [[Command]] 欄位路由到設備寫入：

```python
from csp_lib.integration import CommandMapping

command_mappings = [
    CommandMapping(
        command_field="p_target",
        point_name="p_setpoint",
        trait="pcs",
        transform=lambda p: p / num_pcs,  # 均分功率
    ),
]
```

### DataFeedMapping

使用 [[DataFeedMapping]] 將設備值餵入 [[PVDataService]]：

```python
from csp_lib.integration import DataFeedMapping

data_feed = DataFeedMapping(
    point_name="pv_power",
    trait="solar",
)
```

---

## 3a. 使用 GridControlLoop（基本整合）

[[GridControlLoop]] 提供基本的控制迴圈編排，適合單一策略的簡單場景。

```python
from csp_lib.integration import GridControlLoop, GridControlLoopConfig
from csp_lib.controller import PQModeStrategy, PQModeConfig, SystemBase

config = GridControlLoopConfig(
    context_mappings=mappings,
    command_mappings=command_mappings,
    system_base=SystemBase(p_base=1000, q_base=500),
    data_feed_mapping=DataFeedMapping(point_name="pv_power", trait="solar"),
    pv_max_history=300,
)

loop = GridControlLoop(registry, config)
await loop.set_strategy(PQModeStrategy(PQModeConfig(p=200)))

async with loop:
    # 自動執行: ContextBuilder -> StrategyExecutor -> CommandRouter
    await asyncio.sleep(3600)
```

---

## 3b. 使用 SystemController（進階整合）

[[SystemController]] 提供進階功能，整合 [[ModeManager]] + [[ProtectionGuard]]，適合需要多模式切換與保護的場景。

```python
from csp_lib.integration import SystemController, SystemControllerConfig
from csp_lib.controller import (
    ModePriority, SOCProtection, SOCProtectionConfig,
    ReversePowerProtection, SystemAlarmProtection,
)

config = SystemControllerConfig(
    context_mappings=mappings,
    command_mappings=command_mappings,
    system_base=SystemBase(p_base=1000, q_base=500),
    protection_rules=[
        SOCProtection(SOCProtectionConfig(soc_high=95, soc_low=5, warning_band=5)),
        ReversePowerProtection(threshold=0),
        SystemAlarmProtection(),
    ],
    auto_stop_on_alarm=True,
    capacity_kva=1000,  # 啟用 CascadingStrategy 支援多 base mode
)

controller = SystemController(registry, config)

# 註冊模式
controller.register_mode("schedule", schedule_strategy, ModePriority.SCHEDULE)
controller.register_mode("manual", pq_strategy, ModePriority.MANUAL)

# 設定基底模式
await controller.set_base_mode("schedule")

async with controller:
    # 完整控制迴圈:
    #   ContextBuilder -> StrategyContext (注入 system_alarm)
    #   StrategyExecutor (策略由 ModeManager 決定)
    #   Command -> ProtectionGuard -> CommandRouter -> 設備寫入
    await asyncio.sleep(3600)
```

### SystemController 內部流程

```
ContextBuilder.build() -> StrategyContext (inject system_alarm)
       |
       v
StrategyExecutor (strategy decided by ModeManager)
       |
       v
Command (raw) -> ProtectionGuard.apply() -> Command (protected)
       |
       v
CommandRouter.route() -> Device writes
```

---

## 3c. 使用 GroupControllerManager（多群組整合）

[[GroupControllerManager]] 適用於需要將設備分成多個獨立控制群組的場景，例如多台 PCS/BESS 各自獨立控制。每組擁有獨立的 [[SystemController]]，包含獨立的模式管理、保護機制與策略執行。

```python
from csp_lib.integration import (
    GroupControllerManager, GroupDefinition,
    SystemControllerConfig, DeviceRegistry,
)
from csp_lib.controller import ModePriority

# 建立 master registry
registry = DeviceRegistry()
registry.register(pcs_1, traits=["pcs"])
registry.register(bess_1, traits=["bess"])
registry.register(pcs_2, traits=["pcs"])
registry.register(bess_2, traits=["bess"])

# 定義群組
manager = GroupControllerManager(
    registry=registry,
    groups=[
        GroupDefinition(
            group_id="group1",
            device_ids=["pcs_1", "bess_1"],
            config=SystemControllerConfig(
                context_mappings=[
                    ContextMapping(trait="bess", point_name="soc", context_field="soc"),
                ],
                command_mappings=[
                    CommandMapping(command_field="p_target", trait="pcs", point_name="p_setpoint"),
                ],
                system_base=SystemBase(p_base=500),
            ),
        ),
        GroupDefinition(
            group_id="group2",
            device_ids=["pcs_2", "bess_2"],
            config=SystemControllerConfig(
                context_mappings=[
                    ContextMapping(trait="bess", point_name="soc", context_field="soc"),
                ],
                command_mappings=[
                    CommandMapping(command_field="p_target", trait="pcs", point_name="p_setpoint"),
                ],
                system_base=SystemBase(p_base=500),
            ),
        ),
    ],
)

# 各群組獨立註冊策略
manager.register_mode("group1", "pq", pq_strategy_1, ModePriority.MANUAL)
manager.register_mode("group2", "pv_smooth", pv_strategy_2, ModePriority.MANUAL)
await manager.set_base_mode("group1", "pq")
await manager.set_base_mode("group2", "pv_smooth")

async with manager:
    # 各群組獨立執行控制迴圈
    await asyncio.Event().wait()
```

### 關鍵特性

- **設備隔離**：每組設備在獨立的子 `DeviceRegistry` 中，trait 查詢僅限於該群組
- **策略獨立**：各群組可使用不同策略、不同保護規則
- **告警隔離**：一組設備告警不影響其他群組
- **共享實例**：子 Registry 持有與 master 相同的設備實例（非複製），節省記憶體

---

## 相關頁面

- [[Quick Start]] - 快速入門
- [[Device Setup]] - 設備設定
- [[Control Strategy Setup]] - 控制策略設定
- [[Cluster HA Setup]] - 叢集高可用設定
