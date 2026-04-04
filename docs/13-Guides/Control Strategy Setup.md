---
tags:
  - type/guide
  - layer/controller
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
---

# 控制策略設定指南

本指南說明如何選擇、配置與執行控制策略。

## 步驟總覽

1. 選擇適合的策略
2. 建立策略配置
3. 建立 [[StrategyExecutor]]
4. 設定策略並執行

---

## 1. 選擇策略

csp_lib 提供 12 種內建策略：

| 策略 | 類別 | 用途 | 配置類別 | 執行模式 |
|------|------|------|----------|---------|
| PQ 模式 | [[PQModeStrategy]] | 固定 P/Q 輸出 | `PQModeConfig(p, q)` | PERIODIC 1s |
| PV 平滑 | [[PVSmoothStrategy]] | PV 功率平滑化 | `PVSmoothConfig(capacity, ramp_rate, ...)` | PERIODIC 900s |
| QV 控制 | [[QVStrategy]] | 電壓-無功功率控制 (Volt-VAR) | `QVConfig(nominal_voltage, v_set, droop, ...)` | PERIODIC 1s |
| FP 控制 | [[FPStrategy]] | 頻率-功率控制 (AFC) | `FPConfig(f_base, f1~f6, p1~p6)` | PERIODIC 1s |
| 通用下垂 | [[DroopStrategy]] | 通用下垂控制 | `DroopConfig(...)` | PERIODIC 1s |
| 離網模式 | [[IslandModeStrategy]] | 離網 Grid Forming | `IslandModeConfig(sync_timeout)` | TRIGGERED |
| 直通模式 | [[BypassStrategy]] | 維持上一次命令 | -- | PERIODIC 1s |
| 停機 | [[StopStrategy]] | P=0, Q=0 | -- | PERIODIC 1s |
| 斜率停機 | [[RampStopStrategy]] | 漸進式降載停機 | `RampStopConfig(...)` | PERIODIC 1s |
| 排程 | [[ScheduleStrategy]] | 依時間表執行 | -- | PERIODIC 1s |
| 負載卸載 | [[LoadSheddingStrategy]] | 階段性���載卸載 | `LoadSheddingConfig(stages, ...)` | PERIODIC 5s |
| FF 校準 | [[FFCalibrationStrategy]] | 維護模式 FF 表校準 | `FFCalibrationConfig(...)` | PERIODIC |

---

## 2. 建立策略配置

每個策略有對應的配置類別。所有配置類別支援 `from_dict()` 與 camelCase 轉換。

### PQ 模式

```python
from csp_lib.controller import PQModeStrategy, PQModeConfig

config = PQModeConfig(p=100, q=50)
strategy = PQModeStrategy(config)

# 動態更新配置
strategy.update_config(PQModeConfig(p=200, q=0))
```

### PV 平滑

```python
from csp_lib.controller import PVSmoothStrategy, PVSmoothConfig, PVDataService

pv_service = PVDataService(max_history=300)
strategy = PVSmoothStrategy(
    PVSmoothConfig(capacity=1000, ramp_rate=10, pv_loss=5),
    pv_service=pv_service,
)
# 外部餵入 PV 功率資料
pv_service.append(current_pv_power)
```

### QV 控制

```python
from csp_lib.controller import QVStrategy, QVConfig

strategy = QVStrategy(QVConfig(
    nominal_voltage=380,
    v_set=100,      # 目標電壓 (%)
    droop=5,        # 下垂係數 (%)
    v_deadband=0,   # 死區 (%)
    q_max_ratio=0.5,
))
# 從 context.extra["voltage"] 讀取電壓
```

### FP 控制 (AFC)

```python
from csp_lib.controller import FPStrategy, FPConfig

strategy = FPStrategy(FPConfig(
    f_base=60.0,
    f1=-0.5, f2=-0.25, f3=-0.02, f4=0.02, f5=0.25, f6=0.5,
    p1=100, p2=52, p3=9, p4=-9, p5=-52, p6=-100,
))
# 從 context.extra["frequency"] 讀取頻率
```

### 離網模式

```python
from csp_lib.controller import IslandModeStrategy, IslandModeConfig, RelayProtocol

strategy = IslandModeStrategy(
    relay=my_relay,  # 實作 RelayProtocol
    config=IslandModeConfig(sync_timeout=60),
)
```

---

## 3. 建立 StrategyExecutor

[[StrategyExecutor]] 管理策略的執行生命週期。

```python
from csp_lib.controller import StrategyExecutor, StrategyContext, SystemBase

executor = StrategyExecutor(
    context_provider=lambda: StrategyContext(
        soc=75.0,
        system_base=SystemBase(p_base=1000, q_base=500),
        extra={"voltage": 380.0, "frequency": 60.0},
    ),
    on_command=handle_command,  # 可選：命令回呼
)
```

---

## 4. 設定策略並執行

```python
# 設定策略（自動呼叫 on_activate / on_deactivate）
await executor.set_strategy(strategy)

# 主執行迴圈
await executor.run()

# 手動觸發（TRIGGERED / HYBRID 模式）
executor.trigger()

# 停止迴圈
executor.stop()

# 單次執行（測試用）
command = await executor.execute_once()
```

---

## 執行模式

| 模式 | 說明 |
|------|------|
| `PERIODIC` | 固定週期執行 |
| `TRIGGERED` | 僅在外部觸發時執行 |
| `HYBRID` | 週期執行，但可被提前觸發 |

---

## 進階功能

### ModeManager

使用 [[ModeManager]] 管理多種模式的優先權切換：

