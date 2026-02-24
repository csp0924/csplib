# =============== Manager Schedule - Factory ===============
#
# 策略工廠
#
# 根據 StrategyType + config dict 建立對應的 Strategy 實例：
#   - StrategyFactory: 使用 ConfigMixin.from_dict() 建立策略配置

from __future__ import annotations

from typing import TYPE_CHECKING

from csp_lib.controller.core import Strategy
from csp_lib.controller.strategies import (
    BypassStrategy,
    FPConfig,
    FPStrategy,
    IslandModeConfig,
    IslandModeStrategy,
    PQModeConfig,
    PQModeStrategy,
    PVSmoothConfig,
    PVSmoothStrategy,
    QVConfig,
    QVStrategy,
    StopStrategy,
)
from csp_lib.core import get_logger

from .schema import StrategyType

if TYPE_CHECKING:
    from csp_lib.controller.services import PVDataService
    from csp_lib.controller.strategies import RelayProtocol

logger = get_logger(__name__)


class StrategyFactory:
    """
    策略工廠

    根據 StrategyType 與配置字典建立對應的 Strategy 實例。
    使用 ConfigMixin.from_dict() 處理配置轉換（含 camelCase 支援）。

    Usage:
        factory = StrategyFactory(pv_service=pv_service, relay=relay)
        strategy = factory.create(StrategyType.PQ, {"p": 100, "q": 50})
    """

    def __init__(
        self,
        pv_service: PVDataService | None = None,
        relay: RelayProtocol | None = None,
    ) -> None:
        """
        初始化策略工廠

        Args:
            pv_service: PV 資料服務（PV_SMOOTH 策略需要）
            relay: 繼電器控制（ISLAND 策略需要）
        """
        self._pv_service = pv_service
        self._relay = relay

    def create(self, strategy_type: StrategyType, config_dict: dict | None = None) -> Strategy | None:
        """
        建立策略實例

        Args:
            strategy_type: 策略類型
            config_dict: 策略配置字典（由 ConfigMixin.from_dict 處理）

        Returns:
            Strategy | None: 策略實例，依賴缺失時回傳 None
        """
        config_dict = config_dict or {}

        match strategy_type:
            case StrategyType.PQ:
                pq_config = PQModeConfig.from_dict(config_dict)
                return PQModeStrategy(pq_config)

            case StrategyType.PV_SMOOTH:
                if self._pv_service is None:
                    logger.warning("StrategyFactory: PV_SMOOTH 需要 PVDataService，但未提供")
                    return None
                pv_config = PVSmoothConfig.from_dict(config_dict)
                return PVSmoothStrategy(pv_config, pv_service=self._pv_service)

            case StrategyType.QV:
                qv_config = QVConfig.from_dict(config_dict)
                return QVStrategy(qv_config)

            case StrategyType.FP:
                fp_config = FPConfig.from_dict(config_dict)
                return FPStrategy(fp_config)

            case StrategyType.ISLAND:
                if self._relay is None:
                    logger.warning("StrategyFactory: ISLAND 需要 RelayProtocol，但未提供")
                    return None
                island_config = IslandModeConfig.from_dict(config_dict)
                return IslandModeStrategy(self._relay, island_config)

            case StrategyType.BYPASS:
                return BypassStrategy()

            case StrategyType.STOP:
                return StopStrategy()

        logger.warning(f"StrategyFactory: 未知的策略類型: {strategy_type}")
        return None


__all__ = [
    "StrategyFactory",
]
