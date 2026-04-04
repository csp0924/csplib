---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/bypass_strategy.py
created: 2026-02-17
updated: 2026-04-04
---

# BypassStrategy

旁路策略 (Bypass Mode)，維持 last_command 不變。

> [!info] 回到 [[_MOC Controller]]

## 概述

完全不發送任何新指令，使用 TRIGGERED 模式不會主動執行。`execute()` 直接回傳 `context.last_command`，讓使用者可透過外部方式直接控制設備。

`suppress_heartbeat` 覆寫為 `True`，暫停心跳寫入，讓設備知道控制器已釋放控制權。

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | `TRIGGERED` |
| `suppress_heartbeat` | `True` |
| 說明 | 不主動執行，暫停心跳 |

## 使用情境

- 手動調試設備
- 臨時接管控制權
- 維護模式

## 行為

- `execute(context)` -> 回傳 `context.last_command`
- 無需配置、無內部狀態
- `suppress_heartbeat = True` — 暫停心跳寫入

## Quick Example

```python
from csp_lib.controller import BypassStrategy, ModeManager, ModePriority

manager = ModeManager()
manager.register("bypass", BypassStrategy(), ModePriority.MANUAL)
await manager.set_base_mode("bypass")
# 控制器停止發送命令與心跳，設備可手動操作
```

## 相關連結

- [[Strategy]] — 基礎類別（`suppress_heartbeat` 屬性定義於此）
- [[Command]] — 維持 last_command
- [[ModeManager]] — 可作為 MANUAL 優先權的模式
- [[StopStrategy]] — 類似但會主動發送 P=0, Q=0 且不暫停心跳