```python
from csp_lib.controller import ModeManager, ModePriority

manager = ModeManager(on_strategy_change=handle_change)
manager.register("schedule", schedule_strategy, ModePriority.SCHEDULE)   # 10
manager.register("manual", pq_strategy, ModePriority.MANUAL)             # 50
manager.register("protection", stop_strategy, ModePriority.PROTECTION)   # 100

await manager.set_base_mode("schedule")
await manager.push_override("protection")  # 最高優先權生效
await manager.pop_override("protection")   # 回到 schedule
```

### ProtectionGuard

使用 [[ProtectionGuard]] 進行命令保護：

```python
from csp_lib.controller import ProtectionGuard, SOCProtection, SOCProtectionConfig

guard = ProtectionGuard(rules=[
    SOCProtection(SOCProtectionConfig(soc_high=95, soc_low=5, warning_band=5)),
])
result = guard.apply(command, context)
```

### CascadingStrategy

使用 [[CascadingStrategy]] 進行多策略級聯功率分配：

```python
from csp_lib.controller import CascadingStrategy, CapacityConfig

cascading = CascadingStrategy(
    layers=[pq_strategy, qv_strategy],
    capacity=CapacityConfig(s_max_kva=1000),
)
```

---

## 進階功能

### LoadSheddingStrategy（負載卸載）

使用 [[LoadSheddingStrategy]] 在離網或緊急場景中按優先順序逐階卸載/恢復負載：

```python
from csp_lib.controller.strategies.load_shedding import (
    LoadSheddingStrategy,
    LoadSheddingConfig,
    ShedStage,
    ThresholdCondition,
    RemainingTimeCondition,
)

# 定義卸載條件
soc_condition = ThresholdCondition(
    context_key="soc",
    shed_below=20.0,    # SOC < 20% 時卸載
    restore_above=30.0, # SOC > 30% 時恢復
)
time_condition = RemainingTimeCondition(
    context_key="battery_remaining_minutes",
    shed_below=30.0,    # 剩餘時間 < 30 分鐘時卸載
    restore_above=45.0,
)

# 定義負載迴路（需實作 LoadCircuitProtocol）
class MyCircuit:
    def __init__(self, name: str):
        self._name = name
        self._is_shed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_shed(self) -> bool:
        return self._is_shed

    async def shed(self) -> None:
        self._is_shed = True
        # 執行實際斷路動作（例如寫入斷路器命令）

    async def restore(self) -> None:
        self._is_shed = False

# 定義卸載階段（priority 低的先卸）
config = LoadSheddingConfig(
    stages=[
        ShedStage(
            name="stage1_non_critical",
            circuits=[MyCircuit("air_conditioner"), MyCircuit("water_heater")],
            condition=soc_condition,
            priority=0,          # 最先卸載
            min_hold_seconds=30, # 最少卸載 30 秒
        ),
        ShedStage(
            name="stage2_semi_critical",
            circuits=[MyCircuit("ev_charger")],
            condition=time_condition,
            priority=1,
            min_hold_seconds=60,
        ),
    ],
    evaluation_interval=5,          # 每 5 秒評估一次
    restore_delay=60.0,             # 條件解除後延遲 60 秒才恢復
    auto_restore_on_deactivate=True, # 策略停用時自動恢復所有負載
)

strategy = LoadSheddingStrategy(config)

# 查詢當前卸載階段
print(strategy.shed_stage_names)  # ["stage1_non_critical"]
```

> [!note] 背景動作
> `LoadSheddingStrategy.execute()` 只進行條件評估，實際的 `circuit.shed()` / `circuit.restore()` 由背景 asyncio Task 執行，不阻塞策略迴圈。

---

### EventDrivenOverride（事件驅動 Override）

使用 [[EventDrivenOverride]] 讓 `SystemController` 根據 `StrategyContext` 條件自動推入/彈出 override，取代手動呼叫 `push_override()` / `pop_override()`：

```python
from csp_lib.controller.system.event_override import (
    AlarmStopOverride,
    ContextKeyOverride,
)
from csp_lib.integration import SystemController, SystemControllerConfig
from csp_lib.controller.system import ModePriority
from csp_lib.controller.strategies import StopStrategy

# SystemControllerConfig 預設已包含 AlarmStopOverride（auto_stop_on_alarm=True）
# 自動在任何設備告警時推入 __auto_stop__ 模式

# 手動新增自訂 ContextKeyOverride
controller = SystemController(registry, config)

# 新增：ACB 跳脫時自動進入離網模式
controller.register_mode("island", island_strategy, ModePriority.PROTECTION)
acb_override = ContextKeyOverride(
    name="island",
    context_key="acb_tripped",       # 監測 context.extra["acb_tripped"]
    activate_when=lambda v: v is True,
    cooldown_seconds=5.0,            # 條件解除後冷卻 5 秒才退出 override
)
controller.register_event_override(acb_override)

# 新增：頻率偏差過大時自動進入 FP 模式
controller.register_mode("fp_emergency", fp_strategy, ModePriority.PROTECTION - 1)
freq_override = ContextKeyOverride(
    name="fp_emergency",
    context_key="frequency",
    activate_when=lambda f: abs(f - 60.0) > 0.5,
    cooldown_seconds=10.0,
)
controller.register_event_override(freq_override)
```

| 類別 | 用途 |
|------|------|
| `AlarmStopOverride` | 設備告警時自動停機（`SystemController` 預設使用） |
| `ContextKeyOverride` | 通用：根據 `context.extra` 中的 key 值觸發任意 override |

---

## 相關頁面

- [[Quick Start]] - 快速入門
- [[Custom Strategy]] - 自訂策略
- [[Full System Integration]] - 完整系統整合
