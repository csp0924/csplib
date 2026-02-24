# =============== Monitor - Config ===============
#
# 系統監控配置
#
# 提供系統監控的閾值與行為設定：
#   - MetricThresholds: 系統指標閾值
#   - MonitorConfig: 監控器配置

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NetworkThresholds:
    """
    網路介面閾值

    Attributes:
        send_rate_bytes: 發送速率閾值（bytes/s），0 = 停用
        recv_rate_bytes: 接收速率閾值（bytes/s），0 = 停用
    """

    send_rate_bytes: float = 0.0
    recv_rate_bytes: float = 0.0

    def __post_init__(self) -> None:
        if self.send_rate_bytes < 0:
            raise ValueError(f"send_rate_bytes 必須 >= 0，收到: {self.send_rate_bytes}")
        if self.recv_rate_bytes < 0:
            raise ValueError(f"recv_rate_bytes 必須 >= 0，收到: {self.recv_rate_bytes}")

    @property
    def is_enabled(self) -> bool:
        """是否啟用網路介面閾值"""
        return self.send_rate_bytes > 0 or self.recv_rate_bytes > 0


@dataclass(frozen=True)
class DistributedMonitorConfig:
    """
    分散式監控配置

    Attributes:
        instance_id: 唯一節點 ID
        namespace: 命名空間
        node_ttl: 節點註冊 TTL（秒）
        aggregation_interval: 聚合間隔（秒）
        publish_cluster_health: 是否發布叢集健康狀態
    """

    instance_id: str
    namespace: str = "default"
    node_ttl: int = 30
    aggregation_interval: float = 10.0
    publish_cluster_health: bool = True

    def __post_init__(self) -> None:
        if not self.instance_id:
            raise ValueError("instance_id 不可為空")
        if not self.namespace:
            raise ValueError("namespace 不可為空")
        if self.node_ttl <= 0:
            raise ValueError(f"node_ttl 必須 > 0，收到: {self.node_ttl}")
        if self.aggregation_interval <= 0:
            raise ValueError(f"aggregation_interval 必須 > 0，收到: {self.aggregation_interval}")

    def node_key(self, instance_id: str) -> str:
        """取得節點註冊 Key"""
        return f"monitor:{self.namespace}:nodes:{instance_id}"

    def node_pattern(self) -> str:
        """取得節點探索 Pattern"""
        return f"monitor:{self.namespace}:nodes:*"

    def metrics_prefix(self, instance_id: str) -> str:
        """取得節點指標 Key 前綴"""
        return f"monitor:{self.namespace}:{instance_id}"

    def cluster_health_key(self) -> str:
        """取得叢集健康 Key"""
        return f"monitor:{self.namespace}:cluster:health"


@dataclass(frozen=True)
class MetricThresholds:
    """
    系統指標閾值

    Attributes:
        cpu_percent: CPU 使用率閾值（%）
        ram_percent: RAM 使用率閾值（%）
        disk_percent: 磁碟使用率閾值（%）
    """

    cpu_percent: float = 90.0
    ram_percent: float = 85.0
    disk_percent: float = 95.0

    def __post_init__(self) -> None:
        for name in ("cpu_percent", "ram_percent", "disk_percent"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)):
                raise TypeError(f"{name} 必須為數值，收到: {type(value).__name__}")
            if not (0.0 < value <= 100.0):
                raise ValueError(f"{name} 必須在 (0, 100] 範圍內，收到: {value}")


@dataclass(frozen=True)
class MonitorConfig:
    """
    監控器配置

    Attributes:
        interval_seconds: 監控間隔（秒）
        thresholds: 系統指標閾值
        enable_cpu: 啟用 CPU 監控
        enable_ram: 啟用 RAM 監控
        enable_disk: 啟用磁碟監控
        enable_network: 啟用網路監控
        enable_module_health: 啟用模組健康檢查
        redis_key_prefix: Redis key 前綴
        metrics_ttl: 指標 TTL（秒）
        hysteresis_activate: 告警觸發遲滯次數
        hysteresis_clear: 告警解除遲滯次數
        disk_paths: 監控的磁碟路徑
    """

    interval_seconds: float = 5.0
    thresholds: MetricThresholds = field(default_factory=MetricThresholds)
    enable_cpu: bool = True
    enable_ram: bool = True
    enable_disk: bool = True
    enable_network: bool = True
    enable_module_health: bool = True
    redis_key_prefix: str = "system"
    metrics_ttl: int = 30
    hysteresis_activate: int = 3
    hysteresis_clear: int = 3
    disk_paths: tuple[str, ...] = ("/",)
    network_interfaces: tuple[str, ...] | None = None
    network_thresholds: NetworkThresholds = field(default_factory=NetworkThresholds)

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError(f"interval_seconds 必須 > 0，收到: {self.interval_seconds}")
        if self.metrics_ttl <= 0:
            raise ValueError(f"metrics_ttl 必須 > 0，收到: {self.metrics_ttl}")
        if self.hysteresis_activate < 1:
            raise ValueError(f"hysteresis_activate 必須 >= 1，收到: {self.hysteresis_activate}")
        if self.hysteresis_clear < 1:
            raise ValueError(f"hysteresis_clear 必須 >= 1，收到: {self.hysteresis_clear}")
        if not self.disk_paths:
            raise ValueError("disk_paths 不可為空")
        if not self.redis_key_prefix:
            raise ValueError("redis_key_prefix 不可為空")


__all__ = [
    "DistributedMonitorConfig",
    "MetricThresholds",
    "MonitorConfig",
    "NetworkThresholds",
]
