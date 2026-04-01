# =============== Mode Manager ===============
#
# 模式管理器
#
# 提供模式註冊、優先權切換：
#   - ModePriority: 預設優先等級
#   - ModeDefinition: 模式定義（名稱、策略、優先權）
#   - ModeManager: 模式管理器（base mode + override 堆疊）

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Awaitable, Callable

from csp_lib.core import get_logger

if TYPE_CHECKING:
    from csp_lib.controller.core import Strategy

logger = get_logger(__name__)


class SwitchSource(Enum):
    """模式切換來源（審計用）"""

    MANUAL = "manual"
    SCHEDULE = "schedule"
    EVENT = "event"
    INTERNAL = "internal"


class ModePriority(IntEnum):
    """預設模式優先等級"""

    SCHEDULE = 10
    MANUAL = 50
    PROTECTION = 100


@dataclass(frozen=True)
class ModeDefinition:
    """
    模式定義

    Attributes:
        name: 模式名稱（唯一）
        strategy: 策略實例
        priority: 優先等級（數值越大越優先）
        description: 模式描述
    """

    name: str
    strategy: Strategy
    priority: int
    description: str = ""


class ModeManager:
    """
    模式管理器

    管理模式註冊與切換，支援 base mode 與 override 堆疊。
    多個 override 同時活躍時，取 priority 最高者；
    無 override 時回退到 base mode。

    策略變更時透過 on_strategy_change callback 通知外部。
    """

    def __init__(
        self,
        on_strategy_change: Callable[[Strategy | None, Strategy | None], Awaitable[None]] | None = None,
    ) -> None:
        self._modes: dict[str, ModeDefinition] = {}
        self._base_mode_names: list[str] = []
        self._override_names: list[str] = []
        self._on_strategy_change = on_strategy_change
        self._last_switch_source: SwitchSource | None = None

    # ---- 註冊 / 移除 ----

    def register(self, name: str, strategy: Strategy, priority: int, description: str = "") -> None:
        """
        註冊模式

        Args:
            name: 模式名稱（必須唯一）
            strategy: 策略實例
            priority: 優先等級
            description: 模式描述

        Raises:
            ValueError: 模式名稱已存在
        """
        if name in self._modes:
            raise ValueError(f"Mode '{name}' is already registered")
        self._modes[name] = ModeDefinition(name=name, strategy=strategy, priority=priority, description=description)
        logger.debug(f"Mode registered: {name} (priority={priority})")

    def unregister(self, name: str) -> None:
        """
        移除模式

        同時清理 base mode 和 override 堆疊中的引用。

        Raises:
            KeyError: 模式名稱不存在
        """
        if name not in self._modes:
            raise KeyError(f"Mode '{name}' is not registered")
        del self._modes[name]
        if name in self._base_mode_names:
            self._base_mode_names.remove(name)
        if name in self._override_names:
            self._override_names.remove(name)
        logger.debug(f"Mode unregistered: {name}")

    # ---- 基礎模式 ----

    async def set_base_mode(self, name: str | None, *, source: SwitchSource | None = None) -> None:
        """
        設定基礎模式（向下相容：清除列表後設定單一 base mode）

        Args:
            name: 模式名稱，None 表示清除
            source: 切換來源（可選，審計用）

        Raises:
            KeyError: 模式名稱不存在
        """
        if name is not None and name not in self._modes:
            raise KeyError(f"Mode '{name}' is not registered")

        old_strategy = self.effective_strategy
        self._base_mode_names = [name] if name is not None else []
        new_strategy = self.effective_strategy
        if source is not None:
            self._last_switch_source = source
        logger.info(f"Base mode set to: {name}")
        await self._notify_change(old_strategy, new_strategy)

    async def add_base_mode(self, name: str, *, source: SwitchSource | None = None) -> None:
        """
        新增基礎模式（多 base mode 共存）

        已存在時靜默忽略。

        Args:
            name: 模式名稱
            source: 切換來源（可選，審計用）

        Raises:
            KeyError: 模式名稱不存在
        """
        if name not in self._modes:
            raise KeyError(f"Mode '{name}' is not registered")
        if name in self._base_mode_names:
            return

        old_strategy = self.effective_strategy
        self._base_mode_names.append(name)
        new_strategy = self.effective_strategy
        if source is not None:
            self._last_switch_source = source
        logger.info(f"Base mode added: {name}")
        await self._notify_change(old_strategy, new_strategy)

    async def remove_base_mode(self, name: str, *, source: SwitchSource | None = None) -> None:
        """
        移除基礎模式

        Args:
            name: 模式名稱
            source: 切換來源（可選，審計用）

        Raises:
            KeyError: 該 base mode 不在列表中
        """
        if name not in self._base_mode_names:
            raise KeyError(f"Base mode '{name}' is not active")

        old_strategy = self.effective_strategy
        self._base_mode_names.remove(name)
        new_strategy = self.effective_strategy
        if source is not None:
            self._last_switch_source = source
        logger.info(f"Base mode removed: {name}")
        await self._notify_change(old_strategy, new_strategy)

    # ---- 模式策略更新 ----

    async def update_mode_strategy(
        self,
        name: str,
        strategy: Strategy,
        *,
        source: SwitchSource | None = None,
        description: str | None = None,
    ) -> None:
        """
        替換已註冊模式的策略（原子操作）

        如果該模式當前是活躍的（在 base mode 或 override 中），
        自動呼叫 old.on_deactivate() 和 new.on_activate()，
        並觸發 _notify_change。

        Args:
            name: 模式名稱
            strategy: 新策略實例
            source: 切換來源（可選，審計用）
            description: 新描述（可選，None 時保留原描述）

        Raises:
            KeyError: 模式名稱不存在
        """
        if name not in self._modes:
            raise KeyError(f"Mode '{name}' is not registered")

        old_mode = self._modes[name]
        old_strategy = old_mode.strategy
        is_active = name in self._base_mode_names or name in self._override_names

        if is_active:
            await old_strategy.on_deactivate()

        self._modes[name] = ModeDefinition(
            name=name,
            strategy=strategy,
            priority=old_mode.priority,
            description=description if description is not None else old_mode.description,
        )

        if is_active:
            await strategy.on_activate()

        if source is not None:
            self._last_switch_source = source

        old_effective = old_strategy if is_active else None
        new_effective = strategy if is_active else None
        logger.info(f"Mode strategy updated: {name}")
        await self._notify_change(old_effective, new_effective)

    async def async_unregister(self, name: str, *, source: SwitchSource | None = None) -> None:
        """
        非同步移除模式（含生命週期管理）

        若模式在活躍狀態（base mode 或 override），先呼叫 on_deactivate()，
        然後觸發 _notify_change。

        Args:
            name: 模式名稱
            source: 切換來源（可選，審計用）

        Raises:
            KeyError: 模式名稱不存在
        """
        if name not in self._modes:
            raise KeyError(f"Mode '{name}' is not registered")

        mode = self._modes[name]
        old_strategy = self.effective_strategy
        is_active = name in self._base_mode_names or name in self._override_names

        if is_active:
            await mode.strategy.on_deactivate()

        del self._modes[name]
        if name in self._base_mode_names:
            self._base_mode_names.remove(name)
        if name in self._override_names:
            self._override_names.remove(name)

        if source is not None:
            self._last_switch_source = source

        new_strategy = self.effective_strategy
        logger.debug(f"Mode async unregistered: {name}")
        await self._notify_change(old_strategy, new_strategy)

    # ---- Override 堆疊 ----

    async def push_override(self, name: str, *, source: SwitchSource | None = None) -> None:
        """
        推入 override 模式

        Args:
            name: 模式名稱
            source: 切換來源（可選，審計用）

        Raises:
            KeyError: 模式名稱不存在
            ValueError: 該 override 已存在於堆疊中
        """
        if name not in self._modes:
            raise KeyError(f"Mode '{name}' is not registered")
        if name in self._override_names:
            raise ValueError(f"Override '{name}' is already active")

        old_strategy = self.effective_strategy
        self._override_names.append(name)
        new_strategy = self.effective_strategy
        if source is not None:
            self._last_switch_source = source
        logger.info(f"Override pushed: {name}")
        await self._notify_change(old_strategy, new_strategy)

    async def pop_override(self, name: str, *, source: SwitchSource | None = None) -> None:
        """
        移除指定 override 模式

        Args:
            name: 模式名稱
            source: 切換來源（可選，審計用）

        Raises:
            KeyError: 該 override 不在堆疊中
        """
        if name not in self._override_names:
            raise KeyError(f"Override '{name}' is not active")

        old_strategy = self.effective_strategy
        self._override_names.remove(name)
        new_strategy = self.effective_strategy
        if source is not None:
            self._last_switch_source = source
        logger.info(f"Override popped: {name}")
        await self._notify_change(old_strategy, new_strategy)

    async def clear_overrides(self) -> None:
        """清除所有 override"""
        old_strategy = self.effective_strategy
        self._override_names.clear()
        new_strategy = self.effective_strategy
        logger.info("All overrides cleared")
        await self._notify_change(old_strategy, new_strategy)

    # ---- 查詢 ----

    @property
    def effective_mode(self) -> ModeDefinition | None:
        """取得當前生效的模式（最高優先權 override > 單一 base mode）"""
        if self._override_names:
            best: ModeDefinition | None = None
            for name in self._override_names:
                mode = self._modes.get(name)
                if mode is not None and (best is None or mode.priority > best.priority):
                    best = mode
            return best
        if len(self._base_mode_names) == 1:
            return self._modes.get(self._base_mode_names[0])
        return None

    @property
    def effective_strategy(self) -> Strategy | None:
        """
        取得當前生效的策略

        override 時返回最高優先權 override 策略；
        單一 base mode 時返回該策略；
        多 base mode 時返回 None（由 SystemController 組合為 CascadingStrategy）。
        """
        mode = self.effective_mode
        return mode.strategy if mode is not None else None

    @property
    def base_mode_name(self) -> str | None:
        """當前基礎模式名稱（向下相容：多 base mode 時回傳第一個）"""
        return self._base_mode_names[0] if self._base_mode_names else None

    @property
    def base_mode_names(self) -> list[str]:
        """當前所有 base mode 名稱（依 priority 降序排列）"""
        modes = [self._modes[n] for n in self._base_mode_names if n in self._modes]
        modes.sort(key=lambda m: m.priority, reverse=True)
        return [m.name for m in modes]

    @property
    def base_strategies(self) -> list[Strategy]:
        """當前所有 base mode 的策略（依 priority 降序排列）"""
        modes = [self._modes[n] for n in self._base_mode_names if n in self._modes]
        modes.sort(key=lambda m: m.priority, reverse=True)
        return [m.strategy for m in modes]

    @property
    def active_override_names(self) -> list[str]:
        """當前活躍的 override 名稱列表"""
        return list(self._override_names)

    @property
    def registered_modes(self) -> dict[str, ModeDefinition]:
        """所有已註冊模式"""
        return dict(self._modes)

    @property
    def last_switch_source(self) -> SwitchSource | None:
        """最近一次模式切換的來源"""
        return self._last_switch_source

    # ---- 內部 ----

    async def _notify_change(self, old_strategy: Strategy | None, new_strategy: Strategy | None) -> None:
        """當 effective strategy 改變時通知外部"""
        if old_strategy is new_strategy:
            return
        if self._on_strategy_change is not None:
            await self._on_strategy_change(old_strategy, new_strategy)
