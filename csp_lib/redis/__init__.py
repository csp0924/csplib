# =============== Redis Module ===============
#
# Redis 客戶端模組
#
# 提供異步 Redis 操作封裝：
#   - RedisClient: 異步 Redis 客戶端
#   - RedisConfig: 連線配置（支援 Standalone / Sentinel）
#   - TLSConfig: TLS 連線配置

try:
    from .client import RedisClient, TLSConfig
    from .config import RedisConfig
    from .log_level_source import RedisLogLevelSource
except ImportError as _exc:
    raise ImportError(
        'csp_lib.redis requires additional dependencies. Install with: pip install "csp0924_lib[redis]"'
    ) from _exc

__all__ = [
    "RedisClient",
    "RedisConfig",
    "RedisLogLevelSource",
    "TLSConfig",
]
