# =============== Redis - Config ===============
#
# Redis 連線配置
#
# 支援 Standalone / Sentinel 模式。

from __future__ import annotations

from dataclasses import dataclass

from csp_lib.redis.client import TLSConfig


@dataclass(frozen=True, slots=True)
class RedisConfig:
    """
    Redis 連線配置

    支援兩種模式：
    1. Standalone: 單機模式，使用 host/port
    2. Sentinel: 高可用模式，使用 sentinels/sentinel_master

    當同時提供 sentinels 和 sentinel_master 時自動切換為 Sentinel 模式。

    Attributes:
        host: Redis 主機位址（Standalone 模式）
        port: Redis 連接埠（Standalone 模式）
        password: Redis 密碼

        sentinels: Sentinel 節點列表 [(host, port), ...]
        sentinel_master: Sentinel 監控的 master 名稱
        sentinel_password: Sentinel 本身的密碼（若有）

        tls_config: TLS 配置

        socket_timeout: Socket 讀寫超時（秒）
        socket_connect_timeout: Socket 連線超時（秒）
        retry_on_timeout: 超時時是否重試

    Example:
        ```python
        # Standalone 模式
        config = RedisConfig(
            host="localhost",
            port=6379,
            password="secret",
        )

        # Sentinel 模式
        config = RedisConfig(
            sentinels=[("sentinel1", 26379), ("sentinel2", 26379)],
            sentinel_master="mymaster",
            password="redis_password",
            sentinel_password="sentinel_password",
        )
        ```
    """

    # Standalone
    host: str = "localhost"
    port: int = 6379
    password: str | None = None

    # Sentinel 模式
    sentinels: tuple[tuple[str, int], ...] | None = None
    sentinel_master: str | None = None
    sentinel_password: str | None = None

    # TLS
    tls_config: TLSConfig | None = None

    # Timeout
    socket_timeout: float | None = None
    socket_connect_timeout: float | None = None
    retry_on_timeout: bool = False

    def __post_init__(self) -> None:
        """驗證配置一致性"""
        # Sentinel 模式需同時提供 sentinels 和 sentinel_master
        if (self.sentinels is None) != (self.sentinel_master is None):
            raise ValueError("Sentinel 模式需同時提供 sentinels 和 sentinel_master")

    @property
    def is_sentinel_mode(self) -> bool:
        """是否為 Sentinel 模式"""
        return self.sentinels is not None and self.sentinel_master is not None


__all__ = ["RedisConfig"]
