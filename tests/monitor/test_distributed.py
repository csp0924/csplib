"""分散式監控單元測試"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from csp_lib.core import HealthStatus
from csp_lib.equipment.alarm.definition import AlarmDefinition, AlarmLevel
from csp_lib.equipment.alarm.state import AlarmEvent, AlarmEventType
from csp_lib.monitor.collector import InterfaceMetrics, SystemMetrics
from csp_lib.monitor.config import (
    DistributedMonitorConfig,
    MetricThresholds,
    MonitorConfig,
    NetworkThresholds,
)
from csp_lib.monitor.distributed import (
    ClusterHealthSnapshot,
    ClusterMonitorAggregator,
    NodeMetricsSummary,
    NodeRegistration,
)
from csp_lib.monitor.publisher import RedisMonitorPublisher


# ================ NetworkThresholds ================


class TestNetworkThresholds:
    def test_defaults(self):
        t = NetworkThresholds()
        assert t.send_rate_bytes == 0.0
        assert t.recv_rate_bytes == 0.0
        assert not t.is_enabled

    def test_enabled_send(self):
        t = NetworkThresholds(send_rate_bytes=1_000_000)
        assert t.is_enabled

    def test_enabled_recv(self):
        t = NetworkThresholds(recv_rate_bytes=500_000)
        assert t.is_enabled

    def test_both_enabled(self):
        t = NetworkThresholds(send_rate_bytes=1_000_000, recv_rate_bytes=500_000)
        assert t.is_enabled

    def test_invalid_negative_send(self):
        with pytest.raises(ValueError):
            NetworkThresholds(send_rate_bytes=-1)

    def test_invalid_negative_recv(self):
        with pytest.raises(ValueError):
            NetworkThresholds(recv_rate_bytes=-1)

    def test_frozen(self):
        t = NetworkThresholds()
        with pytest.raises(AttributeError):
            t.send_rate_bytes = 100  # type: ignore[misc]


# ================ DistributedMonitorConfig ================


class TestDistributedMonitorConfig:
    def test_valid(self):
        c = DistributedMonitorConfig(instance_id="node-1")
        assert c.instance_id == "node-1"
        assert c.namespace == "default"
        assert c.node_ttl == 30
        assert c.aggregation_interval == 10.0
        assert c.publish_cluster_health is True

    def test_empty_instance_id(self):
        with pytest.raises(ValueError):
            DistributedMonitorConfig(instance_id="")

    def test_empty_namespace(self):
        with pytest.raises(ValueError):
            DistributedMonitorConfig(instance_id="node-1", namespace="")

    def test_invalid_node_ttl(self):
        with pytest.raises(ValueError):
            DistributedMonitorConfig(instance_id="node-1", node_ttl=0)

    def test_invalid_aggregation_interval(self):
        with pytest.raises(ValueError):
            DistributedMonitorConfig(instance_id="node-1", aggregation_interval=0)

    def test_node_key(self):
        c = DistributedMonitorConfig(instance_id="node-1", namespace="prod")
        assert c.node_key("node-1") == "monitor:prod:nodes:node-1"

    def test_node_pattern(self):
        c = DistributedMonitorConfig(instance_id="node-1", namespace="prod")
        assert c.node_pattern() == "monitor:prod:nodes:*"

    def test_metrics_prefix(self):
        c = DistributedMonitorConfig(instance_id="node-1", namespace="prod")
        assert c.metrics_prefix("node-1") == "monitor:prod:node-1"

    def test_cluster_health_key(self):
        c = DistributedMonitorConfig(instance_id="node-1", namespace="prod")
        assert c.cluster_health_key() == "monitor:prod:cluster:health"

    def test_frozen(self):
        c = DistributedMonitorConfig(instance_id="node-1")
        with pytest.raises(AttributeError):
            c.instance_id = "other"  # type: ignore[misc]


# ================ InterfaceMetrics ================


class TestInterfaceMetrics:
    def test_defaults(self):
        m = InterfaceMetrics(name="eth0")
        assert m.name == "eth0"
        assert m.bytes_sent == 0
        assert m.bytes_recv == 0
        assert m.send_rate == 0.0
        assert m.recv_rate == 0.0

    def test_to_dict(self):
        m = InterfaceMetrics(
            name="eth0",
            bytes_sent=1000,
            bytes_recv=2000,
            send_rate=100.567,
            recv_rate=200.123,
        )
        d = m.to_dict()
        assert d["name"] == "eth0"
        assert d["bytes_sent"] == 1000
        assert d["bytes_recv"] == 2000
        assert d["send_rate"] == 100.6
        assert d["recv_rate"] == 200.1

    def test_frozen(self):
        m = InterfaceMetrics(name="eth0")
        with pytest.raises(AttributeError):
            m.bytes_sent = 100  # type: ignore[misc]


# ================ SystemMetrics with interfaces ================


class TestSystemMetricsInterfaces:
    def test_default_empty(self):
        m = SystemMetrics()
        assert m.interface_metrics == {}

    def test_to_dict_no_interfaces(self):
        m = SystemMetrics()
        d = m.to_dict()
        assert "interfaces" not in d

    def test_to_dict_with_interfaces(self):
        iface = InterfaceMetrics(name="eth0", bytes_sent=1000, bytes_recv=2000, send_rate=100.0, recv_rate=200.0)
        m = SystemMetrics(interface_metrics={"eth0": iface})
        d = m.to_dict()
        assert "interfaces" in d
        assert "eth0" in d["interfaces"]
        assert d["interfaces"]["eth0"]["send_rate"] == 100.0


# ================ MonitorConfig new fields ================


class TestMonitorConfigNewFields:
    def test_defaults(self):
        c = MonitorConfig()
        assert c.network_interfaces is None
        assert c.network_thresholds == NetworkThresholds()
        assert not c.network_thresholds.is_enabled

    def test_network_interfaces_filter(self):
        c = MonitorConfig(network_interfaces=("eth0", "eth1"))
        assert c.network_interfaces == ("eth0", "eth1")

    def test_network_thresholds(self):
        c = MonitorConfig(network_thresholds=NetworkThresholds(send_rate_bytes=1_000_000))
        assert c.network_thresholds.is_enabled


# ================ Per-NIC Collection ================


class TestPerNICCollection:
    def _mock_psutil(self):
        mock = MagicMock()
        mock.cpu_percent.return_value = 45.0
        mem = MagicMock()
        mem.percent = 60.0
        mem.used = 8 * 1024 * 1024 * 1024
        mem.total = 16 * 1024 * 1024 * 1024
        mock.virtual_memory.return_value = mem
        disk = MagicMock()
        disk.percent = 50.0
        mock.disk_usage.return_value = disk
        net = MagicMock()
        net.bytes_sent = 1000
        net.bytes_recv = 2000
        mock.net_io_counters.return_value = net
        return mock

    def test_pernic_collection(self):
        from csp_lib.monitor.collector import SystemMetricsCollector

        config = MonitorConfig()
        collector = SystemMetricsCollector(config)
        mock_psutil = self._mock_psutil()

        eth0 = MagicMock()
        eth0.bytes_sent = 500
        eth0.bytes_recv = 1000
        eth1 = MagicMock()
        eth1.bytes_sent = 300
        eth1.bytes_recv = 700

        mock_psutil.net_io_counters.side_effect = lambda pernic=False: (
            {"eth0": eth0, "eth1": eth1} if pernic else MagicMock(bytes_sent=1000, bytes_recv=2000)
        )

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            metrics = collector.collect()

        assert "eth0" in metrics.interface_metrics
        assert "eth1" in metrics.interface_metrics
        assert metrics.interface_metrics["eth0"].bytes_sent == 500
        assert metrics.interface_metrics["eth1"].bytes_recv == 700

    def test_pernic_filtered(self):
        from csp_lib.monitor.collector import SystemMetricsCollector

        config = MonitorConfig(network_interfaces=("eth0",))
        collector = SystemMetricsCollector(config)
        mock_psutil = self._mock_psutil()

        eth0 = MagicMock()
        eth0.bytes_sent = 500
        eth0.bytes_recv = 1000
        eth1 = MagicMock()
        eth1.bytes_sent = 300
        eth1.bytes_recv = 700

        mock_psutil.net_io_counters.side_effect = lambda pernic=False: (
            {"eth0": eth0, "eth1": eth1} if pernic else MagicMock(bytes_sent=1000, bytes_recv=2000)
        )

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            metrics = collector.collect()

        assert "eth0" in metrics.interface_metrics
        assert "eth1" not in metrics.interface_metrics

    def test_pernic_rate_calculation(self):
        from csp_lib.monitor.collector import SystemMetricsCollector

        config = MonitorConfig()
        collector = SystemMetricsCollector(config)
        mock_psutil = self._mock_psutil()

        eth0_1 = MagicMock()
        eth0_1.bytes_sent = 500
        eth0_1.bytes_recv = 1000

        eth0_2 = MagicMock()
        eth0_2.bytes_sent = 1500  # +1000
        eth0_2.bytes_recv = 3000  # +2000

        call_count = [0]

        def net_io_side_effect(pernic=False):
            if pernic:
                call_count[0] += 1
                if call_count[0] <= 1:
                    return {"eth0": eth0_1}
                return {"eth0": eth0_2}
            return MagicMock(bytes_sent=1000, bytes_recv=2000)

        mock_psutil.net_io_counters.side_effect = net_io_side_effect

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            m1 = collector.collect()
            assert m1.interface_metrics["eth0"].send_rate == 0.0

            # Simulate time passing
            collector._last_iface_time -= 1.0

            m2 = collector.collect()
            assert m2.interface_metrics["eth0"].send_rate > 0
            assert m2.interface_metrics["eth0"].recv_rate > 0

    def test_network_disabled_no_pernic(self):
        from csp_lib.monitor.collector import SystemMetricsCollector

        config = MonitorConfig(enable_network=False)
        collector = SystemMetricsCollector(config)
        mock_psutil = self._mock_psutil()

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            metrics = collector.collect()

        assert metrics.interface_metrics == {}


# ================ Per-Interface Network Alarms ================


class TestNetworkAlarms:
    def test_no_alarms_when_disabled(self):
        from csp_lib.monitor.alarm import SystemAlarmEvaluator

        config = MonitorConfig()
        evaluator = SystemAlarmEvaluator(config)
        iface = InterfaceMetrics(name="eth0", send_rate=999_999_999)
        metrics = SystemMetrics(interface_metrics={"eth0": iface})
        events = evaluator.evaluate(metrics)
        # No network thresholds enabled, so no network alarms
        assert all("NET" not in e.alarm.code for e in events)

    def test_send_alarm_triggers(self):
        from csp_lib.monitor.alarm import SystemAlarmEvaluator

        config = MonitorConfig(
            network_thresholds=NetworkThresholds(send_rate_bytes=1_000_000),
            hysteresis_activate=1,
            hysteresis_clear=1,
        )
        evaluator = SystemAlarmEvaluator(config)
        iface = InterfaceMetrics(name="eth0", send_rate=2_000_000)
        metrics = SystemMetrics(interface_metrics={"eth0": iface})
        events = evaluator.evaluate(metrics)
        net_events = [e for e in events if "NET_SEND" in e.alarm.code]
        assert len(net_events) == 1
        assert net_events[0].alarm.code == "SYS_NET_SEND_HIGH_eth0"

    def test_recv_alarm_triggers(self):
        from csp_lib.monitor.alarm import SystemAlarmEvaluator

        config = MonitorConfig(
            network_thresholds=NetworkThresholds(recv_rate_bytes=500_000),
            hysteresis_activate=1,
            hysteresis_clear=1,
        )
        evaluator = SystemAlarmEvaluator(config)
        iface = InterfaceMetrics(name="eth0", recv_rate=1_000_000)
        metrics = SystemMetrics(interface_metrics={"eth0": iface})
        events = evaluator.evaluate(metrics)
        net_events = [e for e in events if "NET_RECV" in e.alarm.code]
        assert len(net_events) == 1
        assert net_events[0].alarm.code == "SYS_NET_RECV_HIGH_eth0"

    def test_lazy_evaluator_creation(self):
        from csp_lib.monitor.alarm import SystemAlarmEvaluator

        config = MonitorConfig(
            network_thresholds=NetworkThresholds(send_rate_bytes=1_000_000),
            hysteresis_activate=1,
            hysteresis_clear=1,
        )
        evaluator = SystemAlarmEvaluator(config)
        assert len(evaluator._network_evaluators) == 0

        iface = InterfaceMetrics(name="eth0", send_rate=100)
        metrics = SystemMetrics(interface_metrics={"eth0": iface})
        evaluator.evaluate(metrics)
        assert "eth0" in evaluator._network_evaluators

    def test_multiple_interfaces(self):
        from csp_lib.monitor.alarm import SystemAlarmEvaluator

        config = MonitorConfig(
            network_thresholds=NetworkThresholds(send_rate_bytes=1_000),
            hysteresis_activate=1,
            hysteresis_clear=1,
        )
        evaluator = SystemAlarmEvaluator(config)
        metrics = SystemMetrics(
            interface_metrics={
                "eth0": InterfaceMetrics(name="eth0", send_rate=2_000),
                "eth1": InterfaceMetrics(name="eth1", send_rate=2_000),
            }
        )
        events = evaluator.evaluate(metrics)
        codes = {e.alarm.code for e in events}
        assert "SYS_NET_SEND_HIGH_eth0" in codes
        assert "SYS_NET_SEND_HIGH_eth1" in codes


# ================ Publisher Per-Interface ================


class TestPublisherPerInterface:
    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_network_hash_published(self, mock_redis):
        config = MonitorConfig(redis_key_prefix="test", metrics_ttl=30)
        publisher = RedisMonitorPublisher(mock_redis, config)
        iface = InterfaceMetrics(name="eth0", bytes_sent=1000, bytes_recv=2000)
        metrics = SystemMetrics(interface_metrics={"eth0": iface})
        await publisher.publish_metrics(metrics)

        # Should have called hset twice: once for metrics, once for network
        assert mock_redis.hset.call_count == 2
        network_call = mock_redis.hset.call_args_list[1]
        assert network_call[0][0] == "test:network"

    @pytest.mark.asyncio
    async def test_no_network_hash_when_empty(self, mock_redis):
        config = MonitorConfig(redis_key_prefix="test", metrics_ttl=30)
        publisher = RedisMonitorPublisher(mock_redis, config)
        metrics = SystemMetrics()
        await publisher.publish_metrics(metrics)

        # Should have called hset only once (metrics)
        assert mock_redis.hset.call_count == 1


# ================ Publisher Distributed Mode ================


class TestPublisherDistributed:
    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.get.return_value = None
        return redis

    @pytest.fixture
    def dist_config(self):
        return DistributedMonitorConfig(instance_id="node-1", namespace="test")

    @pytest.mark.asyncio
    async def test_register_node(self, mock_redis, dist_config):
        config = MonitorConfig(redis_key_prefix="test")
        publisher = RedisMonitorPublisher(mock_redis, config, dist_config)
        await publisher.register_node()

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "monitor:test:nodes:node-1"
        data = json.loads(call_args[0][1])
        assert data["instance_id"] == "node-1"

    @pytest.mark.asyncio
    async def test_register_node_noop_without_config(self, mock_redis):
        config = MonitorConfig(redis_key_prefix="test")
        publisher = RedisMonitorPublisher(mock_redis, config)
        await publisher.register_node()
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_dual_publish_metrics(self, mock_redis, dist_config):
        config = MonitorConfig(redis_key_prefix="test", metrics_ttl=30)
        publisher = RedisMonitorPublisher(mock_redis, config, dist_config)
        # For refresh_node_registration
        mock_redis.get.return_value = json.dumps({
            "instance_id": "node-1",
            "hostname": "host",
            "started_at": "2026-01-01T00:00:00",
            "last_seen": "2026-01-01T00:00:00",
        })
        await publisher.publish_metrics(SystemMetrics())

        # hset calls: local metrics + distributed metrics
        assert mock_redis.hset.call_count == 2
        dist_call = mock_redis.hset.call_args_list[1]
        assert dist_call[0][0] == "monitor:test:node-1:metrics"

    @pytest.mark.asyncio
    async def test_dual_publish_alarm(self, mock_redis, dist_config):
        config = MonitorConfig(redis_key_prefix="test")
        publisher = RedisMonitorPublisher(mock_redis, config, dist_config)
        alarm = AlarmDefinition(code="SYS_CPU_HIGH", name="CPU 高", level=AlarmLevel.WARNING)
        event = AlarmEvent(
            event_type=AlarmEventType.TRIGGERED,
            alarm=alarm,
            timestamp=datetime.now(timezone.utc),
        )
        await publisher.publish_alarm_event(event)

        # sadd called twice: local + distributed
        assert mock_redis.sadd.call_count == 2
        dist_call = mock_redis.sadd.call_args_list[1]
        assert dist_call[0][0] == "monitor:test:node-1:alarms"

    @pytest.mark.asyncio
    async def test_refresh_node_registration(self, mock_redis, dist_config):
        config = MonitorConfig(redis_key_prefix="test")
        publisher = RedisMonitorPublisher(mock_redis, config, dist_config)
        mock_redis.get.return_value = json.dumps({
            "instance_id": "node-1",
            "hostname": "host",
            "started_at": "2026-01-01T00:00:00",
            "last_seen": "2026-01-01T00:00:00",
        })
        await publisher.refresh_node_registration()
        mock_redis.set.assert_called_once()
        data = json.loads(mock_redis.set.call_args[0][1])
        assert data["last_seen"] != "2026-01-01T00:00:00"


# ================ NodeRegistration ================


class TestNodeRegistration:
    def test_to_dict(self):
        reg = NodeRegistration(
            instance_id="node-1",
            hostname="host1",
            started_at="2026-01-01T00:00:00",
            last_seen="2026-01-01T00:01:00",
        )
        d = reg.to_dict()
        assert d["instance_id"] == "node-1"
        assert d["hostname"] == "host1"


# ================ NodeMetricsSummary ================


class TestNodeMetricsSummary:
    def test_to_dict(self):
        s = NodeMetricsSummary(
            instance_id="node-1",
            metrics={"cpu_percent": 45.0},
            active_alarms=["SYS_CPU_HIGH"],
            is_online=True,
            updated_at="2026-01-01T00:00:00",
        )
        d = s.to_dict()
        assert d["instance_id"] == "node-1"
        assert d["metrics"]["cpu_percent"] == 45.0
        assert d["active_alarms"] == ["SYS_CPU_HIGH"]


# ================ ClusterHealthSnapshot ================


class TestClusterHealthSnapshot:
    def test_to_dict(self):
        snap = ClusterHealthSnapshot(
            nodes=[
                NodeMetricsSummary(instance_id="node-1", is_online=True),
                NodeMetricsSummary(instance_id="node-2", is_online=False),
            ],
            overall_status=HealthStatus.UNHEALTHY,
            node_count=2,
            online_count=1,
            unhealthy_nodes=["node-2"],
        )
        d = snap.to_dict()
        assert d["overall_status"] == "unhealthy"
        assert d["node_count"] == 2
        assert d["online_count"] == 1
        assert "node-2" in d["unhealthy_nodes"]
        assert "node-1" in d["nodes"]
        assert "node-2" in d["nodes"]


# ================ ClusterMonitorAggregator ================


class TestClusterMonitorAggregator:
    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.keys.return_value = []
        redis.get.return_value = None
        redis.hgetall.return_value = {}
        redis.smembers.return_value = set()
        return redis

    @pytest.fixture
    def dist_config(self):
        return DistributedMonitorConfig(instance_id="aggregator", namespace="test", aggregation_interval=0.1)

    def test_health_not_running(self, mock_redis, dist_config):
        agg = ClusterMonitorAggregator(mock_redis, dist_config)
        report = agg.health()
        assert report.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_lifecycle(self, mock_redis, dist_config):
        agg = ClusterMonitorAggregator(mock_redis, dist_config)
        assert not agg.is_running

        await agg.start()
        assert agg.is_running

        await asyncio.sleep(0.05)
        await agg.stop()
        assert not agg.is_running

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_redis, dist_config):
        async with ClusterMonitorAggregator(mock_redis, dist_config) as agg:
            assert agg.is_running
            await asyncio.sleep(0.05)
        assert not agg.is_running

    @pytest.mark.asyncio
    async def test_discover_nodes(self, mock_redis, dist_config):
        mock_redis.keys.return_value = ["monitor:test:nodes:node-1", "monitor:test:nodes:node-2"]
        mock_redis.get.side_effect = [
            json.dumps({
                "instance_id": "node-1",
                "hostname": "host1",
                "started_at": "2026-01-01T00:00:00",
                "last_seen": "2026-01-01T00:01:00",
            }),
            json.dumps({
                "instance_id": "node-2",
                "hostname": "host2",
                "started_at": "2026-01-01T00:00:00",
                "last_seen": "2026-01-01T00:01:00",
            }),
        ]

        agg = ClusterMonitorAggregator(mock_redis, dist_config)
        nodes = await agg._discover_nodes()
        assert len(nodes) == 2
        assert nodes[0].instance_id == "node-1"
        assert nodes[1].instance_id == "node-2"

    @pytest.mark.asyncio
    async def test_collect_node_summary(self, mock_redis, dist_config):
        mock_redis.hgetall.return_value = {
            "cpu_percent": 45.0,
            "updated_at": "2026-01-01T00:00:00",
        }
        mock_redis.smembers.return_value = {"SYS_CPU_HIGH"}

        agg = ClusterMonitorAggregator(mock_redis, dist_config)
        agg._known_nodes = {"node-1": NodeRegistration("node-1", "host1", "", "")}
        summary = await agg._collect_node_summary("node-1")

        assert summary.instance_id == "node-1"
        assert summary.metrics["cpu_percent"] == 45.0
        assert "SYS_CPU_HIGH" in summary.active_alarms
        assert summary.is_online is True
        assert summary.updated_at == "2026-01-01T00:00:00"

    def test_compute_cluster_health_all_healthy(self, mock_redis, dist_config):
        summaries = [
            NodeMetricsSummary(instance_id="node-1", is_online=True),
            NodeMetricsSummary(instance_id="node-2", is_online=True),
        ]
        snap = ClusterMonitorAggregator._compute_cluster_health(summaries)
        assert snap.overall_status == HealthStatus.HEALTHY
        assert snap.node_count == 2
        assert snap.online_count == 2
        assert snap.unhealthy_nodes == []

    def test_compute_cluster_health_degraded(self, mock_redis, dist_config):
        summaries = [
            NodeMetricsSummary(instance_id="node-1", is_online=True, active_alarms=["SYS_CPU_HIGH"]),
            NodeMetricsSummary(instance_id="node-2", is_online=True),
        ]
        snap = ClusterMonitorAggregator._compute_cluster_health(summaries)
        assert snap.overall_status == HealthStatus.DEGRADED
        assert "node-1" in snap.unhealthy_nodes

    def test_compute_cluster_health_unhealthy(self, mock_redis, dist_config):
        summaries = [
            NodeMetricsSummary(instance_id="node-1", is_online=True),
            NodeMetricsSummary(instance_id="node-2", is_online=False),
        ]
        snap = ClusterMonitorAggregator._compute_cluster_health(summaries)
        assert snap.overall_status == HealthStatus.UNHEALTHY
        assert "node-2" in snap.unhealthy_nodes

    @pytest.mark.asyncio
    async def test_publish_cluster_health(self, mock_redis, dist_config):
        agg = ClusterMonitorAggregator(mock_redis, dist_config)
        snapshot = ClusterHealthSnapshot(
            nodes=[],
            overall_status=HealthStatus.HEALTHY,
            node_count=0,
            online_count=0,
        )
        await agg._publish_cluster_health(snapshot)
        mock_redis.hset.assert_called_once()
        key = mock_redis.hset.call_args[0][0]
        assert key == "monitor:test:cluster:health"

    @pytest.mark.asyncio
    async def test_aggregation_cycle(self, mock_redis, dist_config):
        mock_redis.keys.return_value = ["monitor:test:nodes:node-1"]
        mock_redis.get.return_value = json.dumps({
            "instance_id": "node-1",
            "hostname": "host1",
            "started_at": "2026-01-01T00:00:00",
            "last_seen": "2026-01-01T00:01:00",
        })
        mock_redis.hgetall.return_value = {"cpu_percent": 45.0, "updated_at": "2026-01-01T00:00:00"}
        mock_redis.smembers.return_value = set()

        async with ClusterMonitorAggregator(mock_redis, dist_config) as agg:
            await asyncio.sleep(0.25)
            assert agg.last_snapshot is not None
            assert agg.last_snapshot.node_count == 1
            assert agg.last_snapshot.overall_status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_degraded_with_unhealthy_nodes(self, mock_redis, dist_config):
        agg = ClusterMonitorAggregator(mock_redis, dist_config)
        agg._running = True
        agg._last_snapshot = ClusterHealthSnapshot(
            nodes=[],
            overall_status=HealthStatus.DEGRADED,
            node_count=2,
            online_count=1,
            unhealthy_nodes=["node-2"],
        )
        report = agg.health()
        assert report.status == HealthStatus.DEGRADED
        assert "node-2" in report.details["unhealthy_nodes"]

    @pytest.mark.asyncio
    async def test_health_healthy_when_running(self, mock_redis, dist_config):
        agg = ClusterMonitorAggregator(mock_redis, dist_config)
        agg._running = True
        agg._last_snapshot = ClusterHealthSnapshot(
            nodes=[],
            overall_status=HealthStatus.HEALTHY,
            node_count=1,
            online_count=1,
        )
        report = agg.health()
        assert report.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_known_nodes_property(self, mock_redis, dist_config):
        agg = ClusterMonitorAggregator(mock_redis, dist_config)
        assert agg.known_nodes == {}

        reg = NodeRegistration("node-1", "host1", "", "")
        agg._known_nodes = {"node-1": reg}
        nodes = agg.known_nodes
        assert "node-1" in nodes
        # Should be a copy
        nodes["node-2"] = reg
        assert "node-2" not in agg._known_nodes

    @pytest.mark.asyncio
    async def test_redis_failure_resilience(self, mock_redis, dist_config):
        mock_redis.keys.side_effect = ConnectionError("Redis down")

        async with ClusterMonitorAggregator(mock_redis, dist_config) as agg:
            await asyncio.sleep(0.25)
            assert agg.is_running
            # Should continue running despite errors


# ================ SystemMonitor with distributed_config ================


class TestSystemMonitorDistributed:
    def _mock_psutil(self):
        mock = MagicMock()
        mock.cpu_percent.return_value = 45.0
        mem = MagicMock()
        mem.percent = 60.0
        mem.used = 8 * 1024 * 1024 * 1024
        mem.total = 16 * 1024 * 1024 * 1024
        mock.virtual_memory.return_value = mem
        disk = MagicMock()
        disk.percent = 50.0
        mock.disk_usage.return_value = disk
        net = MagicMock()
        net.bytes_sent = 1000
        net.bytes_recv = 2000
        mock.net_io_counters.return_value = net
        return mock

    @pytest.mark.asyncio
    async def test_register_node_on_start(self):
        from csp_lib.monitor.manager import SystemMonitor

        redis = AsyncMock()
        config = MonitorConfig(interval_seconds=0.1)
        dist_config = DistributedMonitorConfig(instance_id="node-1")

        with patch.dict("sys.modules", {"psutil": self._mock_psutil()}):
            async with SystemMonitor(redis_client=redis, config=config, distributed_config=dist_config) as monitor:
                assert monitor.is_running
                await asyncio.sleep(0.05)

        # register_node calls redis.set
        assert redis.set.called

    @pytest.mark.asyncio
    async def test_works_without_distributed(self):
        from csp_lib.monitor.manager import SystemMonitor

        redis = AsyncMock()
        config = MonitorConfig(interval_seconds=0.1)

        with patch.dict("sys.modules", {"psutil": self._mock_psutil()}):
            async with SystemMonitor(redis_client=redis, config=config) as monitor:
                await asyncio.sleep(0.15)
                assert monitor.is_running
                assert monitor.last_metrics is not None
