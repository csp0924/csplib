---
tags:
  - type/guide
  - layer/integration
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
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

### SystemControllerConfigBuilder（Fluent API）

使用 `SystemControllerConfig.builder()` 以鏈式呼叫逐步建構配置：

```python
from csp_lib.integration import SystemControllerConfig
from csp_lib.controller import SOCProtection, SOCProtectionConfig

config = (
    SystemControllerConfig.builder()
    .system_base(p_base=1000, q_base=500)
    .map_context(point_name="soc", target="soc", device_id="bms_001")
    .map_context(point_name="power", target="extra.meter_power", trait="meter")
    .map_command(field="p_target", trait="pcs", point_name="p_setpoint")
    .protect(SOCProtection(SOCProtectionConfig(soc_high=95, soc_low=5, warning_band=5)))
    .processor(compensator)  # CommandProcessor 管線
    .build()
)
```

### preflight_check（啟動前驗證）

`SystemController` 在 `_on_start()` 時自動呼叫 `preflight_check()`，驗證 capability_requirements 是否滿足。也可手動呼叫：

```python
controller = SystemController(registry, config)
warnings = controller.preflight_check()
# warnings 為空表示所有能力需求皆滿足
for w in warnings:
    print(f"Warning: {w}")
```

設定 `strict_capability_check=True` 時，preflight 失敗會拋出 `ConfigurationError`。

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
[CommandProcessor 1] -> [CommandProcessor 2] -> ... (post_protection_processors)
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

## PowerDistributor：多機功率分配

當系統有多台 PCS 或 BESS 需要分配功率時，使用 [[PowerDistributor]] 搭配 `capability_command_mappings` 進行 per-device 智能分配：

```python
from csp_lib.integration import SystemController, SystemControllerConfig
from csp_lib.integration.distributor import (
    EqualDistributor,
    ProportionalDistributor,
    SOCBalancingDistributor,
)
from csp_lib.integration import CapabilityCommandMapping, CapabilityContextMapping

# --- 分配器選擇 ---

# 1. 均分（所有設備相同規格）
distributor = EqualDistributor()

# 2. 按額定容量比例分配（設備規格不同時）
distributor = ProportionalDistributor(rated_key="rated_p")
# 設備 A rated_p=500kW, 設備 B rated_p=1000kW → A 分 1/3, B 分 2/3

# 3. SOC 平衡分配（放電時高 SOC 多放，充電時低 SOC 多充）
distributor = SOCBalancingDistributor(
    rated_key="rated_p",
    soc_capability="soc_readable",
    soc_slot="soc",
    gain=2.0,
)

# --- 配置 SystemController ---
config = SystemControllerConfig(
    # 使用 capability 映射取代點位映射，支援 per-device 路由
    capability_context_mappings=[
        CapabilityContextMapping(
            capability_name="soc_readable",
            slot="soc",
            context_field="soc",         # → context.soc（取第一台設備）
        ),
    ],
    capability_command_mappings=[
        CapabilityCommandMapping(
            capability_name="power_writable",
            slot="p_target",
            command_field="p_target",    # 從 Command.p_target 分配到各設備
        ),
        CapabilityCommandMapping(
            capability_name="power_writable",
            slot="q_target",
            command_field="q_target",
        ),
    ],
    # 啟用 PowerDistributor
    power_distributor=distributor,
    # ... 其他配置
)
```

> [!note] 運作方式
> 設定 `power_distributor` 後，`SystemController` 在每次 `_on_command()` 時：
> 1. 呼叫 `distributor.distribute(protected_command, device_snapshots)`
> 2. 取得每台設備的個別 `Command`
> 3. 透過 `CommandRouter.route_per_device()` 將個別命令寫入對應設備

### DeviceSnapshot

`PowerDistributor.distribute()` 接收的 `DeviceSnapshot` 包含：

| 欄位 | 說明 |
|------|------|
| `device_id` | 設備唯一識別碼 |
| `metadata` | 註冊時的靜態資訊（`rated_p`、`rated_s` 等） |
| `latest_values` | 設備最新讀取值 |
| `capabilities` | `capability_name → {slot: value}` 的映射 |

```python
# 在 DeviceRegistry 注冊時提供 metadata
registry.register(pcs_1, traits=["pcs"], metadata={"rated_p": 500.0, "rated_s": 600.0})
registry.register(pcs_2, traits=["pcs"], metadata={"rated_p": 1000.0, "rated_s": 1200.0})
```

### 自訂 PowerDistributor

實作 `PowerDistributor` Protocol 可自訂分配邏輯：

```python
from csp_lib.integration.distributor import PowerDistributor, DeviceSnapshot
from csp_lib.controller.core import Command


class TemperatureBasedDistributor:
    """根據設備溫度調整分配（低溫設備多充）"""

    def distribute(self, command: Command, devices: list[DeviceSnapshot]) -> dict[str, Command]:
        if not devices:
            return {}
        # 取得各設備溫度（從 latest_values）
        temps = [d.latest_values.get("temperature", 25.0) for d in devices]
        avg_temp = sum(temps) / len(temps)
        # 低溫多充，計算權重
        weights = [max(0.1, avg_temp - t + 1.0) for t in temps]
        total = sum(weights)
        return {
            d.device_id: Command(
                p_target=command.p_target * w / total,
                q_target=command.q_target / len(devices),
            )
            for d, w in zip(devices, weights, strict=True)
        }
```

---

## 相關頁面

- [[Quick Start]] - 快速入門
- [[Device Setup]] - 設備設定
- [[Control Strategy Setup]] - 控制策略設定
- [[Cluster HA Setup]] - 叢集高可用設定
- [[PowerDistributor]] - 功率分配器 API 參考
