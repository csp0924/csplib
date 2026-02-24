# =============== Tests - Redis Config ===============
#
# 測試 RedisConfig 與 RedisClient.from_config()

import pytest

from csp_lib.redis import RedisClient, RedisConfig, TLSConfig


class TestRedisConfig:
    """RedisConfig 單元測試"""

    def test_standalone_mode_default(self) -> None:
        """測試 Standalone 模式預設值"""
        config = RedisConfig()

        assert config.host == "localhost"
        assert config.port == 6379
        assert config.password is None
        assert config.sentinels is None
        assert config.sentinel_master is None
        assert config.is_sentinel_mode is False

    def test_standalone_mode_custom(self) -> None:
        """測試 Standalone 模式自訂值"""
        config = RedisConfig(
            host="redis.example.com",
            port=6380,
            password="secret",
            socket_timeout=1.0,
            socket_connect_timeout=0.5,
        )

        assert config.host == "redis.example.com"
        assert config.port == 6380
        assert config.password == "secret"
        assert config.socket_timeout == 1.0
        assert config.socket_connect_timeout == 0.5
        assert config.is_sentinel_mode is False

    def test_sentinel_mode(self) -> None:
        """測試 Sentinel 模式"""
        config = RedisConfig(
            sentinels=(("sentinel1", 26379), ("sentinel2", 26379)),
            sentinel_master="mymaster",
            password="redis_password",
            sentinel_password="sentinel_password",
        )

        assert config.is_sentinel_mode is True
        assert config.sentinels == (("sentinel1", 26379), ("sentinel2", 26379))
        assert config.sentinel_master == "mymaster"
        assert config.password == "redis_password"
        assert config.sentinel_password == "sentinel_password"

    def test_sentinel_mode_requires_both_params(self) -> None:
        """測試 Sentinel 模式必須同時提供 sentinels 和 sentinel_master"""
        with pytest.raises(ValueError, match="同時提供"):
            RedisConfig(
                sentinels=(("sentinel1", 26379),),
                sentinel_master=None,
            )

        with pytest.raises(ValueError, match="同時提供"):
            RedisConfig(
                sentinels=None,
                sentinel_master="mymaster",
            )

    def test_with_tls_config(self) -> None:
        """測試 TLS 配置"""
        tls = TLSConfig(
            ca_certs="/path/to/ca.crt",
            certfile="/path/to/client.crt",
            keyfile="/path/to/client.key",
        )
        config = RedisConfig(
            host="localhost",
            port=6379,
            tls_config=tls,
        )

        assert config.tls_config is not None
        assert config.tls_config.ca_certs == "/path/to/ca.crt"

    def test_retry_on_timeout(self) -> None:
        """測試 retry_on_timeout 設定"""
        config = RedisConfig(
            host="localhost",
            retry_on_timeout=True,
        )

        assert config.retry_on_timeout is True


class TestRedisClientFromConfig:
    """RedisClient.from_config() 測試"""

    def test_from_config_standalone(self) -> None:
        """測試從 Config 建立 Standalone 客戶端"""
        config = RedisConfig(
            host="localhost",
            port=6379,
            password="secret",
            socket_timeout=1.0,
        )

        client = RedisClient.from_config(config)

        assert client._host == "localhost"
        assert client._port == 6379
        assert client._password == "secret"
        assert client._socket_timeout == 1.0
        assert client.is_sentinel_mode is False
        assert client.is_connected is False

    def test_from_config_sentinel(self) -> None:
        """測試從 Config 建立 Sentinel 客戶端"""
        config = RedisConfig(
            sentinels=(("sentinel1", 26379),),
            sentinel_master="mymaster",
            password="redis_password",
        )

        client = RedisClient.from_config(config)

        assert client.is_sentinel_mode is True
        assert client._config is not None
        assert client._config.sentinel_master == "mymaster"

    def test_direct_init_backward_compatible(self) -> None:
        """測試直接建構保持向後相容"""
        client = RedisClient(
            host="localhost",
            port=6379,
            password="secret",
        )

        assert client._host == "localhost"
        assert client._port == 6379
        assert client._password == "secret"
        assert client.is_sentinel_mode is False
