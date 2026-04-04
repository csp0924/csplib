---
tags:
  - type/moc
  - layer/integration
  - status/complete
updated: 2026-04-04
version: ">=0.4.2"
---

# Integration 模組總覽

橋接 [[_MOC Equipment|Equipment]] 與 [[_MOC Controller|Controller]] 的整合層。

Integration 模組負責將底層設備讀取值轉換為策略上下文、將策略輸出命令路由回設備寫入，並提供完整的控制迴圈編排能力。透過 trait-based 設備索引與宣告式映射 schema，使用者無需手動撰寫資料搬運邏輯。

## 頁面索引

### 查詢與映射

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[DeviceRegistry]] | class | Trait-based 設備查詢索引 |
| [[ContextMapping]] | dataclass | 設備值 → StrategyContext 映射（明確 point_name） |
| [[CommandMapping]] | dataclass | Command → 設備寫入映射（明確 point_name） |
| [[CapabilityContextMapping]] | dataclass | Capability-driven 設備值 → StrategyContext 映射 |
| [[CapabilityCommandMapping]] | dataclass | Capability-driven Command → 設備寫入映射 |
| [[DataFeedMapping]] | dataclass | 設備值 → PVDataService 映射 |
| [[AggregateFunc]] | enum | 多設備值聚合函式 |

### 核心元件

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[ContextBuilder]] | class | 設備值 → StrategyContext 建構器 |
| [[CommandRouter]] | class | Command → 設備寫入路由器 |
| [[DeviceDataFeed]] | class | 設備事件 → PVDataService 資料餵入 |
| [[PowerDistributor]] | class/protocol | 功率分配器（均分、比例、SOC 平衡） |

### 控制迴圈

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[GridControlLoop]] | class | 完整控制迴圈編排器 |
| [[SystemController]] | class | 進階系統控制器（含模式管理與保護機制） |
| [[GroupControllerManager]] | class | 多群組控制器管理（多組獨立 SystemController） |

### 架構文件

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[CapabilityBinding Integration]] | architecture | 能力驅動的設備整合架構與流程圖 |

## 資料流

```
設備讀取值 → ContextBuilder → StrategyContext
  (ContextMapping 或                ↓
   CapabilityContextMapping)  StrategyExecutor
                                    ↓
                               Command
                                    ↓
                          CommandRouter → 設備寫入
                        (CommandMapping 或
                         CapabilityCommandMapping)
```

## 相關模組

- 上游：[[_MOC Equipment]]、[[_MOC Controller]]
- 下游：[[_MOC Manager]]
