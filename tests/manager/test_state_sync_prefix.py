# =============== Manager State - Prefix 配置測試 ===============
#
# 驗證 StateSyncConfig.key_prefix / channel_prefix：
# - 預設值不破壞既有行為
# - 自訂 prefix 正確反映到 key/channel 命名
# - 空字串 raise ValueError（對齊 bug-validation-fail-loud）

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.equipment.device.events import EVENT_READ_COMPLETE, ReadCompletePayload
from csp_lib.manager.state import StateSyncConfig, StateSyncManager


class _FakePipeline:
    def __init__(self) -> None:
        self.commands: list[tuple[str, tuple, dict]] = []
        self.hset = MagicMock(side_effect=lambda *a, **kw: self.commands.append(("hset", a, kw)) or self)
        self.expire = MagicMock(side_effect=lambda *a, **kw: self.commands.append(("expire", a, kw)) or self)
        self.set = MagicMock(side_effect=lambda *a, **kw: self.commands.append(("set", a, kw)) or self)
        self.publish = MagicMock(side_effect=lambda *a, **kw: self.commands.append(("publish", a, kw)) or self)

    async def execute(self) -> list[int]:
        return [1] * len(self.commands)


def _make_redis() -> MagicMock:
    redis = MagicMock()
    redis.hset = AsyncMock()
    redis.set = AsyncMock()
    redis.sadd = AsyncMock()
    redis.srem = AsyncMock()
    redis.publish = AsyncMock()
    redis.expire = AsyncMock()
    redis._last_pipeline = None

    def _pipeline(*_args, **_kwargs):
        pipe = _FakePipeline()
        redis._last_pipeline = pipe
        return pipe

    redis.pipeline = MagicMock(side_effect=_pipeline)
    return redis


class _FakeAsyncDevice:
    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self._handlers: dict[str, list] = {}

    def on(self, event, handler):  # type: ignore[no-untyped-def]
        self._handlers.setdefault(event, []).append(handler)
        return lambda: self._handlers[event].remove(handler)

    async def emit(self, event, payload) -> None:  # type: ignore[no-untyped-def]
        for h in list(self._handlers.get(event, [])):
            await h(payload)


class TestStateSyncConfigPrefix:
    """StateSyncConfig 新增 key_prefix / channel_prefix 欄位與 validation。"""

    def test_default_prefixes(self):
        """預設 prefix 保持與舊版行為一致。"""
        config = StateSyncConfig()
        assert config.key_prefix == "device"
        assert config.channel_prefix == "channel:device"

    def test_custom_prefixes_honored(self):
        config = StateSyncConfig(key_prefix="tw_s1.device", channel_prefix="tw_s1.channel:device")
        assert config.key_prefix == "tw_s1.device"
        assert config.channel_prefix == "tw_s1.channel:device"

    def test_empty_key_prefix_raises(self):
        with pytest.raises(ValueError, match="key_prefix"):
            StateSyncConfig(key_prefix="")

    def test_empty_channel_prefix_raises(self):
        with pytest.raises(ValueError, match="channel_prefix"):
            StateSyncConfig(channel_prefix="")


class TestCustomPrefixAffectsKeysAndChannels:
    """多站部署：prefix 影響 Redis key 與 channel，避免衝突。"""

    async def test_custom_key_prefix_used_in_pipeline_hset(self):
        redis = _make_redis()
        config = StateSyncConfig(key_prefix="site_tw.device")
        manager = StateSyncManager(redis, config=config)

        device = _FakeAsyncDevice("inv1")
        manager.subscribe(device)

        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(device_id="inv1", values={"p": 100}, duration_ms=1.0),
        )

        assert redis._last_pipeline is not None
        hset_cmds = [c for c in redis._last_pipeline.commands if c[0] == "hset"]
        assert hset_cmds[0][1][0] == "site_tw.device:inv1:state"

    async def test_custom_channel_prefix_used_in_pipeline_publish(self):
        redis = _make_redis()
        config = StateSyncConfig(channel_prefix="site_tw.ch")
        manager = StateSyncManager(redis, config=config)

        device = _FakeAsyncDevice("inv1")
        manager.subscribe(device)

        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(device_id="inv1", values={"p": 100}, duration_ms=1.0),
        )

        assert redis._last_pipeline is not None
        publish_cmds = [c for c in redis._last_pipeline.commands if c[0] == "publish"]
        channel = publish_cmds[0][1][0]
        assert channel == "site_tw.ch:inv1:data"

    async def test_default_prefixes_baseline(self):
        """未自訂 prefix 時，key/channel 與既有格式一致（無 regression）。"""
        redis = _make_redis()
        manager = StateSyncManager(redis)  # default config

        device = _FakeAsyncDevice("inv1")
        manager.subscribe(device)

        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(device_id="inv1", values={"p": 100}, duration_ms=1.0),
        )

        assert redis._last_pipeline is not None
        hset_cmds = [c for c in redis._last_pipeline.commands if c[0] == "hset"]
        publish_cmds = [c for c in redis._last_pipeline.commands if c[0] == "publish"]
        assert hset_cmds[0][1][0] == "device:inv1:state"
        assert publish_cmds[0][1][0] == "channel:device:inv1:data"


class TestPipelineBatching:
    """Pipeline 批次：read_complete 把 4 個命令壓成一次 round trip。"""

    async def test_read_complete_uses_single_pipeline(self):
        redis = _make_redis()
        manager = StateSyncManager(redis)

        device = _FakeAsyncDevice("inv1")
        manager.subscribe(device)

        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(device_id="inv1", values={"p": 100, "q": 20}, duration_ms=1.0),
        )

        # 只呼叫一次 pipeline()，內含 hset/expire/set/publish 4 命令
        redis.pipeline.assert_called_once()
        assert redis._last_pipeline is not None
        cmd_names = [c[0] for c in redis._last_pipeline.commands]
        assert cmd_names == ["hset", "expire", "set", "publish"]

    async def test_pipeline_hset_mapping_is_json_encoded(self):
        """pipeline 直接用 redis-py API，需自行 JSON encode 非字串值。"""
        redis = _make_redis()
        manager = StateSyncManager(redis)

        device = _FakeAsyncDevice("inv1")
        manager.subscribe(device)

        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(
                device_id="inv1",
                values={"int_v": 42, "float_v": 3.14, "str_v": "already_str"},
                duration_ms=1.0,
            ),
        )

        assert redis._last_pipeline is not None
        hset_cmds = [c for c in redis._last_pipeline.commands if c[0] == "hset"]
        mapping = hset_cmds[0][2]["mapping"]
        assert json.loads(mapping["int_v"]) == 42
        assert json.loads(mapping["float_v"]) == 3.14
        # 字串值不重複 encode（保留 raw）
        assert mapping["str_v"] == "already_str"
