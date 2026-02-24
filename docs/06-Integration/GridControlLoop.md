---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/loop.py
---

# GridControlLoop

完整控制迴圈編排器，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`GridControlLoop` 組合所有整合元件，提供從設備讀取到策略執行再到設備寫入的完整控制迴圈。繼承 `AsyncLifecycleMixin`，支援 `async with` 使用。

### 內部元件編排

- [[ContextBuilder]]：設備值 → `StrategyContext`
- `StrategyExecutor`：週期性策略執行
- [[CommandRouter]]：`Command` → 設備寫入
- [[DeviceDataFeed]]：事件 → `PVDataService`（可選）

## GridControlLoopConfig

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `context_mappings` | `list[ContextMapping]` | `[]` | 設備點位 → StrategyContext 映射 |
| `command_mappings` | `list[CommandMapping]` | `[]` | Command 欄位 → 設備寫入映射 |
| `system_base` | `SystemBase \| None` | `None` | 系統基準值 |
| `data_feed_mapping` | [[DataFeedMapping]] `\| None` | `None` | PV 資料餵入映射（設定時自動建立 PVDataService） |
| `pv_max_history` | `int` | `300` | PVDataService 最大歷史記錄數 |

## API

| 方法 | 說明 |
|------|------|
| `set_strategy(strategy)` | 設定/切換策略，委派給內部 StrategyExecutor |
| `trigger()` | 手動觸發策略執行（適用於 TRIGGERED / HYBRID 模式） |

### 唯讀屬性

| 屬性 | 說明 |
|------|------|
| `registry` | 設備查詢索引 |
| `executor` | 內部的策略執行器 |
| `pv_service` | PV 資料服務（未設定 DataFeedMapping 時為 `None`） |
| `is_running` | 控制迴圈是否正在執行 |

## 生命週期

- `async with loop:` → 呼叫 `_on_start()` / `_on_stop()`
- 啟動時：attach data feed + 建立 executor 背景任務
- 停止時：stop executor + await 任務完成 + detach data feed

## 使用範例

```python
from csp_lib.integration import GridControlLoop, GridControlLoopConfig

config = GridControlLoopConfig(
    context_mappings=[...],
    command_mappings=[...],
    system_base=SystemBase(p_base=1000, q_base=500),
    data_feed_mapping=DataFeedMapping(point_name="pv_power", trait="solar"),
    pv_max_history=300,
)

loop = GridControlLoop(registry, config)
await loop.set_strategy(strategy)

async with loop:
    # Auto runs: ContextBuilder -> StrategyExecutor -> CommandRouter
    await asyncio.sleep(3600)
```

## 相關頁面

- [[SystemController]] — 進階版本，整合 ModeManager + ProtectionGuard
- [[ContextBuilder]] — 設備值建構器
- [[CommandRouter]] — 命令路由器
- [[DeviceDataFeed]] — PV 資料餵入
- [[DeviceRegistry]] — 設備查詢索引
