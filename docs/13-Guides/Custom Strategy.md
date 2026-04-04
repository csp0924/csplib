---
tags:
  - type/guide
  - layer/controller
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: ">=0.4.2"
---

# 自訂策略指南

本指南說明如何實作自訂控制策略，透過繼承 [[Strategy]] ABC 並實作 `execute()` 方法。

## 步驟總覽

1. 繼承 `Strategy` 基底類別
2. 定義 `execution_config` 屬性
3. 實作 `execute()` 方法
4. （可選）實作生命週期 hooks
5. 使用 [[StrategyExecutor]] 執行

---

## 基本範例

```python
from csp_lib.controller import Strategy, ExecutionConfig, ExecutionMode, StrategyContext, Command

class MyStrategy(Strategy):
    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command(p_target=100.0)

    async def on_activate(self) -> None:
        ...  # 可選：策略啟用時呼叫

    async def on_deactivate(self) -> None:
        ...  # 可選：策略停用時呼叫
```

---

## 詳細說明

### execution_config

定義策略的執行模式與間隔：

```python
@property
def execution_config(self) -> ExecutionConfig:
    return ExecutionConfig(
        mode=ExecutionMode.PERIODIC,   # PERIODIC / TRIGGERED / HYBRID
        interval_seconds=1,            # 執行間隔（秒）
    )
```

| [[ExecutionMode]] | 說明 |
|-------------------|------|
| `PERIODIC` | 固定週期執行 |
| `TRIGGERED` | 僅在外部觸發時執行 |
| `HYBRID` | 週期執行，但可被提前觸發 |

### execute()

策略核心邏輯。接收 [[StrategyContext]]，回傳 [[Command]]。

```python
def execute(self, context: StrategyContext) -> Command:
    # 使用 context 中的資料
    soc = context.soc
    voltage = context.extra.get("voltage", 0)
    last_p = context.last_command.p_target

    # 計算新的功率命令
    p_target = calculate_power(soc, voltage)

    # 百分比轉 kW（使用 system_base）
    p_kw = context.percent_to_kw(50)  # 50% -> kW

    return Command(p_target=p_target, q_target=0)
```

### StrategyContext 可用資料

| 欄位 | 型別 | 說明 |
|------|------|------|
| `last_command` | `Command` | 上一次執行的命令 |
| `soc` | `float` | 電池 SOC (%) |
| `system_base` | `SystemBase` | 系統基準值 |
| `current_time` | `datetime` | 當前時間（由 Executor 注入） |
| `extra` | `dict` | 額外資料字典 |

### 生命週期 Hooks

```python
async def on_activate(self) -> None:
    """策略啟用時呼叫（例如：初始化資源）"""
    self.logger.info("Strategy activated")

async def on_deactivate(self) -> None:
    """策略停用時呼叫（例如：清理資源）"""
    self.logger.info("Strategy deactivated")
```

---

## 含配置的策略

使用 [[ConfigMixin]] 讓策略支援動態配置更新：

```python
from dataclasses import dataclass
from csp_lib.controller import Strategy, ConfigMixin, ExecutionConfig, ExecutionMode

@dataclass(frozen=True)
class MyConfig(ConfigMixin):
    target_power: float = 100.0
    ramp_rate: float = 10.0

class MyConfigurableStrategy(Strategy):
    def __init__(self, config: MyConfig):
        self._config = config

    def update_config(self, config: MyConfig) -> None:
        self._config = config

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command(p_target=self._config.target_power)

# 從字典建立配置（支援 camelCase 轉換）
config = MyConfig.from_dict({"targetPower": 200, "rampRate": 5})
```

---

## 使用 StrategyExecutor 執行

```python
from csp_lib.controller import StrategyExecutor

executor = StrategyExecutor(
    context_provider=get_context,
    on_command=handle_command,
)

strategy = MyStrategy()
await executor.set_strategy(strategy)  # 觸發 on_activate
await executor.run()                   # 開始執行迴圈
```

---

## required_capabilities（v0.4.2 新增）

覆寫 `required_capabilities` 屬性，宣告策略所需的設備能力。`SystemController` 在 `register_mode()` 時自動驗證，若找不到符合的設備會記錄警告（不拋出例外）：

```python
from csp_lib.controller.core import Strategy, ExecutionConfig, ExecutionMode, Command, StrategyContext
from csp_lib.equipment.device.capability import Capability

# 定義需要的 capability（必須與 DeviceRegistry 中的設備 capability 一致）
SOC_READABLE = Capability("soc_readable", read_slots=("soc",))
POWER_WRITABLE = Capability("power_writable", write_slots=("p_target", "q_target"))


class MyBatteryStrategy(Strategy):
    """需要 SOC 讀取能力和功率寫入能力的策略"""

    @property
    def required_capabilities(self) -> tuple[Capability, ...]:
        """聲明此策略所需的設備能力。SystemController 在 register_mode() 時驗證。"""
        return (SOC_READABLE, POWER_WRITABLE)

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        soc = context.soc
        return Command(p_target=100.0 if soc > 20 else 0.0)


# SystemController 的 register_mode() 會自動驗證
controller.register_mode("battery_ctrl", MyBatteryStrategy(), ModePriority.SCHEDULE)
# 若無設備具備 soc_readable 能力，會記錄警告但仍然完成註冊
```

---

## 策略插件發現機制（v0.4.2 新增）

使用 `discover_strategies()` 自動掃描已安裝的第三方策略插件。插件透過 `pyproject.toml` 的 entry_points 機制註冊：

### 第三方套件發布策略

在你的套件 `pyproject.toml` 中新增 entry_points：

```toml
[project.entry-points."csp_lib.strategies"]
my_pq = "my_package.strategies:CustomPQStrategy"
my_island = "my_package.strategies:CustomIslandStrategy"
```

### 掃描已安裝策略

```python
from csp_lib.controller.discovery import discover_strategies, ENTRY_POINT_GROUP

# 自動掃描所有已安裝的策略插件
descriptors = discover_strategies()
for desc in descriptors:
    print(f"Strategy: {desc.name}")
    print(f"  Class:   {desc.strategy_class.__name__}")
    print(f"  Module:  {desc.module}")
    print(f"  Desc:    {desc.description}")

# 也可掃描自訂群組
custom_plugins = discover_strategies(group="myapp.strategies")
```

```python
# StrategyDescriptor 欄位
from csp_lib.controller.discovery import StrategyDescriptor

desc: StrategyDescriptor
desc.name            # entry point 名稱（str）
desc.strategy_class  # 策略類別（type[Strategy]）
desc.module          # 策略所在模組路徑（str）
desc.description     # 策略說明（來自 docstring 第一行）
```

> [!tip] 自動整合
> 可結合 `discover_strategies()` 與 `SystemController.register_mode()` 實現插件式策略熱載入。

---

## 相關頁面

- [[Control Strategy Setup]] - 內建策略總覽
- [[Full System Integration]] - 完整系統整合
