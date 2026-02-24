"""Tests for ClusterController promotion/demotion lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from csp_lib.cluster.config import ClusterConfig, EtcdConfig
from csp_lib.cluster.controller import ClusterController
from csp_lib.cluster.election import ElectionState
from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.integration.schema import ContextMapping


class MockStrategy(Strategy):
    def __init__(self, name: str = "mock"):
        self._name = name

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command()

    def __repr__(self) -> str:
        return f"MockStrategy({self._name})"


def _make_config(instance_id: str = "node-1") -> ClusterConfig:
    return ClusterConfig(
        instance_id=instance_id,
        etcd=EtcdConfig(endpoints=["localhost:2379"]),
        namespace="test",
        lease_ttl=5,
        state_publish_interval=0.1,
        failover_grace_period=0.1,  # 測試用短 grace period
        device_ids=["meter-1"],
    )


def _make_system_controller() -> MagicMock:
    """建立 mock SystemController"""
    sc = MagicMock()
    sc.start = AsyncMock()
    sc.stop = AsyncMock()
    sc.is_running = True

    # Config
    sc.config = MagicMock()
    sc.config.context_mappings = [
        ContextMapping(point_name="active_power", context_field="extra.meter_power", device_id="meter-1"),
    ]
    sc.config.system_base = None

    # Registry
    sc.registry = MagicMock()
    sc.registry.get_devices_by_trait = MagicMock(return_value=[])

    # Executor
    executor = MagicMock()
    executor.last_command = Command()
    executor.set_context_provider = MagicMock()
    executor.set_on_command = MagicMock()
    sc.executor = executor

    # Mode manager
    sc.mode_manager = MagicMock()
    sc.mode_manager.base_mode_names = []
    sc.mode_manager.active_override_names = []
    sc.mode_manager.effective_mode = None
    sc.mode_manager.registered_modes = {}
    sc.mode_manager.add_base_mode = AsyncMock()

    # Protection guard
    sc.protection_guard = MagicMock()
    sc.protection_guard.last_result = None

    # Internal methods (used by ClusterController)
    sc._build_context = MagicMock(return_value=StrategyContext())
    sc._on_command = AsyncMock()
    sc.auto_stop_active = False

    return sc


def _make_unified_manager() -> MagicMock:
    """建立 mock UnifiedDeviceManager"""
    um = MagicMock()
    um.start = AsyncMock()
    um.stop = AsyncMock()
    um.is_running = False
    return um


def _make_redis() -> MagicMock:
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


class TestClusterControllerInit:
    def test_initial_properties(self):
        """初始化時應為 stopped 狀態"""
        config = _make_config()
        sc = _make_system_controller()
        um = _make_unified_manager()
        redis = _make_redis()

        cc = ClusterController(
            config=config,
            system_controller=sc,
            unified_manager=um,
            redis_client=redis,
        )
        assert cc.role == "stopped"
        assert cc.is_leader is False
        assert cc.elector is None


class TestClusterControllerLifecycle:
    @pytest.mark.asyncio
    async def test_starts_as_follower(self):
        """啟動時應以 follower 模式運行"""
        config = _make_config()
        sc = _make_system_controller()
        um = _make_unified_manager()
        redis = _make_redis()

        cc = ClusterController(
            config=config,
            system_controller=sc,
            unified_manager=um,
            redis_client=redis,
        )

        # Mock elector to not actually connect to etcd
        with patch("csp_lib.cluster.controller.LeaderElector") as MockElector:
            mock_elector = MagicMock()
            mock_elector.start = AsyncMock()
            mock_elector.stop = AsyncMock()
            mock_elector.is_leader = False
            mock_elector.state = ElectionState.FOLLOWER
            mock_elector.current_leader_id = None
            MockElector.return_value = mock_elector

            await cc.start()

            # subscriber 應啟動
            # system controller 應啟動
            sc.start.assert_awaited_once()

            # executor 應被切換到 follower 模式
            sc.executor.set_context_provider.assert_called()
            sc.executor.set_on_command.assert_called()

            # unified manager 不應啟動（follower 不連接設備）
            um.start.assert_not_awaited()

            await cc.stop()

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self):
        """停止時應清理所有元件"""
        config = _make_config()
        sc = _make_system_controller()
        um = _make_unified_manager()
        redis = _make_redis()

        cc = ClusterController(
            config=config,
            system_controller=sc,
            unified_manager=um,
            redis_client=redis,
        )

        with patch("csp_lib.cluster.controller.LeaderElector") as MockElector:
            mock_elector = MagicMock()
            mock_elector.start = AsyncMock()
            mock_elector.stop = AsyncMock()
            mock_elector.is_leader = False
            mock_elector.state = ElectionState.FOLLOWER
            MockElector.return_value = mock_elector

            await cc.start()
            await cc.stop()

            mock_elector.stop.assert_awaited_once()
            sc.stop.assert_awaited_once()


class TestClusterControllerPromotion:
    @pytest.mark.asyncio
    async def test_promotion_starts_unified_manager(self):
        """升格為 leader 時應啟動 UnifiedDeviceManager"""
        config = _make_config()
        sc = _make_system_controller()
        um = _make_unified_manager()
        redis = _make_redis()

        cc = ClusterController(
            config=config,
            system_controller=sc,
            unified_manager=um,
            redis_client=redis,
        )

        # 直接呼叫 _handle_elected
        await cc._handle_elected()

        um.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_promotion_switches_to_live_context(self):
        """升格為 leader 時應切換到 live context provider"""
        config = _make_config()
        sc = _make_system_controller()
        um = _make_unified_manager()
        redis = _make_redis()

        cc = ClusterController(
            config=config,
            system_controller=sc,
            unified_manager=um,
            redis_client=redis,
        )

        await cc._handle_elected()

        # executor 應被設定為 live context provider
        sc.executor.set_context_provider.assert_called()
        sc.executor.set_on_command.assert_called()

    @pytest.mark.asyncio
    async def test_promotion_calls_hook(self):
        """升格為 leader 時應呼叫使用者 hook"""
        config = _make_config()
        sc = _make_system_controller()
        um = _make_unified_manager()
        redis = _make_redis()
        on_promoted = AsyncMock()

        cc = ClusterController(
            config=config,
            system_controller=sc,
            unified_manager=um,
            redis_client=redis,
            on_promoted=on_promoted,
        )

        await cc._handle_elected()
        on_promoted.assert_awaited_once()


class TestClusterControllerDemotion:
    @pytest.mark.asyncio
    async def test_demotion_stops_unified_manager(self):
        """降級為 follower 時應停止 UnifiedDeviceManager"""
        config = _make_config()
        sc = _make_system_controller()
        um = _make_unified_manager()
        redis = _make_redis()

        cc = ClusterController(
            config=config,
            system_controller=sc,
            unified_manager=um,
            redis_client=redis,
        )

        # 先模擬有 subscriber（正常啟動後會有）
        cc._subscriber = MagicMock()
        cc._subscriber.device_states = {}
        cc._subscriber.snapshot = MagicMock()
        cc._subscriber.snapshot.base_modes = []

        # 建立 virtual builder
        from csp_lib.cluster.context import VirtualContextBuilder

        cc._virtual_builder = VirtualContextBuilder(
            subscriber=cc._subscriber,
            mappings=sc.config.context_mappings,
        )

        await cc._handle_demoted()

        um.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_demotion_switches_to_virtual_context(self):
        """降級為 follower 時應切換到 virtual context"""
        config = _make_config()
        sc = _make_system_controller()
        um = _make_unified_manager()
        redis = _make_redis()

        cc = ClusterController(
            config=config,
            system_controller=sc,
            unified_manager=um,
            redis_client=redis,
        )

        cc._subscriber = MagicMock()
        cc._subscriber.device_states = {}
        cc._subscriber.snapshot = MagicMock()
        cc._subscriber.snapshot.base_modes = []

        from csp_lib.cluster.context import VirtualContextBuilder

        cc._virtual_builder = VirtualContextBuilder(
            subscriber=cc._subscriber,
            mappings=sc.config.context_mappings,
        )

        await cc._handle_demoted()

        # executor 應被切換
        sc.executor.set_context_provider.assert_called()
        sc.executor.set_on_command.assert_called()

    @pytest.mark.asyncio
    async def test_demotion_calls_hook(self):
        """降級為 follower 時應呼叫使用者 hook"""
        config = _make_config()
        sc = _make_system_controller()
        um = _make_unified_manager()
        redis = _make_redis()
        on_demoted = AsyncMock()

        cc = ClusterController(
            config=config,
            system_controller=sc,
            unified_manager=um,
            redis_client=redis,
            on_demoted=on_demoted,
        )

        cc._subscriber = MagicMock()
        cc._subscriber.device_states = {}
        cc._subscriber.snapshot = MagicMock()
        cc._subscriber.snapshot.base_modes = []

        from csp_lib.cluster.context import VirtualContextBuilder

        cc._virtual_builder = VirtualContextBuilder(
            subscriber=cc._subscriber,
            mappings=sc.config.context_mappings,
        )

        await cc._handle_demoted()
        on_demoted.assert_awaited_once()


class TestClusterControllerHealth:
    def test_health_report(self):
        """health() 應回傳叢集狀態"""
        config = _make_config()
        sc = _make_system_controller()
        um = _make_unified_manager()
        redis = _make_redis()

        cc = ClusterController(
            config=config,
            system_controller=sc,
            unified_manager=um,
            redis_client=redis,
        )

        health = cc.health()
        assert health["role"] == "stopped"
        assert health["instance_id"] == "node-1"
        assert health["is_leader"] is False


class TestClusterControllerModeSyncOnPromotion:
    @pytest.mark.asyncio
    async def test_syncs_mode_from_snapshot(self):
        """升格時應從 snapshot 同步 base mode"""
        config = _make_config()
        sc = _make_system_controller()
        um = _make_unified_manager()
        redis = _make_redis()

        # 註冊 pq 模式
        sc.mode_manager.registered_modes = {"pq": MagicMock()}
        sc.mode_manager.base_mode_names = []

        cc = ClusterController(
            config=config,
            system_controller=sc,
            unified_manager=um,
            redis_client=redis,
        )

        # 設定 subscriber snapshot 有 pq base mode
        cc._subscriber = MagicMock()
        cc._subscriber.snapshot = MagicMock()
        cc._subscriber.snapshot.base_modes = ["pq"]
        cc._subscriber.device_states = {}

        await cc._sync_mode_state_from_snapshot()

        sc.mode_manager.add_base_mode.assert_awaited_with("pq")


class TestNoopCommandHandler:
    @pytest.mark.asyncio
    async def test_noop_handler(self):
        """No-op 命令處理器不應拋出例外"""
        await ClusterController._noop_command_handler(Command(p_target=100.0))
