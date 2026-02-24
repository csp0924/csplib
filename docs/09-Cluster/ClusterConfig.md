---
tags:
  - type/config
  - layer/cluster
  - status/complete
source: csp_lib/cluster/config.py
created: 2026-02-17
---

# ClusterConfig

> 叢集配置

`ClusterConfig` 與 `EtcdConfig` 定義分散式叢集的所有參數，包括 etcd 連線、Redis 命名空間隔離、lease TTL、failover 行為等。兩者皆為 frozen dataclass。

---

## EtcdConfig

etcd 連線配置。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `endpoints` | `list[str]` | `["localhost:2379"]` | etcd gRPC 端點列表 |
| `username` | `str \| None` | `None` | 認證使用者名稱 |
| `password` | `str \| None` | `None` | 認證密碼 |
| `ca_cert` | `str \| None` | `None` | CA 憑證路徑（TLS） |
| `cert_key` | `str \| None` | `None` | 客戶端私鑰路徑（mTLS） |
| `cert_cert` | `str \| None` | `None` | 客戶端憑證路徑（mTLS） |

---

## ClusterConfig

叢集參數配置。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `instance_id` | `str` | (必填) | 唯一實例識別碼 |
| `etcd` | `EtcdConfig` | `EtcdConfig()` | etcd 連線配置 |
| `namespace` | `str` | `"default"` | Redis key 命名空間隔離 |
| `election_key` | `str` | `"/csp/cluster/election"` | etcd 選舉 key 前綴 |
| `lease_ttl` | `int` | `10` | etcd lease TTL（秒） |
| `state_publish_interval` | `float` | `1.0` | Leader 發佈狀態的間隔（秒） |
| `state_ttl` | `int` | `30` | Redis 叢集狀態 key 的 TTL（秒） |
| `failover_grace_period` | `float` | `2.0` | 升格為 Leader 後的等待時間（秒） |
| `device_ids` | `list[str]` | `[]` | 需同步的設備 ID 列表 |

### 方法

| 方法 | 說明 |
|------|------|
| `redis_key(suffix)` | 產生帶命名空間的 Redis key：`cluster:{namespace}:{suffix}` |
| `redis_channel(suffix)` | 產生帶命名空間的 Pub/Sub channel：`channel:cluster:{namespace}:{suffix}` |

---

## 程式碼範例

```python
from csp_lib.cluster import ClusterConfig, EtcdConfig

config = ClusterConfig(
    instance_id="node-01",
    etcd=EtcdConfig(
        endpoints=["etcd1:2379", "etcd2:2379"],
        username="root",
        password="secret",
    ),
    namespace="production",
    election_key="/csp/cluster/election",
    lease_ttl=10,
    state_publish_interval=1.0,
    state_ttl=30,
    failover_grace_period=2.0,
    device_ids=["pcs_001", "bms_001"],
)
```

---

## 相關頁面

- [[ClusterController]] -- 中央編排器
- [[LeaderElector]] -- Leader election
- [[Leader-Follower Flow]] -- Redis Key Schema
- [[_MOC Cluster]] -- 模組總覽
