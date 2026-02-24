from unittest.mock import AsyncMock, patch

import pytest

from csp_lib.redis.client import RedisClient, TLSConfig


class TestTLSConfig:
    def test_valid_ca_only(self):
        config = TLSConfig(ca_certs="/path/ca.crt")
        assert config.certfile is None
        assert config.keyfile is None

    def test_certfile_without_keyfile_raises(self):
        with pytest.raises(ValueError, match="certfile 和 keyfile"):
            TLSConfig(ca_certs="/ca.crt", certfile="/cert.crt")

    def test_keyfile_without_certfile_raises(self):
        with pytest.raises(ValueError, match="certfile 和 keyfile"):
            TLSConfig(ca_certs="/ca.crt", keyfile="/key.pem")

    def test_mutual_tls_valid(self):
        config = TLSConfig(ca_certs="/ca.crt", certfile="/cert.crt", keyfile="/key.pem")
        assert config.certfile is not None


class TestRedisClient:
    @pytest.mark.asyncio
    async def test_hset_not_connected_raises(self):
        client = RedisClient()
        with pytest.raises(ConnectionError):
            await client.hset("key", {"field": "value"})

    @pytest.mark.asyncio
    async def test_get_not_connected_raises(self):
        client = RedisClient()
        with pytest.raises(ConnectionError):
            await client.get("key")

    @pytest.mark.asyncio
    async def test_set_not_connected_raises(self):
        client = RedisClient()
        with pytest.raises(ConnectionError):
            await client.set("key", "value")

    @pytest.mark.asyncio
    async def test_delete_not_connected_raises(self):
        client = RedisClient()
        with pytest.raises(ConnectionError):
            await client.delete("key")

    @pytest.mark.asyncio
    async def test_exists_not_connected_raises(self):
        client = RedisClient()
        with pytest.raises(ConnectionError):
            await client.exists("key")

    @pytest.mark.asyncio
    async def test_publish_not_connected_raises(self):
        client = RedisClient()
        with pytest.raises(ConnectionError):
            await client.publish("chan", "msg")

    @pytest.mark.asyncio
    async def test_sadd_not_connected_raises(self):
        client = RedisClient()
        with pytest.raises(ConnectionError):
            await client.sadd("key", "v1")

    @pytest.mark.asyncio
    async def test_hgetall_not_connected_raises(self):
        client = RedisClient()
        with pytest.raises(ConnectionError):
            await client.hgetall("key")

    def test_is_connected_false_initially(self):
        client = RedisClient()
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self):
        client = RedisClient()
        await client.disconnect()  # should not raise

    @pytest.mark.asyncio
    async def test_connect_double_idempotent(self):
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        with patch("csp_lib.redis.client.Redis", return_value=mock_redis):
            await client.connect()
            await client.connect()  # second call should be no-op
            assert mock_redis.ping.await_count == 1

    @pytest.mark.asyncio
    async def test_hset_json_serialization(self):
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock(return_value=1)
        client._client = mock_redis
        result = await client.hset("key", {"num": 42, "str_val": "hello"})
        assert result == 1
        call_kwargs = mock_redis.hset.call_args
        mapping = call_kwargs[1]["mapping"]
        assert mapping["num"] == "42"  # JSON serialized
        assert mapping["str_val"] == "hello"  # string stays as-is

    @pytest.mark.asyncio
    async def test_hgetall_json_parsing(self):
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={"num": "42", "obj": '{"a":1}', "plain": "text"})
        client._client = mock_redis
        result = await client.hgetall("key")
        assert result["num"] == 42  # parsed from JSON
        assert result["obj"] == {"a": 1}
        assert result["plain"] == "text"  # not valid JSON, stays as string

    @pytest.mark.asyncio
    async def test_context_manager(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.aclose = AsyncMock()
        with patch("csp_lib.redis.client.Redis", return_value=mock_redis):
            async with RedisClient() as client:
                assert client.is_connected
            # After exit, disconnect is called
            mock_redis.aclose.assert_awaited_once()

    def test_from_config_standalone(self):
        from csp_lib.redis.config import RedisConfig

        config = RedisConfig(host="myhost", port=6380, password="secret")
        client = RedisClient.from_config(config)
        assert client._host == "myhost"
        assert client._port == 6380
        assert client._password == "secret"

    def test_from_config_sentinel(self):
        from csp_lib.redis.config import RedisConfig

        config = RedisConfig(
            sentinels=(("s1", 26379), ("s2", 26379)),
            sentinel_master="mymaster",
        )
        client = RedisClient.from_config(config)
        assert client.is_sentinel_mode
