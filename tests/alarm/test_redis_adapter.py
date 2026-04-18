# =============== Redis Alarm Adapter Tests (v0.8.2 B3) ===============
#
# 測試 RedisAlarmPublisher / RedisAlarmSource：
#   - Publisher: aggregator on_change → publish JSON
#   - Source:    訂閱 channel → 注入 aggregator
#   - 缺 redis extra → ImportError
#
# fakeredis 未安裝時標記 skip。

from __future__ import annotations

import asyncio
import importlib
import json
from typing import Any

import pytest

from csp_lib.alarm import AlarmAggregator
from csp_lib.alarm.redis_adapter import RedisAlarmPublisher, RedisAlarmSource

# ---------- fakeredis 檢查（缺失僅對需要 broker 的類別跳過） ----------

try:
    import fakeredis  # type: ignore[import-not-found]

    _HAS_FAKEREDIS = True
except ImportError:
    fakeredis = None  # type: ignore[assignment]
    _HAS_FAKEREDIS = False

requires_fakeredis = pytest.mark.skipif(
    not _HAS_FAKEREDIS,
    reason="fakeredis 未安裝；Redis adapter 整合測試跳過（pip install fakeredis 後啟用）",
)


# ---------- Fixtures ----------


@pytest.fixture
async def fake_redis():
    """提供 fakeredis 的 async 實例，並在結束後關閉連線。"""
    # 兩種 API 名稱兼容：舊的 aioredis.FakeRedis / 新的 FakeAsyncRedis
    client_cls = getattr(fakeredis.aioredis, "FakeRedis", None)
    if client_cls is None:
        client_cls = getattr(fakeredis, "FakeAsyncRedis", None)
    if client_cls is None:
        pytest.skip("fakeredis 沒有可用的 async client")
    client = client_cls()
    try:
        yield client
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


@pytest.fixture
def aggregator() -> AlarmAggregator:
    return AlarmAggregator()


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    """輪詢直到 predicate 為 True 或 timeout。"""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"condition not met within {timeout}s")


# ---------- Publisher ----------


@requires_fakeredis
class TestRedisAlarmPublisher:
    async def test_publisher_publishes_on_aggregator_active(self, fake_redis, aggregator: AlarmAggregator):
        """aggregator on_change True → Redis channel 收到 JSON payload。"""
        channel = "test_alarm_ch"
        pubsub = fake_redis.pubsub()
        await pubsub.subscribe(channel)
        # 消耗訂閱確認訊息
        await asyncio.sleep(0.05)

        publisher = RedisAlarmPublisher(aggregator, fake_redis, channel)
        await publisher.start()

        aggregator.mark_source("dev_a", True)

        # 讀取訊息（skip non-message frames）
        async def _read_message() -> dict[str, Any] | None:
            for _ in range(100):
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
                if msg and msg.get("type") == "message":
                    return msg
                await asyncio.sleep(0.01)
            return None

        msg = await _read_message()
        assert msg is not None, "publisher 未 publish 訊息"
        data = json.loads(msg["data"])
        assert data["active"] is True
        assert "dev_a" in data["sources"]
        assert data["type"] == "aggregated_alarm"
        assert "timestamp" in data

        await publisher.stop()
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()

    async def test_publisher_stop_removes_observer(self, fake_redis, aggregator: AlarmAggregator):
        """stop() 後 aggregator.on_change 不再觸發 publish。"""
        publisher = RedisAlarmPublisher(aggregator, fake_redis, "chan")
        await publisher.start()
        await publisher.stop()

        # 驗證 observer 已被移除：aggregator._observers 為空
        assert aggregator._observers == []  # noqa: SLF001

    async def test_publisher_custom_payload_builder(self, fake_redis, aggregator: AlarmAggregator):
        """自訂 payload_builder 應覆寫預設 schema。"""
        channel = "custom_ch"
        pubsub = fake_redis.pubsub()
        await pubsub.subscribe(channel)
        await asyncio.sleep(0.05)

        def custom(active: bool, agg: AlarmAggregator) -> dict[str, Any]:
            return {"custom": True, "flag": active, "n": len(agg.active_sources)}

        pub = RedisAlarmPublisher(aggregator, fake_redis, channel, payload_builder=custom)
        await pub.start()
        aggregator.mark_source("x", True)

        msg = None
        for _ in range(100):
            m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if m and m.get("type") == "message":
                msg = m
                break
            await asyncio.sleep(0.01)

        assert msg is not None
        data = json.loads(msg["data"])
        assert data == {"custom": True, "flag": True, "n": 1}

        await pub.stop()
        await pubsub.aclose()


