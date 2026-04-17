# =============== Ramp Stop Strategy ===============
#
# 斜坡降功率策略（維護型）
#
# 被 EventDrivenOverride push 後，從 last_command 開始按斜率降至 0。
# 使用實際 dt（monotonic clock）計算每步降幅。
#
# 與 StopStrategy 的區別：
#   StopStrategy: 立即 P=0（用於設備告警等需要立即停止的情境）
#   RampStopStrategy: 斜坡降至 0（用於通訊中斷等可容忍漸進停止的情境）
#
# 搭配 EventDrivenOverride + ModeManager 使用：
#   controller.register_mode("ramp_stop", RampStopStrategy(2000), ModePriority.PROTECTION)
#   controller.register_event_override(ContextKeyOverride(name="ramp_stop", key="comm_timeout"))
#
# v0.8.2: 擴充 params / param_keys / enabled_key kwargs 支援 runtime 動態化
# （rated_power, ramp_rate_pct）。原 positional ctor 100% 向後相容。

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.core import get_logger
from csp_lib.core.runtime_params import RuntimeParameters

from ._param_resolver import ParamResolver

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _RampStopRuntimeConfig:
    """RampStopStrategy 內部用 frozen config（非 public API）。

    供 ParamResolver 使用；外部仍透過 ctor positional args 傳入
    ``rated_power`` 與 ``ramp_rate_pct``，保留既有呼叫簽名。
    """

    rated_power: float
    ramp_rate_pct: float


class RampStopStrategy(Strategy):
    """
    斜坡降功率策略

    透過 ModeManager.push_override() 啟動，從當前功率開始按斜率降至 0。
    到達 0 後維持 P=0 直到被 pop_override() 移除。

    使用實際 dt（monotonic clock）計算每步降幅，不依賴固定 interval：
        ramp_step = ramp_rate_pct / 100 × rated_power × dt

    Runtime 動態化 (v0.8.2):
        傳入 ``params`` + ``param_keys`` 可讓 EMS 即時覆蓋
        ``rated_power`` / ``ramp_rate_pct``；``enabled_key`` falsy 時
        回 ``context.last_command``（保守策略，避免誤執行 ramp-down）。

    Args:
        rated_power: 系統額定功率 (kW)
        ramp_rate_pct: 斜率 (%/s)，預設 5.0 表示每秒降 5% 額定功率
        params: RuntimeParameters，可選（kwargs-only）
        param_keys: {"rated_power": "...", "ramp_rate_pct": "..."} 映射
        enabled_key: runtime 啟停旗標 key
    """

    def __init__(
        self,
        rated_power: float,
        ramp_rate_pct: float = 5.0,
        *,
        params: RuntimeParameters | None = None,
        param_keys: Mapping[str, str] | None = None,
        enabled_key: str | None = None,
    ) -> None:
        self._config = _RampStopRuntimeConfig(rated_power=rated_power, ramp_rate_pct=ramp_rate_pct)
        self._current_p: float = 0.0
        self._last_time: float | None = None
        self._resolver = ParamResolver(
            params=params,
            param_keys=param_keys,
            config=self._config,
        )
        self._enabled_key = enabled_key

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        # Runtime enabled 旗標：falsy → 保守策略，維持上次指令
        if self._enabled_key is not None:
            enabled = self._resolver.resolve_optional(self._enabled_key, True)
            if not enabled:
                logger.debug("RampStopStrategy: runtime disabled via '%s'", self._enabled_key)
                return context.last_command

        now = time.monotonic()
        dt = (now - self._last_time) if self._last_time is not None else 0.0
        self._last_time = now

        # 第一次執行：繼承上次功率（NO_CHANGE 降級為 0.0）
        if self._current_p == 0.0 and dt == 0.0:
            self._current_p = context.last_command.effective_p(0.0)
            logger.info(f"RampStop: starting ramp from {self._current_p:.1f}kW")

        # 已到 0 → 維持
        if self._current_p == 0.0:
            return Command(p_target=0.0, q_target=0.0)

        # 讀取動態配置
        rated = float(self._resolver.resolve("rated_power"))
        ramp_rate = float(self._resolver.resolve("ramp_rate_pct"))

        # 計算 ramp step
        ramp_step = ramp_rate / 100.0 * rated * dt

        if abs(self._current_p) <= ramp_step:
            self._current_p = 0.0
            logger.info("RampStop: reached P=0")
        elif self._current_p > 0:
            self._current_p -= ramp_step
        else:
            self._current_p += ramp_step

        logger.debug(f"RampStop: P={self._current_p:.1f}kW (dt={dt:.3f}s, step={ramp_step:.1f}kW)")
        return Command(p_target=self._current_p, q_target=0.0)

    async def on_activate(self) -> None:
        self._current_p = 0.0
        self._last_time = None
        logger.info(
            f"RampStopStrategy activated (rated={self._config.rated_power}kW, rate={self._config.ramp_rate_pct}%/s)"
        )

    async def on_deactivate(self) -> None:
        self._current_p = 0.0
        self._last_time = None
        logger.info("RampStopStrategy deactivated")

    def __str__(self) -> str:
        return f"RampStopStrategy(rated={self._config.rated_power}kW, rate={self._config.ramp_rate_pct}%/s)"


__all__ = ["RampStopStrategy"]
