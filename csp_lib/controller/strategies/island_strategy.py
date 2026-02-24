# =============== Island Mode Strategy ===============
#
# 離網模式策略 (Grid Forming)
# - 啟用時: 切離 ACB (set_open)
# - 停用時: 等待 sync_ok 後搭接 ACB (set_close)
#
# 使用 RelayProtocol 避免直接依賴 P3U30

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from csp_lib.controller.core import (
    Command,
    ConfigMixin,
    ExecutionConfig,
    ExecutionMode,
    Strategy,
    StrategyContext,
)
from csp_lib.core import get_logger

logger = get_logger(__name__)


# =============== Relay Protocol ===============


@runtime_checkable
class RelayProtocol(Protocol):
    """
    繼電器/斷路器控制協定

    用於 IslandModeStrategy 的 ACB 控制。
    實作此協定的設備需提供以下屬性和方法：
    - sync_ok: 同步狀態
    - sync_counter: 同步計數
    - set_open(): 開啟斷路器
    - set_close(): 閉合斷路器 (需 sync_ok)
    - set_force_close(): 強制閉合斷路器
    """

    @property
    def sync_ok(self) -> bool:
        """同步狀態"""
        ...

    @property
    def sync_counter(self) -> int:
        """同步計數"""
        ...

    async def set_open(self) -> None:
        """開啟斷路器"""
        ...

    async def set_close(self) -> None:
        """閉合斷路器 (需 sync_ok)"""
        ...

    async def set_force_close(self) -> None:
        """強制閉合斷路器"""
        ...


# =============== Island Mode Config ===============


@dataclass
class IslandModeConfig(ConfigMixin):
    """
    離網模式配置

    Attributes:
        sync_timeout: 等待 sync_ok 超時 (秒)，預設 60
    """

    sync_timeout: float = 60.0


# =============== Island Mode Strategy ===============


class IslandModeStrategy(Strategy):
    """
    離網模式策略 (Grid Forming / Island Mode)

    當策略啟用時，自動切離 ACB 進入離網模式。
    當策略停用時，等待 sync_ok 後自動搭接 ACB 返回併網模式。

    **重要**: 此策略使用 TRIGGERED 模式，不會主動發送命令。
    功率控制應由 PCS 自身的 VF 模式處理，或由其他策略組合使用。

    Usage:
        relay = P3U30(...)  # 實作 RelayProtocol
        strategy = IslandModeStrategy(relay, config=IslandModeConfig())

        # 啟用 -> 自動切離 ACB
        await executor.set_strategy(strategy)

        # 切換策略 -> 自動等待 sync_ok 後搭接 ACB
        await executor.set_strategy(other_strategy)
    """

    def __init__(
        self,
        relay: RelayProtocol,
        config: Optional[IslandModeConfig] = None,
    ) -> None:
        """
        初始化離網模式策略

        Args:
            relay: 實作 RelayProtocol 的設備 (如 P3U30)
            config: 離網模式配置
        """
        self._relay = relay
        self._config = config or IslandModeConfig()

    @property
    def config(self) -> IslandModeConfig:
        """當前配置"""
        return self._config

    @property
    def execution_config(self) -> ExecutionConfig:
        """執行配置: TRIGGERED 模式 - 不主動執行"""
        return ExecutionConfig(mode=ExecutionMode.TRIGGERED, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        """
        執行策略邏輯

        離網模式不發送功率命令，返回 last_command 維持現狀。
        """
        return context.last_command

    async def on_activate(self) -> None:
        """
        策略啟用: 切離 ACB

        開啟 ACB，使系統進入離網 (孤島) 模式。
        """
        logger.info("IslandModeStrategy: 啟用離網模式，切離 ACB")
        await self._relay.set_open()
        logger.info("IslandModeStrategy: ACB 已開啟，進入離網模式")

    async def on_deactivate(self) -> None:
        """
        策略停用: 等待 sync_ok 後搭接 ACB

        持續等待同步信號，確認後閉合 ACB 返回併網模式。
        """
        logger.info("IslandModeStrategy: 準備離開離網模式，等待 sync_ok...")

        # 等待 sync_ok
        timeout = self._config.sync_timeout
        elapsed = 0.0
        check_interval = 0.5

        while elapsed < timeout:
            if self._relay.sync_ok:
                break
            logger.debug(
                f"IslandModeStrategy: 等待同步中... counter={self._relay.sync_counter}, elapsed={elapsed:.1f}s"
            )
            await asyncio.sleep(check_interval)
            elapsed += check_interval

        if not self._relay.sync_ok:
            logger.critical(f"IslandModeStrategy: 等待 sync_ok 超時 ({timeout}s)，失敗，請手動處理 ACB")
        else:
            logger.info("IslandModeStrategy: sync_ok 確認，閉合 ACB")
            await self._relay.set_close()
            logger.info("IslandModeStrategy: ACB 已閉合，返回併網模式")

    def update_config(self, config: IslandModeConfig) -> None:
        """更新配置"""
        self._config = config

    def __str__(self) -> str:
        return "IslandModeStrategy()"
