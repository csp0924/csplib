# =============== Cluster Module ===============
#
# 分散式叢集控制模組
#
# 透過 etcd leader election 實現多實例 HA：
#   - ClusterConfig / EtcdConfig: 叢集與 etcd 配置
#   - LeaderElector: etcd lease-based leader election
#   - ClusterStatePublisher / ClusterStateSubscriber: Redis 狀態同步
#   - VirtualContextBuilder: 從 Redis 資料建構 StrategyContext
#   - ClusterController: 中央編排器

from .config import ClusterConfig, EtcdConfig
from .context import DeviceStateProvider, VirtualContextBuilder
from .controller import ClusterController
from .election import ElectionState, LeaderElector
from .sync import ClusterSnapshot, ClusterStatePublisher, ClusterStateSubscriber

__all__ = [
    # Config
    "ClusterConfig",
    "EtcdConfig",
    # Election
    "ElectionState",
    "LeaderElector",
    # Sync
    "ClusterSnapshot",
    "ClusterStatePublisher",
    "ClusterStateSubscriber",
    # Context
    "DeviceStateProvider",
    "VirtualContextBuilder",
    # Controller
    "ClusterController",
]
