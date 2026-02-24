---
tags:
  - type/moc
  - layer/cluster
  - status/complete
created: 2026-02-17
---

# Cluster 模組總覽

> **分散式高可用控制 (`csp_lib.cluster`)**

Cluster 模組透過 etcd leader election 實現多實例高可用（HA）控制。當 Leader 實例故障時，系統自動觸發 failover，由新 Leader 接手設備控制，Follower 則以 shadow 模式從 Redis 訂閱狀態，維持即時同步。

需安裝：`pip install csp0924_lib[cluster]`

---

## 架構概覽

```
ClusterController
  ├── LeaderElector ─── etcd lease-based election
  ├── ClusterStatePublisher ─── Leader → Redis (state hash + pub/sub)
  ├── ClusterStateSubscriber ─── Follower ← Redis (polling)
  └── VirtualContextBuilder ─── Redis data → StrategyContext
```

---

## 索引

### 配置

| 頁面 | 說明 |
|------|------|
| [[ClusterConfig]] | 叢集與 etcd 連線配置 |

### 核心元件

| 頁面 | 說明 |
|------|------|
| [[LeaderElector]] | etcd lease-based leader election |
| [[ClusterController]] | 中央編排器（Leader/Follower 自動切換） |

### 概念

| 頁面 | 說明 |
|------|------|
| [[Leader-Follower Flow]] | Leader/Follower/Failover 流程與 Redis Key Schema |

---

## Dataview 查詢

```dataview
TABLE source AS "原始碼", tags AS "標籤"
FROM "09-Cluster"
WHERE file.name != "_MOC Cluster"
SORT file.name ASC
```

---

## 相關 MOC

- 上游：[[_MOC Integration]] -- 整合層提供 SystemController 與 ControlLoop
- 使用：[[_MOC Storage]] -- Redis 狀態同步、etcd leader election
