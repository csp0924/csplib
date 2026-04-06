---
tags:
  - type/moc
  - status/complete
created: 2026-02-17
updated: 2026-04-06
version: ">=0.7.1"
---

# Guides

使用教學與入門指南。涵蓋從基本設備讀寫到完整系統整合的各項教學。

## 頁面索引

| 指南 | 說明 |
|------|------|
| [[Quick Start]] | 快速入門：基本設備讀寫、控制策略、完整系統整合 |
| [[Device Setup]] | 設備設定：定義點位、建立客戶端、事件註冊、生命週期管理 |
| [[Control Strategy Setup]] | 控制策略設定：選擇策略、配置參數、建立執行器 |
| [[Full System Integration]] | 完整系統整合：DeviceRegistry、映射 Schema、控制迴圈 |
| [[Custom Strategy]] | 自訂策略：繼承 Strategy ABC、實作 execute() |
| [[Cluster HA Setup]] | 叢集高可用設定：etcd leader election、ClusterController |
| [[No MongoDB Setup]] | 不使用 MongoDB：NullBatchUploader、InMemoryBatchUploader、自訂後端 |
| [[Custom Repository]] | 實作自訂 Repository：AlarmRepository、CommandRepository、SQLite 範例 |
| [[ModbusGateway Setup]] | ModbusGateway 設定：暴露系統狀態給 EMS/SCADA，WriteHook、DataSyncSource |
| [[Capability-driven Deployment]] | Capability 系統：設備能力宣告、CapabilityBinding、preflight_check 驗證 |
| [[Custom Database Backend]] | 自訂資料庫後端：BatchUploader Protocol、InfluxDB / PostgreSQL 實作範例 |

## 相關資源

- [[_MOC Reference]] - 參考索引
- [[_MOC Development]] - 開發相關資訊
