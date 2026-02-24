---
tags:
  - type/guide
  - layer/cluster
  - status/complete
created: 2026-02-17
---

# 叢集高可用設定指南

本指南說明如何使用 Cluster 模組設定分散式高可用 (HA) 控制系統，透過 etcd leader election 實現多實例自動故障轉移。

## 安裝

```bash
pip install csp0924_lib[cluster]
```

---

## 架構概覽

```
Leader:
  LocalDevice.read() -> Redis.publish(state)
  ContextBuilder(local) -> StrategyExecutor -> CommandRouter -> Device.write()

Follower:
  Redis.subscribe(state) -> VirtualContextBuilder
  VirtualContextBuilder -> StrategyExecutor -> (no write, shadow mode)

Failover:
  Leader down -> etcd lease expires -> new election
  New leader: grace period -> start controlling
```

---

## 步驟總覽

1. 配置 etcd 連線
2. 建立 [[ClusterConfig]]
3. 建立 [[ClusterController]]
4. 啟動叢集

---

## 1. 配置 etcd

確保 etcd 叢集已就緒（至少 3 節點以確保高可用性）。

---

## 2. 建立 ClusterConfig

使用 [[ClusterConfig]] 與 [[EtcdConfig]] 設定叢集參數：

```python
from csp_lib.cluster import ClusterConfig, EtcdConfig

config = ClusterConfig(
    instance_id="node-01",                    # 此實例的唯一 ID
    etcd=EtcdConfig(
        endpoints=["etcd1:2379", "etcd2:2379", "etcd3:2379"],
        username="root",
        password="secret",
    ),
    namespace="production",                    # 叢集命名空間
    election_key="/csp/cluster/election",      # leader election key
    lease_ttl=10,                              # etcd lease TTL（秒）
    state_publish_interval=1.0,                # 狀態發佈間隔（秒）
    state_ttl=30,                              # Redis 狀態 TTL（秒）
    failover_grace_period=2.0,                 # 故障轉移等待期（秒）
    device_ids=["pcs_001", "bms_001"],         # 管理的設備 ID
)
```

---

## 3. 建立 ClusterController

[[ClusterController]] 是中央編排器，自動處理 Leader/Follower 角色切換。

```python
from csp_lib.cluster import ClusterController

controller = ClusterController(
    config=cluster_config,
    redis_client=redis,
    registry=registry,              # DeviceRegistry
    control_loop_config=loop_config, # GridControlLoopConfig
)
```

---

## 4. 啟動叢集

```python
async with controller:
    # 自動處理:
    # - etcd leader election
    # - Leader: 本地設備控制 + 狀態發佈
    # - Follower: 狀態訂閱 + shadow execution
    # - 故障轉移 (含 grace period)
    await asyncio.Event().wait()
```

---

## 核心元件

| 元件 | 說明 |
|------|------|
| `LeaderElector` | etcd lease-based leader election |
| `ClusterStatePublisher` | Leader 將設備狀態發佈到 Redis |
| `ClusterStateSubscriber` | Follower 從 Redis 訂閱設備狀態 |
| `VirtualContextBuilder` | 從 Redis 資料建構 [[StrategyContext]] |
| [[ClusterController]] | 中央編排器（Leader/Follower 自動切換） |

---

## Redis Key Schema

叢集使用以下 Redis key 結構：

```
cluster:{namespace}:state          # Cluster state hash
cluster:{namespace}:device:{id}    # Device state hash
channel:cluster:{namespace}:state  # State change pub/sub channel
```

---

## Leader/Follower 行為

### Leader

- 執行本地設備讀取
- 透過 `ClusterStatePublisher` 將設備狀態發佈到 Redis
- 正常執行控制迴圈（ContextBuilder -> StrategyExecutor -> CommandRouter）

### Follower

- 透過 `ClusterStateSubscriber` 從 Redis 訂閱設備狀態
- 使用 `VirtualContextBuilder` 建構 StrategyContext
- 執行 shadow mode（僅計算，不寫入設備）

### 故障轉移

1. Leader 失聯 -> etcd lease 過期
2. 觸發新的 leader election
3. 新 Leader 等待 `failover_grace_period`
4. 開始接管設備控制

---

## 相關頁面

- [[Full System Integration]] - 完整系統整合
- [[Control Strategy Setup]] - 控制策略設定
