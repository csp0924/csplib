# =============== Manager - Schedule ===============
#
# 排程管理模組
#
# 提供排程驅動的策略切換功能：
#   - Schema: ScheduleType, StrategyType, ScheduleRule
#   - Config: ScheduleServiceConfig
#   - Repository: ScheduleRepository (Protocol), MongoScheduleRepository (實作)
#   - Factory: StrategyFactory
#   - Service: ScheduleService (AsyncLifecycleMixin)

from .config import ScheduleServiceConfig
from .factory import StrategyFactory
from .repository import MongoScheduleRepository, ScheduleRepository
from .schema import ScheduleRule, ScheduleType, StrategyType
from .service import ScheduleService

__all__ = [
    # Config
    "ScheduleServiceConfig",
    # Factory
    "StrategyFactory",
    # Repository
    "MongoScheduleRepository",
    "ScheduleRepository",
    # Schema
    "ScheduleRule",
    "ScheduleType",
    "StrategyType",
    # Service
    "ScheduleService",
]
