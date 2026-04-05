# =============== Cascading Strategy ===============
#
# 級聯功率分配策略
#
# 多策略共存時，依優先順序逐層分配功率：
#   - CapacityConfig: 系統容量配置
#   - CascadingStrategy: 級聯策略（delta-based clamping）
#
# Delta-based clamping 保護高優先層的分配：
#   PQ 先佔 P=600kW → QV 想加 Q=900 → S=√(600²+900²)=1082 > 1000
#   只縮放 QV 的 delta Q，不動 PQ 的 P → Q 限 ≈800kVar

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, StrategyContext
from csp_lib.core import get_logger

if TYPE_CHECKING:
    from csp_lib.controller.core import Strategy

logger = get_logger(__name__)


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
    級聯功率分配策略

    多策略依優先順序逐層分配功率，使用 delta-based clamping 確保高優先層分配不被修改。

    流程：
    1. 第一層收到原始 context（保留 executor 注入的 last_command）
    2. 後續層收到 last_command=當前累積值，extra["remaining_s_kva"]=剩餘容量
    3. 每層執行後計算 delta_p, delta_q，若加上 delta 後 S 超過容量，只縮放 delta

    Usage::

        cascading = CascadingStrategy(
            layers=[pq_strategy, qv_strategy],
            capacity=CapacityConfig(s_max_kva=1000),
            execution_config=ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1),
        )
    """

    def __init__(
        self,
        layers: list[Strategy],
        capacity: CapacityConfig,
        execution_config: ExecutionConfig | None = None,
    ) -> None:
        self._layers = layers
        self._capacity = capacity
        self._execution_config = execution_config or ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    @property
    def execution_config(self) -> ExecutionConfig:
        return self._execution_config

    def execute(self, context: StrategyContext) -> Command:
        """
        逐層執行策略，使用 delta-based clamping 限制總容量

        Args:
            context: 策略上下文（含 last_command 由 executor 注入）

        Returns:
            最終累積的 Command
        """
        if not self._layers:
            return context.last_command

        s_max = self._capacity.s_max_kva
        accumulated = Command(p_target=0.0, q_target=0.0)

        for i, layer in enumerate(self._layers):
            # 建構此層的 context
            if i == 0:
                layer_context = context
            else:
                s_used = math.hypot(accumulated.p_target, accumulated.q_target)
                remaining = max(0.0, s_max - s_used)
                layer_context = replace(
                    context,
                    last_command=accumulated,
                    extra={**context.extra, "remaining_s_kva": remaining},
                )

            # 執行此層策略
            layer_output = layer.execute(layer_context)

            # 計算 delta
            delta_p = layer_output.p_target - accumulated.p_target
            delta_q = layer_output.q_target - accumulated.q_target

            # 如果沒有增量，直接跳過 clamping
            if delta_p == 0.0 and delta_q == 0.0:
                continue

            # 計算加上 delta 後的 S
            new_p = accumulated.p_target + delta_p
            new_q = accumulated.q_target + delta_q
            new_s = math.hypot(new_p, new_q)

            if new_s > s_max and new_s > 0:
                # 只縮放 delta，保護高優先層的分配
                # 用二次方程求 t: |accumulated + t * delta|² = s_max²
                # A*t² + B*t + C = 0
                a_p, a_q = accumulated.p_target, accumulated.q_target
                a_coeff = delta_p**2 + delta_q**2  # A
                b_coeff = 2.0 * (a_p * delta_p + a_q * delta_q)  # B
                c_coeff = a_p**2 + a_q**2 - s_max**2  # C

                if a_coeff > 0:
                    discriminant = b_coeff**2 - 4.0 * a_coeff * c_coeff
                    if discriminant >= 0:
                        scale = (-b_coeff + math.sqrt(discriminant)) / (2.0 * a_coeff)
                        scale = max(0.0, min(1.0, scale))
                    else:
                        scale = 0.0
                    delta_p *= scale
                    delta_q *= scale
                    logger.debug(
                        f"Layer {i} delta clamped: scale={scale:.3f}, delta_p={delta_p:.1f}, delta_q={delta_q:.1f}"
                    )

            accumulated = Command(
                p_target=accumulated.p_target + delta_p,
                q_target=accumulated.q_target + delta_q,
            )

        return accumulated

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
        return f"CascadingStrategy([{layer_names}], S_max={self._capacity.s_max_kva}kVA)"

    def __repr__(self) -> str:
        return self.__str__()
