---
tags: [type/moc, status/complete]
updated: 2026-04-23
version: ">=0.10.0"
---
# _MOC Architecture

> 系統架構與設計模式索引

## 概述

csp_lib 採用嚴格的分層架構，依賴方向由上往下，每層只依賴下一層的公開介面。本區塊涵蓋架構設計、資料流、設計模式與非同步模式等核心概念。

## 頁面索引

### 架構設計
- [[Layered Architecture]] — 八層分層架構詳解
- [[System Diagrams]] — v0.6 系統總覽、流程、狀態機與生命週期圖表（6 張）
- [[Data Flow]] — 核心資料流（讀取循環、控制循環、模式切換）
- [[Manager Layer]] — Layer 5 總覽、Reconciler 對應、LeaderGate 閘門點（v0.10.0）
- [[Design Patterns]] — 設計模式總覽
- [[Reconciliation Pattern]] — Kubernetes reconciler 模式與 CommandRefreshService 實作（v0.8.1）；v0.9.0 Protocol 已實作
- [[Operator Pattern]] — Reconciler Protocol + TypeRegistry + Site Manifest 完整 Operator 架構（v0.9.0）

### 技術模式
- [[Async Patterns]] — 非同步優先模式與生命週期管理
- [[Event System]] — 事件驅動架構與 DeviceEventEmitter
- [[Optional Dependencies]] — 可選依賴與惰性載入

## Dataview 索引

```dataview
TABLE tags AS "標籤"
FROM "01-Architecture"
WHERE !contains(file.name, "_MOC")
SORT file.name ASC
```

## 相關模組

| MOC | 說明 |
|-----|------|
| [[_MOC Core]] | 核心基礎設施（日誌、生命週期、錯誤） |
| [[_MOC Modbus]] | Modbus 通訊協定層 |
| [[_MOC Equipment]] | 設備抽象層 |
| [[_MOC Controller]] | 控制策略層 |
| [[_MOC Integration]] | 整合層 |
| [[_MOC Manager]] | 管理層 |
| [[_MOC Storage]] | 儲存層（MongoDB + Redis） |
| [[_MOC Alarm]] | Alarm 模組（L8，告警聚合與 Redis 橋接，v0.8.2） |
