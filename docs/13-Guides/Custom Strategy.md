---
tags:
  - type/guide
  - layer/controller
  - status/complete
created: 2026-02-17
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

## 相關頁面

- [[Control Strategy Setup]] - 內建策略總覽
- [[Full System Integration]] - 完整系統整合
