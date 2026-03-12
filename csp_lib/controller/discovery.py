# =============== Controller - Strategy Discovery ===============
#
# 策略插件自動發現機制
#
# 使用 importlib.metadata.entry_points 標準機制，
# 允許第三方套件透過 pyproject.toml 註冊策略：
#
#   [project.entry-points."csp_lib.strategies"]
#   my_custom_pq = "my_package.strategies:CustomPQStrategy"

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from csp_lib.core import get_logger

if TYPE_CHECKING:
    from .core import Strategy

logger = get_logger(__name__)

ENTRY_POINT_GROUP = "csp_lib.strategies"


@dataclass(frozen=True, slots=True)
class StrategyDescriptor:
    """
    策略描述

    Args:
        name: 策略名稱 (entry point name)
        strategy_class: 策略類別
        module: 策略所在模組路徑
        description: 策略說明 (來自 docstring)
    """

    name: str
    strategy_class: type[Strategy]
    module: str
    description: str


def discover_strategies(group: str = ENTRY_POINT_GROUP) -> list[StrategyDescriptor]:
    """
    自動發現已註冊的策略插件

    掃描 entry_points 中指定群組的所有策略，載入並返回描述列表。
    載入失敗的策略會被跳過並記錄警告。

    Args:
        group: entry point 群組名稱，預設為 "csp_lib.strategies"

    Returns:
        已發現的策略描述列表
    """
    eps = entry_points()
    # Python 3.12+ returns a SelectableGroups, use .select()
    selected = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, [])  # type: ignore[attr-defined]

    descriptors: list[StrategyDescriptor] = []
    for ep in selected:
        try:
            strategy_cls = ep.load()
            desc = (strategy_cls.__doc__ or "").strip().split("\n")[0]
            descriptors.append(
                StrategyDescriptor(
                    name=ep.name,
                    strategy_class=strategy_cls,
                    module=ep.value,
                    description=desc,
                )
            )
            logger.debug(f"發現策略插件: {ep.name} ({ep.value})")
        except Exception as exc:
            logger.warning(f"載入策略插件 '{ep.name}' 失敗: {exc}")

    return descriptors


__all__ = [
    "StrategyDescriptor",
    "discover_strategies",
    "ENTRY_POINT_GROUP",
]
