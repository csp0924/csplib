"""Tests for cluster config."""

import pytest

from csp_lib.cluster.config import ClusterConfig, EtcdConfig


class TestEtcdConfig:
    def test_defaults(self):
        cfg = EtcdConfig()
        assert cfg.endpoints == ["localhost:2379"]
        assert cfg.username is None
        assert cfg.password is None
        assert cfg.ca_cert is None

    def test_custom_endpoints(self):
        cfg = EtcdConfig(endpoints=["etcd1:2379", "etcd2:2379"])
        assert len(cfg.endpoints) == 2

    def test_frozen(self):
        cfg = EtcdConfig()
        with pytest.raises(AttributeError):
            cfg.username = "test"  # type: ignore[misc]


class TestClusterConfig:
    def test_defaults(self):
        cfg = ClusterConfig(instance_id="node-1")
        assert cfg.instance_id == "node-1"
        assert cfg.namespace == "default"
        assert cfg.election_key == "/csp/cluster/election"
        assert cfg.lease_ttl == 10
        assert cfg.state_publish_interval == 1.0
        assert cfg.state_ttl == 30
        assert cfg.failover_grace_period == 2.0
        assert cfg.device_ids == []

    def test_redis_key(self):
        cfg = ClusterConfig(instance_id="node-1", namespace="prod")
        assert cfg.redis_key("leader") == "cluster:prod:leader"
        assert cfg.redis_key("mode_state") == "cluster:prod:mode_state"

    def test_redis_channel(self):
        cfg = ClusterConfig(instance_id="node-1", namespace="prod")
        assert cfg.redis_channel("leader_change") == "channel:cluster:prod:leader_change"
        assert cfg.redis_channel("mode_change") == "channel:cluster:prod:mode_change"

    def test_custom_namespace(self):
        cfg = ClusterConfig(instance_id="node-1", namespace="staging")
        assert cfg.redis_key("leader") == "cluster:staging:leader"

    def test_device_ids(self):
        cfg = ClusterConfig(instance_id="node-1", device_ids=["meter-1", "pcs-1"])
        assert cfg.device_ids == ["meter-1", "pcs-1"]

    def test_frozen(self):
        cfg = ClusterConfig(instance_id="node-1")
        with pytest.raises(AttributeError):
            cfg.instance_id = "other"  # type: ignore[misc]
