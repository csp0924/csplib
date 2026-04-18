# =============== Integration Module ===============
#
# Equipment-Controller 整合層
#
# 橋接設備層 (Equipment) 與控制器層 (Controller)：
#   - DeviceRegistry: Trait-based 設備查詢索引
#   - ContextBuilder: 設備值 → StrategyContext 映射
#   - CommandRouter: Command → 設備寫入路由
#   - DeviceDataFeed: 設備事件 → PVDataService 餵入
#   - GridControlLoop: 完整控制迴圈編排

from .command_refresh import CommandRefreshService
from .command_router import CommandRouter
from .context_builder import ContextBuilder, apply_builtin_aggregate
from .data_feed import DeviceDataFeed
from .distributed import (
    DeviceStateSubscriber,
    DistributedConfig,
    DistributedController,
    RemoteCommandRouter,
    RemoteSiteConfig,
    RemoteSiteRunner,
)
from .distributor import (
    DeviceSnapshot,
    EqualDistributor,
    PowerDistributor,
    ProportionalDistributor,
    SOCBalancingDistributor,
)
from .group_controller import GroupControllerManager, GroupDefinition
from .heartbeat import HeartbeatService
from .heartbeat_generators import (
    ConstantGenerator,
    HeartbeatValueGenerator,
    IncrementGenerator,
    ToggleGenerator,
)
from .heartbeat_targets import DeviceHeartbeatTarget, HeartbeatTarget
from .loop import GridControlLoop, GridControlLoopConfig
from .orchestrator import (
    CommandStep,
    StepCheck,
    StepResult,
    SystemCommand,
    SystemCommandOrchestrator,
    SystemCommandResult,
)
from .registry import DeviceRegistry
from .schema import (
    AggregateFunc,
    AggregationResult,
    CapabilityCommandMapping,
    CapabilityContextMapping,
    CapabilityRequirement,
    CommandMapping,
    ContextMapping,
    DataFeedMapping,
    HeartbeatMapping,
    HeartbeatMode,
)
from .system_controller import (
    CommandRefreshConfig,
    HeartbeatConfig,
    SystemController,
    SystemControllerConfig,
)

__all__ = [
    "DeviceRegistry",
    "AggregateFunc",
    "AggregationResult",
    "ContextMapping",
    "CommandMapping",
    "CapabilityContextMapping",
    "CapabilityCommandMapping",
    "CapabilityRequirement",
    "DataFeedMapping",
    "HeartbeatMapping",
    "HeartbeatMode",
    "HeartbeatService",
    "ContextBuilder",
    "apply_builtin_aggregate",
    "CommandRouter",
    "DeviceDataFeed",
    "GridControlLoop",
    "GridControlLoopConfig",
    "SystemController",
    "SystemControllerConfig",
    "GroupDefinition",
    "GroupControllerManager",
    "SystemCommandOrchestrator",
    "SystemCommand",
    "CommandStep",
    "StepCheck",
    "StepResult",
    "SystemCommandResult",
    # Distributor
    "DeviceSnapshot",
    "PowerDistributor",
    "EqualDistributor",
    "ProportionalDistributor",
    "SOCBalancingDistributor",
    # Distributed
    "DistributedConfig",
    "RemoteSiteConfig",
    "DeviceStateSubscriber",
    "RemoteCommandRouter",
    "DistributedController",
    "RemoteSiteRunner",
    # 命令刷新（reconciler）
    "CommandRefreshConfig",
    "CommandRefreshService",
    # Protocol-driven heartbeat
    "HeartbeatConfig",
    "HeartbeatValueGenerator",
    "ToggleGenerator",
    "IncrementGenerator",
    "ConstantGenerator",
    "HeartbeatTarget",
    "DeviceHeartbeatTarget",
]
