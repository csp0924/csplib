"""Tests for ClusterStatePublisher and ClusterStateSubscriber."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.cluster.config import ClusterConfig, EtcdConfig
from csp_lib.cluster.sync import ClusterSnapshot, ClusterStatePublisher, ClusterStateSubscriber


def _make_config() -> ClusterConfig:
    return ClusterConfig(
        instance_id="node-1",
        etcd=EtcdConfig(),
        namespace="test",
        state_publish_interval=0.1,
        state_ttl=30,
        device_ids=["meter-1", "pcs-1"],
    )


def _make_mock_redis() -> MagicMock:
    """建立 mock RedisClient"""
    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.hset = AsyncMock(return_value=0)
    redis.hgetall = AsyncMock(return_value={})
    redis.expire = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.publish = AsyncMock(return_value=0)
    return redis


class TestClusterSnapshot:
    def test_defaults(self):
        snap = ClusterSnapshot()
        assert snap.leader_id is None
        assert snap.base_modes == ()
        assert snap.override_names == ()
        assert snap.effective_mode is None
        assert snap.triggered_rules == ()
        assert snap.protection_was_modified is False
        assert snap.p_target == 0.0
        assert snap.q_target == 0.0
        assert snap.auto_stop_active is False


class TestClusterStatePublisher:
    @pytest.mark.asyncio
    async def test_publishes_leader_identity(self):
        """啟動時應發佈 leader 身份"""
        config = _make_config()
        redis = _make_mock_redis()
        mm = MagicMock()
        mm.base_mode_names = ["pq"]
        mm.active_override_names = []
        mm.effective_mode = MagicMock(name="pq")
        mm.effective_mode.name = "pq"

        pg = MagicMock()
        pg.last_result = None

        publisher = ClusterStatePublisher(
            config=config,
            redis_client=redis,
            mode_manager=mm,
            protection_guard=pg,
            get_last_command=lambda: (100.0, 50.0),
            get_auto_stop=lambda: False,
        )

        await publisher.start()
        await asyncio.sleep(0.05)

        # 確認 leader key 已設定
        redis.set.assert_called()
        # 找到 leader key 的呼叫
        leader_calls = [c for c in redis.set.call_args_list if "cluster:test:leader" in str(c)]
        assert len(leader_calls) > 0

        await publisher.stop()

    @pytest.mark.asyncio
    async def test_publishes_mode_state(self):
        """應發佈模式狀態到 Redis Hash"""
        config = _make_config()
        redis = _make_mock_redis()
        mm = MagicMock()
        mm.base_mode_names = ["pq", "qv"]
        mm.active_override_names = ["stop"]
        mm.effective_mode = MagicMock()
        mm.effective_mode.name = "stop"

        pg = MagicMock()
        pg.last_result = None

        publisher = ClusterStatePublisher(
            config=config,
            redis_client=redis,
            mode_manager=mm,
            protection_guard=pg,
            get_last_command=lambda: (0.0, 0.0),
            get_auto_stop=lambda: True,
        )

        await publisher.start()
        await asyncio.sleep(0.15)

        # 確認 hset 被呼叫
        assert redis.hset.call_count > 0

        await publisher.stop()

    @pytest.mark.asyncio
    async def test_publishes_protection_state(self):
        """應發佈保護狀態"""
        config = _make_config()
        redis = _make_mock_redis()
        mm = MagicMock()
        mm.base_mode_names = []
        mm.active_override_names = []
        mm.effective_mode = None

        pg = MagicMock()
        result = MagicMock()
        result.triggered_rules = ["soc_protection"]
        result.was_modified = True
        pg.last_result = result

        publisher = ClusterStatePublisher(
            config=config,
            redis_client=redis,
            mode_manager=mm,
            protection_guard=pg,
            get_last_command=lambda: (0.0, 0.0),
            get_auto_stop=lambda: False,
        )

        await publisher.start()
        await asyncio.sleep(0.15)

        # 檢查 hset 呼叫中包含 protection_state key
        hset_calls = [c for c in redis.hset.call_args_list if "protection_state" in str(c)]
        assert len(hset_calls) > 0

        await publisher.stop()

    @pytest.mark.asyncio
    async def test_clears_leader_key_on_stop(self):
        """停止時應清除 leader key"""
        config = _make_config()
        redis = _make_mock_redis()
        mm = MagicMock()
        mm.base_mode_names = []
        mm.active_override_names = []
        mm.effective_mode = None
        pg = MagicMock()
        pg.last_result = None

        publisher = ClusterStatePublisher(
            config=config,
            redis_client=redis,
            mode_manager=mm,
            protection_guard=pg,
            get_last_command=lambda: (0.0, 0.0),
            get_auto_stop=lambda: False,
        )

        await publisher.start()
        await asyncio.sleep(0.05)
        await publisher.stop()

        # 確認 delete 被呼叫
        delete_calls = [c for c in redis.delete.call_args_list if "leader" in str(c)]
        assert len(delete_calls) > 0


class TestClusterStateSubscriber:
    @pytest.mark.asyncio
    async def test_polls_leader_identity(self):
        """應輪詢並解析 leader 身份"""
        config = _make_config()
        redis = _make_mock_redis()

        leader_data = json.dumps({"instance_id": "node-2", "elected_at": 1000.0, "hostname": "host-2"})
        redis.get = AsyncMock(side_effect=lambda key: leader_data if "leader" in key else None)

        subscriber = ClusterStateSubscriber(config=config, redis_client=redis)
        await subscriber.start()
        await asyncio.sleep(0.15)

        snap = subscriber.snapshot
        assert snap.leader_id == "node-2"
        assert snap.elected_at == 1000.0

        await subscriber.stop()

    @pytest.mark.asyncio
    async def test_polls_mode_state(self):
        """應輪詢並解析模式狀態"""
        config = _make_config()
        redis = _make_mock_redis()

        redis.get = AsyncMock(return_value=None)
        redis.hgetall = AsyncMock(
            side_effect=lambda key: (
                {
                    "base_modes": json.dumps(["pq"]),
                    "overrides": json.dumps([]),
                    "effective_mode": "pq",
                }
                if "mode_state" in key
                else {}
            )
        )

        subscriber = ClusterStateSubscriber(config=config, redis_client=redis)
        await subscriber.start()
        await asyncio.sleep(0.15)

        snap = subscriber.snapshot
        assert snap.base_modes == ("pq",)
        assert snap.effective_mode == "pq"

        await subscriber.stop()

    @pytest.mark.asyncio
    async def test_polls_device_states(self):
        """應輪詢設備狀態"""
        config = _make_config()
        redis = _make_mock_redis()

        redis.get = AsyncMock(return_value=None)

        def mock_hgetall(key):
            if key == "device:meter-1:state":
                return {"active_power": 100.0, "voltage": 220.0}
            if key == "device:pcs-1:state":
                return {"soc": 50.0, "p_target": 0.0}
            return {}

        redis.hgetall = AsyncMock(side_effect=mock_hgetall)

        subscriber = ClusterStateSubscriber(config=config, redis_client=redis)
        await subscriber.start()
        await asyncio.sleep(0.15)

        states = subscriber.device_states
        assert "meter-1" in states
        assert states["meter-1"]["active_power"] == 100.0
        assert "pcs-1" in states
        assert states["pcs-1"]["soc"] == 50.0

        await subscriber.stop()

    @pytest.mark.asyncio
    async def test_polls_auto_stop(self):
        """應輪詢 auto_stop 狀態"""
        config = _make_config()
        redis = _make_mock_redis()

        redis.get = AsyncMock(side_effect=lambda key: "1" if "auto_stop" in key else None)
        redis.hgetall = AsyncMock(return_value={})

        subscriber = ClusterStateSubscriber(config=config, redis_client=redis)
        await subscriber.start()
        await asyncio.sleep(0.15)

        assert subscriber.snapshot.auto_stop_active is True

        await subscriber.stop()

    @pytest.mark.asyncio
    async def test_polls_last_command_from_json_str(self):
        """last_command 欄位為 JSON 字串時應正確解析為 float（publisher 用 json.dumps，Redis 讀回為 str）"""
        config = _make_config()
        redis = _make_mock_redis()
        redis.get = AsyncMock(return_value=None)

        def mock_hgetall(key):
            if "last_command" in key:
                # Publisher 端用 json.dumps，Redis hgetall 讀回為 str（decode_responses=True 場景）
                return {
                    "p_target": json.dumps(100.0),
                    "q_target": json.dumps(-50.0),
                    "timestamp": json.dumps(1234.5),
                }
            return {}

        redis.hgetall = AsyncMock(side_effect=mock_hgetall)

        subscriber = ClusterStateSubscriber(config=config, redis_client=redis)
        await subscriber.start()
        await asyncio.sleep(0.15)

        snap = subscriber.snapshot
        assert snap.p_target == 100.0, f"p_target 應解析為 100.0，實際為 {snap.p_target}"
        assert snap.q_target == -50.0, f"q_target 應解析為 -50.0，實際為 {snap.q_target}"
        assert snap.command_timestamp == 1234.5, f"command_timestamp 應解析為 1234.5，實際為 {snap.command_timestamp}"

        await subscriber.stop()

    @pytest.mark.asyncio
    async def test_polls_last_command_rejects_non_finite(self):
        """last_command 欄位為 NaN/Inf 字串時應回退到 default (finite guard)"""
        config = _make_config()
        redis = _make_mock_redis()
        redis.get = AsyncMock(return_value=None)

        def mock_hgetall(key):
            if "last_command" in key:
                return {
                    "p_target": json.dumps(float("nan")),
                    "q_target": json.dumps(float("inf")),
                    "timestamp": "not-a-number",
                }
            return {}

        redis.hgetall = AsyncMock(side_effect=mock_hgetall)

        subscriber = ClusterStateSubscriber(config=config, redis_client=redis)
        await subscriber.start()
        await asyncio.sleep(0.15)

        snap = subscriber.snapshot
        assert snap.p_target == 0.0
        assert snap.q_target == 0.0
        assert snap.command_timestamp == 0.0

        await subscriber.stop()

    @pytest.mark.asyncio
    async def test_empty_redis_returns_defaults(self):
        """Redis 為空時應回傳預設值"""
        config = _make_config()
        redis = _make_mock_redis()

        subscriber = ClusterStateSubscriber(config=config, redis_client=redis)
        await subscriber.start()
        await asyncio.sleep(0.15)

        snap = subscriber.snapshot
        assert snap.leader_id is None
        assert snap.base_modes == ()
        assert snap.auto_stop_active is False

        await subscriber.stop()
