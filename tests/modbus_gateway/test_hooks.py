"""Tests for CallbackHook (and protocol compliance check for RedisPublishHook / StatePersistHook)."""

import pytest

from csp_lib.modbus_gateway.hooks import CallbackHook, RedisPublishHook, StatePersistHook
from csp_lib.modbus_gateway.protocol import WriteHook

# ===========================================================================
# Protocol compliance
# ===========================================================================


class TestHookProtocol:
    def test_callback_hook_satisfies_protocol(self):
        async def noop(name, old, new):
            pass

        assert isinstance(CallbackHook(noop), WriteHook)

    def test_redis_publish_hook_satisfies_protocol(self):
        """RedisPublishHook should satisfy WriteHook protocol."""
        from unittest.mock import MagicMock

        hook = RedisPublishHook(redis_client=MagicMock())
        assert isinstance(hook, WriteHook)

    def test_state_persist_hook_satisfies_protocol(self):
        from unittest.mock import MagicMock

        hook = StatePersistHook(redis_client=MagicMock())
        assert isinstance(hook, WriteHook)


# ===========================================================================
# CallbackHook
# ===========================================================================


class TestCallbackHook:
    @pytest.mark.asyncio
    async def test_callback_invoked(self):
        calls = []

        async def recorder(name, old, new):
            calls.append((name, old, new))

        hook = CallbackHook(recorder)
        await hook.on_write("power", 0, 100)
        assert calls == [("power", 0, 100)]

    @pytest.mark.asyncio
    async def test_callback_called_with_correct_args(self):
        received = {}

        async def capture(name, old, new):
            received["name"] = name
            received["old"] = old
            received["new"] = new

        hook = CallbackHook(capture)
        await hook.on_write("voltage", 220, 230)
        assert received == {"name": "voltage", "old": 220, "new": 230}

    @pytest.mark.asyncio
    async def test_callback_multiple_writes(self):
        calls = []

        async def recorder(name, old, new):
            calls.append((name, old, new))

        hook = CallbackHook(recorder)
        await hook.on_write("a", 0, 1)
        await hook.on_write("b", 10, 20)
        assert len(calls) == 2


# ===========================================================================
# RedisPublishHook (mocked redis)
# ===========================================================================


class TestRedisPublishHook:
    @pytest.mark.asyncio
    async def test_publish_called(self):
        from unittest.mock import AsyncMock

        mock_redis = AsyncMock()
        hook = RedisPublishHook(mock_redis, channel="test:writes")
        await hook.on_write("power", 0, 100)
        mock_redis.publish.assert_called_once()
        args = mock_redis.publish.call_args
        assert args[0][0] == "test:writes"

    @pytest.mark.asyncio
    async def test_publish_exception_handled(self):
        from unittest.mock import AsyncMock

        mock_redis = AsyncMock()
        mock_redis.publish.side_effect = ConnectionError("redis down")
        hook = RedisPublishHook(mock_redis)
        # Should not raise
        await hook.on_write("power", 0, 100)


# ===========================================================================
# StatePersistHook (mocked redis)
# ===========================================================================


class TestStatePersistHook:
    def test_redis_key_format(self):
        from unittest.mock import MagicMock

        hook = StatePersistHook(redis_client=MagicMock(), server_name="my_gw")
        assert hook.redis_key == "gateway:my_gw:state"

    @pytest.mark.asyncio
    async def test_on_write_persists(self):
        from unittest.mock import AsyncMock

        mock_redis = AsyncMock()
        hook = StatePersistHook(mock_redis, server_name="test")
        await hook.on_write("power", 0, 100)
        mock_redis.hset.assert_called_once()
