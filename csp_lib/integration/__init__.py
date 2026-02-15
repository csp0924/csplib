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

from .command_router import CommandRouter
from .context_builder import ContextBuilder
from .data_feed import DeviceDataFeed
from .loop import GridControlLoop, GridControlLoopConfig
from .registry import DeviceRegistry
from .schema import AggregateFunc, CommandMapping, ContextMapping, DataFeedMapping

__all__ = [
    "DeviceRegistry",
    "AggregateFunc",
    "ContextMapping",
    "CommandMapping",
    "DataFeedMapping",
    "ContextBuilder",
    "CommandRouter",
    "DeviceDataFeed",
    "GridControlLoop",
    "GridControlLoopConfig",
]
