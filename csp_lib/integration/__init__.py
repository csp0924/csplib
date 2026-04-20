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
from .manifest import (
    DeviceSpec,
    ManifestMetadata,
    ReconcilerSpec,
    SiteManifest,
    SiteSpec,
    StrategySpec,
    load_manifest,
)
from .manifest_binder import (
    BoundDeviceSpec,
    BoundReconcilerSpec,
    BoundStrategySpec,
    ManifestBindResult,
    apply_manifest_to_builder,
)
from .orchestrator import (
    CommandStep,
    StepCheck,
    StepResult,
    SystemCommand,
    SystemCommandOrchestrator,
    SystemCommandResult,
)
from .reconciler import Reconciler, ReconcilerStatus
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
from .setpoint_drift_reconciler import DriftTolerance, SetpointDriftReconciler
from .system_controller import (
    CommandRefreshConfig,
    HeartbeatConfig,
    SystemController,
    SystemControllerConfig,
)
from .type_registry import (
    TypeRegistry,
    device_type_registry,
    register_device_type,
    register_strategy_type,
    strategy_type_registry,
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
    # Operator Pattern — Reconciler Protocol
    "Reconciler",
    "ReconcilerStatus",
    # Operator Pattern — TypeRegistry
    "TypeRegistry",
    "device_type_registry",
    "strategy_type_registry",
    "register_device_type",
    "register_strategy_type",
    # Operator Pattern — SiteManifest (apiVersion: csp_lib/v1)
    "SiteManifest",
    "ManifestMetadata",
    "SiteSpec",
    "DeviceSpec",
    "StrategySpec",
    "ReconcilerSpec",
    "load_manifest",
    # Operator Pattern — Manifest binder
    "BoundDeviceSpec",
    "BoundStrategySpec",
    "BoundReconcilerSpec",
    "ManifestBindResult",
    "apply_manifest_to_builder",
    # Operator Pattern — SetpointDriftReconciler
    "DriftTolerance",
    "SetpointDriftReconciler",
]
