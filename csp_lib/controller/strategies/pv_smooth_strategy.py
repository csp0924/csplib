# =============== PV Smooth Strategy ===============
#
# PV 平滑策略：根據 PV 歷史功率計算目標輸出，限制功率變化速率
#
# v0.8.2: 支援透過 RuntimeParameters + param_keys 動態覆蓋
# capacity / ramp_rate / pv_loss / min_history；可透過 enabled_key
# 讓 EMS 即時停用（輸出 Command(0, 0)）。

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from csp_lib.controller.core import Command, ConfigMixin, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.services import PVDataService
from csp_lib.core import get_logger
from csp_lib.core.runtime_params import RuntimeParameters

from ._param_resolver import ParamResolver

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
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

    執行模式：PERIODIC (預設 900 秒週期，v0.8.0 起 float)

    Runtime 動態化 (v0.8.2):
        傳入 ``params`` + ``param_keys`` 即可讓 EMS 透過 RuntimeParameters
        即時覆蓋以下欄位（key 由 ``param_keys`` 映射，欄位缺失則 fallback config）：

            - capacity / ramp_rate / pv_loss / min_history

        額外旗標：
            - ``enabled_key``: params[enabled_key] 為 falsy → 立即輸出
              ``Command(p_target=0, q_target=0)``（與原行為一致，安全降級）

    Args:
        config: PV 平滑配置，None 時使用預設值。
        pv_service: PV 資料服務（注入）。
        interval_seconds: 執行週期 (秒)，v0.8.0 起支援 float 次秒級。
        params: RuntimeParameters，可選。必須與 ``param_keys`` 同時提供或同時省略。
        param_keys: {config 欄位名: runtime key} 映射。
        enabled_key: runtime 啟停旗標 key。

    Usage:
        pv_service = PVDataService(max_history=300)
        config = PVSmoothConfig(capacity=1000, ramp_rate=10)
        strategy = PVSmoothStrategy(config, pv_service)
    """

    DEFAULT_INTERVAL: float = 900.0

    def __init__(
        self,
        config: PVSmoothConfig | None = None,
        pv_service: PVDataService | None = None,
        interval_seconds: float = DEFAULT_INTERVAL,
        *,
        params: RuntimeParameters | None = None,
        param_keys: Mapping[str, str] | None = None,
        enabled_key: str | None = None,
    ) -> None:
        """初始化 PV 平滑策略。

        Args:
            config: PV 平滑配置
            pv_service: PV 資料服務（注入）
            interval_seconds: 執行週期（秒），v0.8.0 起支援 float
            params: RuntimeParameters，可選
            param_keys: config 欄位名 → runtime key 映射
            enabled_key: runtime 啟停旗標 key
        """
        self._config = config or PVSmoothConfig()
        self._pv_service = pv_service
        self._interval = interval_seconds
        self._resolver = ParamResolver(
            params=params,
            param_keys=param_keys,
            config=self._config,
        )
        self._enabled_key = enabled_key

    @property
    def config(self) -> PVSmoothConfig:
        """當前配置"""
        return self._config

    @property
    def pv_service(self) -> PVDataService | None:
        """PV 資料服務"""
        return self._pv_service

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=self._interval)

    def execute(self, context: StrategyContext) -> Command:
        """
        執行 PV 平滑策略，計算目標功率輸出

        策略流程：
        1. Runtime enabled 檢查（動態停用時輸出 Command(0, 0)）
        2. 前置條件檢查 (PV Service 存在性、歷史資料充足性)
        3. 計算歷史平均功率
        4. 扣除系統損耗
        5. 套用斜率限制 (Ramp Rate Limiting) 防止功率劇烈變化

        Args:
            context: 策略上下文，包含上次指令等狀態資訊

        Returns:
            Command: 包含目標有功功率 (p_target) 和無功功率 (q_target) 的指令
        """
        # Runtime enabled 旗標：falsy → 立即輸出 0
        if self._enabled_key is not None:
            enabled = self._resolver.resolve_optional(self._enabled_key, True)
            if not enabled:
                logger.debug("PVSmoothStrategy: runtime disabled via '{}'", self._enabled_key)
                return Command(p_target=0.0, q_target=0.0)

        # 前置條件檢查 - PV 資料服務存在性
        if self._pv_service is None:
            logger.warning("PVSmoothStrategy: 未設定 PVDataService，回傳 0")
            return Command(p_target=0.0, q_target=0.0)

        # 讀取動態配置欄位
        min_history = int(self._resolver.resolve("min_history"))
        capacity = float(self._resolver.resolve("capacity"))
        ramp_rate = float(self._resolver.resolve("ramp_rate"))
        pv_loss = float(self._resolver.resolve("pv_loss"))

        # 前置條件檢查 - 歷史資料充足性
        if self._pv_service.count < min_history:
            logger.debug(f"PVSmoothStrategy: 歷史資料不足 ({self._pv_service.count}/{min_history})")
            return Command(p_target=0.0, q_target=0.0)

        # 計算歷史平均功率
        average_power = self._pv_service.get_average()
        if average_power is None:
            logger.debug("PVSmoothStrategy: 無有效資料，回傳 0")
            return Command(p_target=0.0, q_target=0.0)

        # 扣除系統損耗（使用 max(_, 0.0) 確保調整後功率不為負值）
        adjusted_power = max(average_power - pv_loss, 0.0)

        # 計算斜率限制：容量 × 變化率百分比
        rate_limit = capacity * ramp_rate / 100.0

        # 取得上次指令的有功功率作為變化基準（NO_CHANGE 降級為 0.0）
        last_command_p = context.last_command.effective_p(0.0)

        # 套用斜率限制，計算最終目標功率
        max_p = last_command_p + rate_limit
        min_p = last_command_p - rate_limit
        target_p = max(min(adjusted_power, max_p), min_p)

        logger.debug(
            f"PVSmoothStrategy: avg={average_power:.1f}, adjusted={adjusted_power:.1f}, "
            f"target={target_p:.1f} (ramp limit: ±{rate_limit:.1f})"
        )

        return Command(p_target=target_p, q_target=0.0)

    def update_config(self, config: PVSmoothConfig) -> None:
        """更新配置並重建 resolver（保留既有 runtime 設定）。"""
        self._config = config
        self._resolver = self._resolver.with_config(self._config)

    def set_pv_service(self, pv_service: PVDataService) -> None:
        """設定 PV 資料服務"""
        self._pv_service = pv_service

    def __str__(self) -> str:
        return f"PVSmoothStrategy(capacity={self._config.capacity}, ramp_rate={self._config.ramp_rate}%)"
