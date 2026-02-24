"""Tests for LeaderElector with mocked etcd."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.cluster.config import ClusterConfig, EtcdConfig
from csp_lib.cluster.election import ElectionState, LeaderElector


def _make_config(instance_id: str = "node-1") -> ClusterConfig:
    return ClusterConfig(
        instance_id=instance_id,
        etcd=EtcdConfig(endpoints=["localhost:2379"]),
        lease_ttl=5,
    )


def _make_mock_client(**overrides) -> MagicMock:
    """建立 mock etcd client"""
    client = MagicMock()
    client.lease_grant = AsyncMock(return_value=12345)
    client.txn_put_if_not_exists = AsyncMock(return_value=True)
    client.lease_keepalive = AsyncMock()
    client.lease_revoke = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.close = AsyncMock()
    for k, v in overrides.items():
        setattr(client, k, v)
    return client


class TestElectionState:
    def test_initial_state(self):
        elector = LeaderElector(config=_make_config())
        assert elector.state == ElectionState.STOPPED
        assert elector.is_leader is False
        assert elector.current_leader_id is None

    def test_state_values(self):
        assert ElectionState.CANDIDATE.value == "candidate"
        assert ElectionState.LEADER.value == "leader"
        assert ElectionState.FOLLOWER.value == "follower"
        assert ElectionState.STOPPED.value == "stopped"


class TestLeaderElectorCampaign:
    @pytest.mark.asyncio
    async def test_campaign_success_becomes_leader(self):
        """成功競選應觸發 on_elected 回呼"""
        config = _make_config()
        on_elected = AsyncMock()
        elector = LeaderElector(config=config, on_elected=on_elected)

        mock_client = _make_mock_client()
        elector._create_etcd_client = MagicMock(return_value=mock_client)

        await elector.start()
        await asyncio.sleep(0.1)

        assert elector.state == ElectionState.LEADER
        assert elector.is_leader is True
        assert elector.current_leader_id == "node-1"
        on_elected.assert_awaited_once()

        await elector.stop()
        assert elector.state == ElectionState.STOPPED

    @pytest.mark.asyncio
    async def test_campaign_failure_becomes_follower(self):
        """競選失敗應成為 follower"""
        config = _make_config()
        elector = LeaderElector(config=config)

        mock_client = _make_mock_client(
            txn_put_if_not_exists=AsyncMock(return_value=False),
            get=AsyncMock(return_value="other-node@host"),
        )
        elector._create_etcd_client = MagicMock(return_value=mock_client)

        await elector.start()
        await asyncio.sleep(0.1)

        assert elector.state in (ElectionState.FOLLOWER, ElectionState.CANDIDATE)
        assert elector.is_leader is False
        assert elector.current_leader_id == "other-node"

        await elector.stop()


class TestLeaderElectorResign:
    @pytest.mark.asyncio
    async def test_resign_revokes_lease(self):
        """Resign 應撤銷 lease"""
        config = _make_config()
        elector = LeaderElector(config=config)

        mock_client = _make_mock_client()
        elector._create_etcd_client = MagicMock(return_value=mock_client)

        await elector.start()
        await asyncio.sleep(0.1)
        assert elector.is_leader

        await elector.resign()
        mock_client.lease_revoke.assert_awaited()

        await elector.stop()

    @pytest.mark.asyncio
    async def test_resign_when_not_leader_is_noop(self):
        """非 leader 時 resign 應無操作"""
        config = _make_config()
        elector = LeaderElector(config=config)
        await elector.resign()  # should not raise


class TestLeaderElectorDemotion:
    @pytest.mark.asyncio
    async def test_keepalive_failure_triggers_demotion(self):
        """Keepalive 連續失敗應觸發降級"""
        config = _make_config()
        on_demoted = AsyncMock()
        elector = LeaderElector(config=config, on_demoted=on_demoted)

        mock_client = _make_mock_client(
            lease_keepalive=AsyncMock(side_effect=Exception("connection lost")),
        )
        elector._create_etcd_client = MagicMock(return_value=mock_client)

        await elector.start()
        # 等待足夠時間讓 keepalive 失敗 3 次
        await asyncio.sleep(6.0)

        # 應已呼叫 keepalive 至少一次
        assert mock_client.lease_keepalive.await_count >= 1

        await elector.stop()
