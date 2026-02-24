---
tags:
  - type/class
  - layer/cluster
  - status/complete
source: csp_lib/cluster/election.py
created: 2026-02-17
---

# LeaderElector

> etcd lease-based leader election

`LeaderElector` 實作基於 etcd lease 的分散式 leader election。繼承自 `AsyncLifecycleMixin`，透過 etcd transaction 進行原子性競選，並以 lease keepalive 維持 leader 身份。

---

## 演算法

1. **Grant lease**：取得一個帶 TTL 的 etcd lease
2. **Transaction**：`IF election_key NOT EXISTS -> PUT(key, instance_id, lease)`
3. **成功 (Leader)**：啟動 keepalive renewal loop + watch key deletion
4. **失敗 (Follower)**：watch election key，等待 leader 離開後重新競選

---

## ElectionState

選舉狀態列舉：

| 值 | 說明 |
|----|------|
| `CANDIDATE` | 正在競選中 |
| `LEADER` | 已當選為 leader |
| `FOLLOWER` | 跟隨目前的 leader |
| `STOPPED` | 已停止 |

---

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `config` | `ClusterConfig` | 叢集配置（含 etcd 連線資訊） |
| `on_elected` | `Callable[[], Awaitable[None]] \| None` | 當選為 leader 時的回呼 |
| `on_demoted` | `Callable[[], Awaitable[None]] \| None` | 從 leader 降級時的回呼 |

---

## 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `is_leader` | `bool` | 是否為 leader |
| `state` | `ElectionState` | 目前選舉狀態 |
| `current_leader_id` | `str \| None` | 目前 leader 的 instance_id |

---

## 方法

| 方法 | 說明 |
|------|------|
| `start()` | 啟動選舉流程，進入 CANDIDATE 狀態 |
| `stop()` | 停止選舉，若為 leader 則自動 resign |
| `resign()` | 主動辭去 leader 角色（撤銷 lease） |

---

## 內部機制

- **Keepalive**：Leader 模式下以 `lease_ttl / 3` 間隔更新 lease，連續失敗 3 次則 self-fencing（自動降級）
- **Watch**：Follower 模式下以 `lease_ttl / 2` 間隔輪詢 election key，key 消失即重新競選
- **Self-fencing**：當 keepalive 連續失敗時，主動降級為 follower 避免腦裂

---

## 相關頁面

- [[ClusterConfig]] -- 叢集配置（含 EtcdConfig）
- [[ClusterController]] -- 使用 LeaderElector 進行角色切換
- [[Leader-Follower Flow]] -- Leader/Follower 流程圖
- [[_MOC Cluster]] -- 模組總覽
