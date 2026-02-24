---
tags:
  - type/guide
  - layer/controller
  - status/complete
created: 2026-02-17
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

csp_lib 提供 8 種內建策略：

| 策略 | 類別 | 用途 | 配置類別 | 執行模式 |
|------|------|------|----------|---------|
| PQ 模式 | [[PQModeStrategy]] | 固定 P/Q 輸出 | `PQModeConfig(p, q)` | PERIODIC 1s |
| PV 平滑 | [[PVSmoothStrategy]] | PV 功率平滑化 | `PVSmoothConfig(capacity, ramp_rate, ...)` | PERIODIC 900s |
| QV 控制 | [[QVStrategy]] | 電壓-無功功率控制 (Volt-VAR) | `QVConfig(nominal_voltage, v_set, droop, ...)` | PERIODIC 1s |
| FP 控制 | [[FPStrategy]] | 頻率-功率控制 (AFC) | `FPConfig(f_base, f1~f6, p1~p6)` | PERIODIC 1s |
| 離網模式 | [[IslandModeStrategy]] | 離網 Grid Forming | `IslandModeConfig(sync_timeout)` | TRIGGERED |
| 直通模式 | [[BypassStrategy]] | 維持上一次命令 | -- | PERIODIC 1s |
| 停機 | [[StopStrategy]] | P=0, Q=0 | -- | PERIODIC 1s |
| 排程 | [[ScheduleStrategy]] | 依時間表執行 | -- | PERIODIC 1s |

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

## 相關頁面

- [[Quick Start]] - 快速入門
- [[Custom Strategy]] - 自訂策略
- [[Full System Integration]] - 完整系統整合
