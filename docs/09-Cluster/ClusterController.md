---
tags:
  - type/class
  - layer/cluster
  - status/complete
source: csp_lib/cluster/controller.py
created: 2026-02-17
---

# ClusterController

> 叢集中央編排器

`ClusterController` 是 Cluster 模組的主入口，繼承自 `AsyncLifecycleMixin`。它包裝 `SystemController` 與 `UnifiedDeviceManager`，根據 etcd leader election 結果在 Leader/Follower 角色間自動切換。

---

## 核心元件

| 元件 | 說明 |
|------|------|
| [[LeaderElector]] | etcd lease-based leader election |
| `ClusterStatePublisher` | Leader 將設備狀態發佈到 Redis |
| `ClusterStateSubscriber` | Follower 從 Redis 訂閱設備狀態 |
| `VirtualContextBuilder` | 從 Redis 資料建構 `StrategyContext` |

---

## 角色行為

| 角色 | 行為 |
|------|------|
| **Leader** | 完整管線 -- 連接設備、保護評估、命令路由、MongoDB/Redis 寫入 |
| **Follower** | 虛擬 context（從 Redis 讀取）、策略 dry-run、不連接設備 |

---

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `config` | `ClusterConfig` | 叢集配置 |
| `system_controller` | `SystemController` | 系統控制器 |
| `unified_manager` | `UnifiedDeviceManager` | 統一設備管理器 |
| `redis_client` | `RedisClient` | Redis 客戶端 |
| `on_promoted` | `Callable[[], Awaitable[None]] \| None` | 升格為 leader 時的使用者回呼 |
| `on_demoted` | `Callable[[], Awaitable[None]] \| None` | 降級為 follower 時的使用者回呼 |

---

## 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `role` | `str` | 目前角色（`"leader"` / `"follower"` / `"candidate"` / `"stopped"`） |
| `is_leader` | `bool` | 是否為 leader |
| `elector` | `LeaderElector \| None` | Leader election 元件 |

---

## 方法

| 方法 | 說明 |
|------|------|
| `start()` | 啟動叢集控制器（以 follower 模式啟動） |
| `stop()` | 停止叢集控制器 |
| `health()` | 取得叢集健康狀態字典 |

---

## 生命週期流程

1. 建立並啟動 `ClusterStateSubscriber`
2. 建立 `VirtualContextBuilder`
3. 進入 Follower 模式（swap executor context provider）
4. 啟動 `SystemController`
5. 啟動 `LeaderElector`

### Promotion（升格為 Leader）

1. 啟動 `UnifiedDeviceManager`（連接 Modbus、啟動讀取）
2. 等待 `failover_grace_period`（讓設備產生新資料）
3. 切換 executor 到 live 模式
4. 啟動 `ClusterStatePublisher`
5. 同步 follower 快取的模式狀態到 live `ModeManager`

### Demotion（降級為 Follower）

1. 停止 `ClusterStatePublisher`
2. 切換 executor 到 follower 模式
3. 停止 `UnifiedDeviceManager`

---

## 程式碼範例

```python
from csp_lib.cluster import ClusterController

controller = ClusterController(
    config=cluster_config,
    system_controller=sys_ctrl,
    unified_manager=unified_mgr,
    redis_client=redis,
)

async with controller:
    # Automatically handles:
    # - etcd leader election
    # - Leader: local device control + state publishing
    # - Follower: state subscription + shadow execution
    # - Failover with grace period
    await asyncio.Event().wait()
```

---

## 相關頁面

- [[ClusterConfig]] -- 叢集配置
- [[LeaderElector]] -- Leader election
- [[Leader-Follower Flow]] -- 流程與 Redis Key Schema
- [[_MOC Integration]] -- SystemController
- [[_MOC Manager]] -- UnifiedDeviceManager
- [[_MOC Cluster]] -- 模組總覽
