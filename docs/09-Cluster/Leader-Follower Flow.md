---
tags:
  - type/concept
  - layer/cluster
  - status/complete
created: 2026-02-17
---

# Leader-Follower Flow

> Leader/Follower/Failover 流程與 Redis Key Schema

本頁描述 Cluster 模組中 Leader 與 Follower 角色的資料流程、Failover 機制，以及 Redis Key 的命名規範。

---

## Leader 流程

Leader 負責完整的設備控制管線：

```
LocalDevice.read() --> Redis.publish(state)
ContextBuilder(local) --> StrategyExecutor --> CommandRouter --> Device.write()
```

1. 定期讀取本地 Modbus 設備
2. 透過 `ClusterStatePublisher` 將設備狀態發佈到 Redis
3. 使用本地 `ContextBuilder` 建構 `StrategyContext`
4. `StrategyExecutor` 執行策略產生 `Command`
5. `CommandRouter` 將命令路由到設備寫入

---

## Follower 流程

Follower 不連接實體設備，以 shadow 模式運行：

```
Redis.subscribe(state) --> VirtualContextBuilder
VirtualContextBuilder --> StrategyExecutor --> (no write, shadow mode)
```

1. 透過 `ClusterStateSubscriber` 從 Redis 輪詢 Leader 發佈的狀態
2. `VirtualContextBuilder` 從 Redis 快取資料建構 `StrategyContext`
3. `StrategyExecutor` 以 dry-run 模式執行策略
4. 命令處理器為 no-op（不實際寫入設備）

---

## Failover 流程

當 Leader 實例故障時，自動觸發 failover：

```
Leader down --> etcd lease expires --> new election
New leader: grace period --> start controlling
```

1. Leader 停止回應，etcd lease TTL 到期
2. Follower 偵測到 election key 消失，進入 CANDIDATE 狀態
3. 新一輪 election，某 Follower 當選為新 Leader
4. 新 Leader 等待 `failover_grace_period`（預設 2 秒）
5. Grace period 結束後，啟動設備連線與完整控制管線

---

## Redis Key Schema

所有 key 均帶有 `namespace` 前綴，格式為 `cluster:{namespace}:*`：

### State Keys（Hash / String）

| Key | 型別 | 說明 | TTL |
|-----|------|------|-----|
| `cluster:{namespace}:leader` | String (JSON) | Leader 身份（instance_id, elected_at, hostname） | `state_ttl` |
| `cluster:{namespace}:mode_state` | Hash | 模式狀態（base_modes, overrides, effective_mode） | `state_ttl` |
| `cluster:{namespace}:protection_state` | Hash | 保護狀態（triggered_rules, was_modified） | `state_ttl` |
| `cluster:{namespace}:last_command` | Hash | 最後一次命令（p_target, q_target, timestamp） | `state_ttl` |
| `cluster:{namespace}:auto_stop_active` | String | 自動停機狀態（`"0"` / `"1"`） | `state_ttl` |

### Device State Keys

| Key | 型別 | 說明 |
|-----|------|------|
| `device:{device_id}:state` | Hash | 設備最新狀態（由 `StateSyncManager` 發佈） |

### Pub/Sub Channels

| Channel | 說明 |
|---------|------|
| `channel:cluster:{namespace}:leader_change` | Leader 變更通知 |
| `channel:cluster:{namespace}:state` | 狀態變更串流 |

---

## ClusterSnapshot

`ClusterStateSubscriber` 將 Redis 資料反序列化為 `ClusterSnapshot` dataclass：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `leader_id` | `str \| None` | 目前 leader instance_id |
| `elected_at` | `float \| None` | leader 上任時間 |
| `base_modes` | `list[str]` | 基礎模式名稱列表 |
| `override_names` | `list[str]` | 活躍的 override 名稱列表 |
| `effective_mode` | `str \| None` | 目前生效的模式名稱 |
| `triggered_rules` | `list[str]` | 觸發的保護規則名稱列表 |
| `protection_was_modified` | `bool` | 保護是否修改了命令 |
| `p_target` | `float` | 最後一次命令的 P 目標 |
| `q_target` | `float` | 最後一次命令的 Q 目標 |
| `command_timestamp` | `float \| None` | 最後一次命令的時間戳 |
| `auto_stop_active` | `bool` | 自動停機是否啟動 |

---

## 相關頁面

- [[ClusterController]] -- 中央編排器
- [[LeaderElector]] -- etcd leader election
- [[ClusterConfig]] -- 配置（含 namespace、TTL 參數）
- [[_MOC Storage]] -- Redis 客戶端
- [[_MOC Cluster]] -- 模組總覽