# ---------- Source ----------


@requires_fakeredis
class TestRedisAlarmSource:
    async def test_source_injects_active_from_channel(self, fake_redis, aggregator: AlarmAggregator):
        """外部 publish {"active": true} → aggregator mark_source 為 True。"""
        channel = "src_ch"
        source = RedisAlarmSource(aggregator, fake_redis, channel, name="remote")
        await source.start()
        await asyncio.sleep(0.1)  # 等待訂閱就緒

        await fake_redis.publish(channel, json.dumps({"active": True}))
        await _wait_for(lambda: aggregator.active is True, timeout=2.0)
        assert "remote" in aggregator.active_sources

        await fake_redis.publish(channel, json.dumps({"active": False}))
        await _wait_for(lambda: aggregator.active is False, timeout=2.0)

        await source.stop()

    async def test_source_stop_cancels_task_and_unbinds(self, fake_redis, aggregator: AlarmAggregator):
        """stop() 後 task 被取消，且 aggregator 不再含此 source。"""
        channel = "src_stop"
        source = RedisAlarmSource(aggregator, fake_redis, channel, name="r1")
        await source.start()
        await asyncio.sleep(0.05)

        # 先注入一個 active
        await fake_redis.publish(channel, json.dumps({"active": True}))
        await _wait_for(lambda: aggregator.active is True, timeout=2.0)

        await source.stop()
        # stop 會 unbind → source 清為 inactive
        assert aggregator.active is False
        assert "r1" not in aggregator.active_sources

    async def test_source_custom_event_parser(self, fake_redis, aggregator: AlarmAggregator):
        """自訂 event_parser 應覆寫預設解析邏輯。"""
        channel = "src_parse"

        def parser(payload: dict[str, Any]) -> bool:
            return payload.get("state") == "ALARM"

        source = RedisAlarmSource(aggregator, fake_redis, channel, name="r", event_parser=parser)
        await source.start()
        await asyncio.sleep(0.05)

        await fake_redis.publish(channel, json.dumps({"state": "ALARM"}))
        await _wait_for(lambda: aggregator.active is True, timeout=2.0)

        await fake_redis.publish(channel, json.dumps({"state": "OK"}))
        await _wait_for(lambda: aggregator.active is False, timeout=2.0)

        await source.stop()

    async def test_source_empty_name_raises(self, fake_redis, aggregator: AlarmAggregator):
        with pytest.raises(ValueError, match="非空的 name"):
            RedisAlarmSource(aggregator, fake_redis, "c", name="")


# ---------- Missing redis extra ----------


class TestMissingRedisExtra:
    def test_publisher_ctor_raises_without_redis_extra(self, monkeypatch, aggregator: AlarmAggregator):
        """mock _require_redis_extra 失敗 → ctor 拋 ImportError。"""
        import csp_lib.alarm.redis_adapter as mod

        def fake_require() -> None:
            raise ImportError("redis not installed")

        monkeypatch.setattr(mod, "_require_redis_extra", fake_require)
        with pytest.raises(ImportError, match="redis"):
            RedisAlarmPublisher(aggregator, object(), "chan")  # type: ignore[arg-type]

    def test_source_ctor_raises_without_redis_extra(self, monkeypatch, aggregator: AlarmAggregator):
        import csp_lib.alarm.redis_adapter as mod

        def fake_require() -> None:
            raise ImportError("redis not installed")

        monkeypatch.setattr(mod, "_require_redis_extra", fake_require)
        with pytest.raises(ImportError, match="redis"):
            RedisAlarmSource(aggregator, object(), "chan", name="s")  # type: ignore[arg-type]


# 確保 importlib 未被直接使用時不會被 ruff 移除（保留給 CI 偵錯）
_ = importlib
