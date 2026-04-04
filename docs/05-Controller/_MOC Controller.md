---
tags:
  - type/moc
  - layer/controller
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: ">=0.4.2"
---

# Controller 模組總覽

Controller 層負責控制策略的定義、執行與系統管理。位於 [[_MOC Equipment]] 之上、[[_MOC Integration]] 之下，將設備讀值轉化為功率控制命令。

## 架構概覽

```
StrategyExecutor ─── Strategy.execute(context) ──→ Command
       │                     │
       │              StrategyContext (注入)
       │
  ModeManager ──→ 模式切換 (base / override)
  ProtectionGuard ──→ 保護規則鏈
  CascadingStrategy ──→ 多策略級聯
```

---

## 索引

### 核心概念

| 文件 | 說明 |
|------|------|
| [[Command]] | 策略輸出的不可變命令 (p_target, q_target) |
| [[SystemBase]] | 系統基準值，百分比與絕對值轉換 |
| [[StrategyContext]] | 策略執行時上下文，由 Executor 注入 |
| [[ConfigMixin]] | Config 類別共用 Mixin，支援 from_dict |

### 策略基底

| 文件 | 說明 |
|------|------|
| [[Strategy]] | 策略抽象基礎類別 (ABC) |
| [[ExecutionMode]] | 執行模式列舉與 ExecutionConfig |

### 內建策略

| 文件 | 用途 | 執行模式 |
|------|------|---------|
| [[PQModeStrategy]] | 固定 P/Q 輸出 | PERIODIC 1s |
| [[PVSmoothStrategy]] | PV 功率平滑 | PERIODIC 900s |
| [[QVStrategy]] | 電壓-無功功率控制 (Volt-VAR) | PERIODIC 1s |
| [[FPStrategy]] | 頻率-功率控制 (AFC) | PERIODIC 1s |
| [[IslandModeStrategy]] | 離網模式 (Grid Forming) | TRIGGERED |
| [[ScheduleStrategy]] | 排程策略 (依時間執行) | PERIODIC 1s |
| [[StopStrategy]] | 停機 (P=0, Q=0) | PERIODIC 1s |
| [[BypassStrategy]] | 直通模式 (維持 last_command) | TRIGGERED |
| [[LoadSheddingStrategy]] | 階段性負載卸載（離網場景） | PERIODIC 5s |

### 執行引擎

| 文件 | 說明 |
|------|------|
| [[StrategyExecutor]] | 策略生命週期管理與執行迴圈 |

### 系統管理

| 文件 | 說明 |
|------|------|
| [[ModeManager]] | 模式註冊與優先權切換 |
| [[ScheduleModeController]] | 排程模式控制協定，橋接 ScheduleService (L5) 與 SystemController (L6) |
| [[EventDrivenOverride]] | 系統事件驅動的自動 Override 協定與內建實現 |
| [[ProtectionGuard]] | 保護規則鏈 (Chain of Responsibility) |
| [[SOCProtection]] | SOC 高低限保護與警戒區漸進限制 |
| [[ReversePowerProtection]] | 表後逆送保護 |
| [[SystemAlarmProtection]] | 系統告警強制停機保護 |
| [[CascadingStrategy]] | 多策略級聯功率分配 (delta-based clamping) |

### 策略發現

| 文件 | 說明 |
|------|------|
| [[StrategyDiscovery]] | 策略插件自動發現機制（entry_points） |

### 輔助服務

| 文件 | 說明 |
|------|------|
| [[PVDataService]] | PV 功率資料服務 |

---

## Dataview 查詢

```dataview
TABLE source AS "原始碼", tags AS "標籤"
FROM "05-Controller"
WHERE file.name != "_MOC Controller"
SORT file.name ASC
```

---

## 相關 MOC

- 上游：[[_MOC Equipment]] — 設備層提供讀值與事件
- 下游：[[_MOC Integration]] — 整合層串接 Controller 與 Manager
