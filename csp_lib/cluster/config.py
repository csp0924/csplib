# =============== Cluster - Config ===============
#
# 分散式叢集配置
#
# 定義 etcd 與叢集相關設定：
#   - EtcdConfig: etcd 連線配置
#   - ClusterConfig: 叢集參數（election key、TTL、Redis key schema）

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EtcdConfig:
    """
    etcd 連線配置

    Attributes:
        endpoints: etcd gRPC 端點列表
        username: 認證使用者名稱（可選）
        password: 認證密碼（可選）
        ca_cert: CA 憑證路徑（TLS，可選）
        cert_key: 客戶端私鑰路徑（mTLS，可選）
        cert_cert: 客戶端憑證路徑（mTLS，可選）
    """

    endpoints: list[str] = field(default_factory=lambda: ["localhost:2379"])
    username: str | None = None
    password: str | None = None
    ca_cert: str | None = None
    cert_key: str | None = None
    cert_cert: str | None = None


@dataclass(frozen=True)
class ClusterConfig:
    """
    叢集配置

    Attributes:
        instance_id: 唯一實例識別碼
        etcd: etcd 連線配置
        namespace: Redis key 命名空間隔離（預設 "default"）
        election_key: etcd 選舉 key 前綴
        lease_ttl: etcd lease TTL（秒）
        state_publish_interval: leader 發佈狀態的間隔（秒）
        state_ttl: Redis 叢集狀態 key 的 TTL（秒）
        failover_grace_period: 升格為 leader 後的等待時間（秒）
        device_ids: 需同步的設備 ID 列表
    """

    instance_id: str
    etcd: EtcdConfig = field(default_factory=EtcdConfig)
    namespace: str = "default"
    election_key: str = "/csp/cluster/election"
    lease_ttl: int = 10
    state_publish_interval: float = 1.0
    state_ttl: int = 30
    failover_grace_period: float = 2.0
    device_ids: list[str] = field(default_factory=list)
    max_keepalive_failures: int = 3
    campaign_retry_delay: float = 2.0

    def __post_init__(self) -> None:
        if self.max_keepalive_failures <= 0:
            raise ValueError(f"max_keepalive_failures 必須大於 0，收到: {self.max_keepalive_failures}")
        if self.campaign_retry_delay <= 0:
            raise ValueError(f"campaign_retry_delay 必須大於 0，收到: {self.campaign_retry_delay}")

    def redis_key(self, suffix: str) -> str:
        """產生帶命名空間的 Redis key"""
        return f"cluster:{self.namespace}:{suffix}"

    def redis_channel(self, suffix: str) -> str:
        """產生帶命名空間的 Redis Pub/Sub channel"""
        return f"channel:cluster:{self.namespace}:{suffix}"


__all__ = [
    "ClusterConfig",
    "EtcdConfig",
]
