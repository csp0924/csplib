---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/strategies/bypass_strategy.py
created: 2026-02-17
---

# BypassStrategy

旁路策略 (Bypass Mode)，維持 last_command 不變。

> [!info] 回到 [[_MOC Controller]]

## 概述

完全不發送任何新指令，使用 TRIGGERED 模式不會主動執行。`execute()` 直接回傳 `context.last_command`，讓使用者可透過外部方式直接控制設備。

## 執行配置

| 項目 | 值 |
|------|---|
| 模式 | `TRIGGERED` |
| 說明 | 不主動執行 |

## 使用情境

- 手動調試設備
- 臨時接管控制權
- 維護模式

## 行為

- `execute(context)` -> 回傳 `context.last_command`
- 無需配置、無內部狀態
- GridController 的 command loop 會跳過此策略

## 相關連結

- [[Strategy]] — 基礎類別
- [[Command]] — 維持 last_command
- [[ModeManager]] — 可作為 MANUAL 優先權的模式
