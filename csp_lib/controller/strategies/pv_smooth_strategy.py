# =============== PV Smooth Strategy ===============
#
# PV 平滑策略：根據 PV 歷史功率計算目標輸出，限制功率變化速率

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from csp_lib.controller.core import Command, ConfigMixin, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.services import PVDataService
from csp_lib.core import get_logger

logger = get_logger(__name__)


@dataclass
class PVSmoothConfig(ConfigMixin):
    """
    PV 平滑配置

    Attributes:
        capacity: PV 系統容量 (kW)
        ramp_rate: 功率變化率限制 (百分比/週期)
        pv_loss: PV 系統損失 (kW)，計算時扣除此值
        min_history: 最少需要的歷史資料筆數
    """

    capacity: float = 1000.0
    ramp_rate: float = 10.0  # 10% per interval
    pv_loss: float = 0.0  # 系統損失
    min_history: int = 1  # 最少歷史筆數


class PVSmoothStrategy(Strategy):
    """
    PV 平滑策略

    根據 PV 歷史功率的平均值計算目標輸出，並限制功率變化速率。

    執行模式：PERIODIC (900秒週期)

    Usage:
        pv_service = PVDataService(max_history=300)
        config = PVSmoothConfig(capacity=1000, ramp_rate=10)
        strategy = PVSmoothStrategy(config, pv_service)

        # 外部 loop 定期更新 pv_service
        pv_service.append(current_pv_power)
    """

    DEFAULT_INTERVAL = 900

    def __init__(
        self,
        config: Optional[PVSmoothConfig] = None,
        pv_service: Optional[PVDataService] = None,
        interval_seconds: int = DEFAULT_INTERVAL,
    ):
        """
        初始化 PV 平滑策略

        Args:
            config: PV 平滑配置
            pv_service: PV 資料服務 (注入)
            interval_seconds: 執行週期 (秒)
        """
        self._config = config or PVSmoothConfig()
        self._pv_service = pv_service
        self._interval = interval_seconds

    @property
    def config(self) -> PVSmoothConfig:
        """當前配置"""
        return self._config

    @property
    def pv_service(self) -> Optional[PVDataService]:
        """PV 資料服務"""
        return self._pv_service

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=self._interval)

    def execute(self, context: StrategyContext) -> Command:
        """
        執行 PV 平滑策略，計算目標功率輸出

        策略流程：
        1. 前置條件檢查 (PV Service 存在性、歷史資料充足性)
        2. 計算歷史平均功率
        3. 扣除系統損耗
        4. 套用斜率限制 (Ramp Rate Limiting) 防止功率劇烈變化

        Args:
            context: 策略上下文，包含上次指令等狀態資訊

        Returns:
            Command: 包含目標有功功率 (p_target) 和無功功率 (q_target) 的指令
        """
        # ============================================================
        # 步驟 1: 前置條件檢查 - PV 資料服務存在性
        # ============================================================
        # 確保 PV 資料服務已注入，否則無法取得歷史功率資料
        if self._pv_service is None:
            logger.warning("PVSmoothStrategy: 未設定 PVDataService，回傳 0")
            return Command(p_target=0.0, q_target=0.0)

        # ============================================================
        # 步驟 2: 前置條件檢查 - 歷史資料充足性
        # ============================================================
        # 歷史資料不足時無法計算可靠的平均值，返回安全值 0
        if self._pv_service.count < self._config.min_history:
            logger.debug(f"PVSmoothStrategy: 歷史資料不足 ({self._pv_service.count}/{self._config.min_history})")
            return Command(p_target=0.0, q_target=0.0)

        # ============================================================
        # 步驟 3: 計算歷史平均功率
        # ============================================================
        # 取得 PV 歷史功率的平均值作為平滑後的基準
        average_power = self._pv_service.get_average()
        if average_power is None:
            logger.debug("PVSmoothStrategy: 無有效資料，回傳 0")
            return Command(p_target=0.0, q_target=0.0)

        # ============================================================
        # 步驟 4: 扣除系統損耗
        # ============================================================
        # 扣除 PV 系統的固定損耗 (如Inverter損耗、線路損耗)
        # 使用 max(_, 0.0) 確保調整後功率不為負值
        adjusted_power = max(average_power - self._config.pv_loss, 0.0)

        # ============================================================
        # 步驟 5: 計算斜率限制 (Ramp Rate Limiting)
        # ============================================================
        # 斜率限制 = 系統容量 × 變化率百分比
        # 例如: 1000kW × 10% = 100kW/週期
        rate_limit = self._config.capacity * self._config.ramp_rate / 100.0

        # 取得上次指令的有功功率作為變化基準
        last_command_p = context.last_command.p_target

        # ============================================================
        # 步驟 6: 套用斜率限制，計算最終目標功率
        # ============================================================
        # 設定功率變化的上下限邊界
        max_p = last_command_p + rate_limit  # 最大允許增加到的功率
        min_p = last_command_p - rate_limit  # 最小允許降低到的功率

        # 將調整後功率夾限 (clamp) 在允許範圍內
        target_p = max(min(adjusted_power, max_p), min_p)

        logger.debug(
            f"PVSmoothStrategy: avg={average_power:.1f}, adjusted={adjusted_power:.1f}, "
            f"target={target_p:.1f} (ramp limit: ±{rate_limit:.1f})"
        )

        # 返回計算結果，Q 目標固定為 0 (本策略不控制無功功率)
        return Command(p_target=target_p, q_target=0.0)

    def update_config(self, config: PVSmoothConfig) -> None:
        """更新配置"""
        self._config = config

    def set_pv_service(self, pv_service: PVDataService) -> None:
        """設定 PV 資料服務"""
        self._pv_service = pv_service

    def __str__(self) -> str:
        return f"PVSmoothStrategy(capacity={self._config.capacity}, ramp_rate={self._config.ramp_rate}%)"
