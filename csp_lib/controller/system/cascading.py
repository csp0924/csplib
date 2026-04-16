# =============== Cascading Strategy ===============
#
# 級聯功率分配策略
#
# 多策略共存時，每層輸出其「貢獻量」，逐層相加：
#   - PQ 貢獻 P=80kW, Q=0
#   - QV 貢獻 P=0, Q=50kVar
#   - 合計 P=80kW, Q=50kVar
#   - 若 S > S_max，依 priority 決定保留哪個軸

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, StrategyContext
from csp_lib.core import get_logger

if TYPE_CHECKING:
    from csp_lib.controller.core import Strategy

logger = get_logger(__name__)


class ClampPriority(str, Enum):
    """S_max 超限時的限幅優先級"""

    P_FIRST = "p_first"  # 保 P，削 Q
    Q_FIRST = "q_first"  # 保 Q，削 P


@dataclass(frozen=True, slots=True)
class CapacityConfig:
    """
    系統容量配置

    Attributes:
        s_max_kva: 最大視在功率 (kVA)
    """

    s_max_kva: float


class CascadingStrategy:
    """
    級聯功率分配策略（加法式）

    每層策略輸出其「貢獻量」（不是總量），逐層相加後限幅。

    流程：
    1. 每層獨立執行，輸出此層的 P/Q 貢獻
    2. 所有層的 P 和 Q 分別累加
    3. 若 S = √(P²+Q²) > S_max，依 priority 決定保留哪個軸

    Usage::

        cascading = CascadingStrategy(
            layers=[pq_strategy, qv_strategy],
            capacity=CapacityConfig(s_max_kva=200),
            priority=ClampPriority.P_FIRST,  # 超限時保 P 削 Q
        )
    """

    def __init__(
        self,
        layers: list[Strategy],
        capacity: CapacityConfig,
        priority: ClampPriority = ClampPriority.P_FIRST,
        execution_config: ExecutionConfig | None = None,
    ) -> None:
        self._layers = layers
        self._capacity = capacity
        self._priority = priority
        self._execution_config = execution_config or ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    @property
    def execution_config(self) -> ExecutionConfig:
        return self._execution_config

    def execute(self, context: StrategyContext) -> Command:
        """
        逐層執行策略，加法式累積後限幅

        Args:
            context: 策略上下文

        Returns:
            累積並限幅後的 Command
        """
        if not self._layers:
            return context.last_command

        s_max = self._capacity.s_max_kva
        total_p = 0.0
        total_q = 0.0

        for i, layer in enumerate(self._layers):
            # 建構此層的 context：last_command 為目前累積值
            s_used = math.hypot(total_p, total_q)
            remaining = max(0.0, s_max - s_used)
            layer_context = replace(
                context,
                last_command=Command(p_target=total_p, q_target=total_q),
                extra={**context.extra, "remaining_s_kva": remaining},
            )

            # 執行此層策略，output 是此層的「貢獻量」
            layer_output = layer.execute(layer_context)

            # 若某層輸出 NO_CHANGE，視為「此層不貢獻」（0.0）
            layer_p = layer_output.effective_p(0.0)
            layer_q = layer_output.effective_q(0.0)

            logger.trace(f"Layer {i} ({layer}): contribution P={layer_p:.1f}, Q={layer_q:.1f}")

            # 加法式累積
            total_p += layer_p
            total_q += layer_q

        # 限幅：若 S > S_max，依 priority 保留一個軸，削減另一個
        total_s = math.hypot(total_p, total_q)
        if total_s > s_max and total_s > 0:
            if self._priority == ClampPriority.P_FIRST:
                # 保 P，削 Q
                p_clamped = math.copysign(min(abs(total_p), s_max), total_p)
                q_headroom = math.sqrt(max(0.0, s_max**2 - p_clamped**2))
                q_clamped = math.copysign(min(abs(total_q), q_headroom), total_q)
                logger.debug(
                    f"S={total_s:.1f} > S_max={s_max:.1f}, P_FIRST: "
                    f"P {total_p:.1f}->{p_clamped:.1f}, Q {total_q:.1f}->{q_clamped:.1f}"
                )
                total_p, total_q = p_clamped, q_clamped
            else:
                # 保 Q，削 P
                q_clamped = math.copysign(min(abs(total_q), s_max), total_q)
                p_headroom = math.sqrt(max(0.0, s_max**2 - q_clamped**2))
                p_clamped = math.copysign(min(abs(total_p), p_headroom), total_p)
                logger.debug(
                    f"S={total_s:.1f} > S_max={s_max:.1f}, Q_FIRST: "
                    f"P {total_p:.1f}->{p_clamped:.1f}, Q {total_q:.1f}->{q_clamped:.1f}"
                )
                total_p, total_q = p_clamped, q_clamped

        return Command(p_target=total_p, q_target=total_q)

    @property
    def suppress_heartbeat(self) -> bool:
        """級聯策略不暫停心跳"""
        return False

    async def on_activate(self) -> None:
        """委派給所有子策略"""
        for layer in self._layers:
            await layer.on_activate()

    async def on_deactivate(self) -> None:
        """委派給所有子策略"""
        for layer in self._layers:
            await layer.on_deactivate()

    def __str__(self) -> str:
        layer_names = ", ".join(str(s) for s in self._layers)
        return f"CascadingStrategy([{layer_names}], S_max={self._capacity.s_max_kva}kVA, {self._priority.value})"

    def __repr__(self) -> str:
        return self.__str__()


__all__ = [
    "CapacityConfig",
    "CascadingStrategy",
    "ClampPriority",
]
