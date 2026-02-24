---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/island_strategy.py
created: 2026-02-17
---

# IslandModeStrategy

離網模式策略 (Grid Forming / Island Mode)。

> [!info] 回到 [[_MOC Controller]]

## 概述

當策略啟用時，自動切離 ACB (Air Circuit Breaker) 進入離網模式；停用時，等待同步訊號 (sync_ok) 後自動搭接 ACB 返回併網模式。使用 TRIGGERED 模式，不主動發送功率命令，功率控制由 PCS 自身的 VF 模式處理。

## RelayProtocol

繼電器/斷路器控制協定 (`@runtime_checkable Protocol`)。IslandModeStrategy 依賴此協定操作 ACB。

| 成員 | 類型 | 說明 |
|------|------|------|
| `sync_ok` | `property -> bool` | 同步狀態 |
| `sync_counter` | `property -> int` | 同步計數 |
| `set_open()` | `async method` | 開啟斷路器 |
| `set_close()` | `async method` | 閉合斷路器 (需 sync_ok) |
| `set_force_close()` | `async method` | 強制閉合斷路器 |

## IslandModeConfig

繼承 [[ConfigMixin]]，搭配 `@dataclass` 使用。

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `sync_timeout` | `float` | `60.0` | 等待 sync_ok 超時 (秒) |

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | `TRIGGERED` |
| 說明 | 不主動執行，`execute()` 維持 `last_command` |

## 生命週期

### on_activate()

1. 呼叫 `relay.set_open()` 開啟 ACB
2. 系統進入離網 (孤島) 模式

### on_deactivate()

1. 等待 `relay.sync_ok` 變為 `True`（每 0.5 秒檢查一次）
2. 超時未同步 -> 記錄 CRITICAL 日誌，需手動處理
3. 同步成功 -> 呼叫 `relay.set_close()` 閉合 ACB，返回併網模式

## 程式碼範例

```python
from csp_lib.controller import IslandModeStrategy, IslandModeConfig, RelayProtocol

strategy = IslandModeStrategy(
    relay=my_relay,  # Implements RelayProtocol
    config=IslandModeConfig(sync_timeout=60),
)
# on_activate: opens ACB (enters island mode)
# on_deactivate: waits for sync_ok, then closes ACB (returns to grid)
```

## 相關連結

- [[Strategy]] — 基礎類別
- [[StrategyExecutor]] — `set_strategy()` 時自動呼叫 on_activate / on_deactivate
- [[ModeManager]] — 常註冊為 PROTECTION 等級的 override 模式
