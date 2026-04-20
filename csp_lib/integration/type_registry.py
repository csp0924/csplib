# =============== Integration - TypeRegistry ===============
#
# Decorator-driven 類型註冊表。K8s Operator Pattern 的 "Kind" 查找層。
#
# 兩個獨立 singleton：
#   - device_type_registry:   kind → AsyncModbusDevice 子類
#   - strategy_type_registry: kind → Strategy 實作類
#
# 與 entry_points 的互補關係：
#   - 本 registry 走 in-process decorator 註冊（import time 生效）
#   - entry_points（group="csp_lib.integration.device_types"）留給第三方
#     套件未來擴充（非本 WI 實作）
#   - 兩者可共存：啟動時先 import 內建模組觸發 decorator，再載入 entry_points

from __future__ import annotations

import re
import threading
from typing import TYPE_CHECKING, Callable, Generic, TypeVar

from csp_lib.core import get_logger
from csp_lib.core.errors import ConfigurationError

if TYPE_CHECKING:
    from csp_lib.controller.core import Strategy
    from csp_lib.equipment.device import AsyncModbusDevice

logger = get_logger(__name__)

# kind 命名規則：字母或底線開頭，含字母/數字/_/-，不允許 "/"（namespace 留給未來）
_KIND_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

T = TypeVar("T")


class TypeRegistry(Generic[T]):
    """執行緒安全的 kind → class 註冊表。

    Args:
        label: 註冊表名稱（用於錯誤訊息），例: "device" / "strategy"
    """

    def __init__(self, label: str) -> None:
        self._label = label
        self._table: dict[str, type[T]] = {}
        self._lock = threading.Lock()

    def register(self, kind: str, cls: type[T], *, force: bool = False) -> None:
        """註冊 kind → cls。

        Args:
            kind:  類型識別字串，須匹配 ``^[A-Za-z_][A-Za-z0-9_-]*$``
            cls:   實作類
            force: 若 True，允許覆寫既有註冊（預設 False → raise ValueError）

        Raises:
            ValueError: kind 格式無效、或 kind 已註冊且 force=False
        """
        if not _KIND_PATTERN.match(kind):
            raise ValueError(f"TypeRegistry({self._label}): invalid kind '{kind}'; must match {_KIND_PATTERN.pattern}")
        with self._lock:
            existing = self._table.get(kind)
            if existing is not None and not force:
                raise ValueError(
                    f"TypeRegistry({self._label}): kind '{kind}' already "
                    f"registered to {existing!r}; pass force=True to override"
                )
            self._table[kind] = cls
        if existing is not None:
            logger.warning(f"TypeRegistry({self._label}): kind '{kind}' overridden ({existing!r} -> {cls!r})")

    def get(self, kind: str) -> type[T]:
        """查詢 kind 對應的類。

        Raises:
            ConfigurationError: kind 未註冊（manifest-driven 錯誤歸屬此族）
        """
        with self._lock:
            cls = self._table.get(kind)
            known = sorted(self._table.keys()) if cls is None else None
        if cls is None:
            raise ConfigurationError(f"TypeRegistry({self._label}): unknown kind '{kind}'; registered kinds: {known}")
        return cls

    def list(self) -> list[str]:
        """回傳已註冊的 kind 列表（排序後副本）。"""
        with self._lock:
            return sorted(self._table.keys())

    def __contains__(self, kind: object) -> bool:
        if not isinstance(kind, str):
            return False
        with self._lock:
            return kind in self._table


# ─────────── Singleton instances ───────────

device_type_registry: TypeRegistry["AsyncModbusDevice"] = TypeRegistry("device")
strategy_type_registry: TypeRegistry["Strategy"] = TypeRegistry("strategy")


# ─────────── Decorators ───────────


def register_device_type(
    kind: str, *, force: bool = False
) -> Callable[[type["AsyncModbusDevice"]], type["AsyncModbusDevice"]]:
    """Decorator：把 AsyncModbusDevice 子類註冊到 device_type_registry。

    Usage::

        @register_device_type("ExamplePCS")
        class ExamplePCSDevice(AsyncModbusDevice):
            ...

    Args:
        kind:  類型識別字串
        force: 覆寫既有註冊（預設 False）
    """

    def _wrap(cls: type["AsyncModbusDevice"]) -> type["AsyncModbusDevice"]:
        device_type_registry.register(kind, cls, force=force)
        return cls

    return _wrap


def register_strategy_type(kind: str, *, force: bool = False) -> Callable[[type["Strategy"]], type["Strategy"]]:
    """Decorator：把 Strategy 子類註冊到 strategy_type_registry。

    Usage::

        @register_strategy_type("PQStrategy")
        class PQStrategy(Strategy):
            ...
    """

    def _wrap(cls: type["Strategy"]) -> type["Strategy"]:
        strategy_type_registry.register(kind, cls, force=force)
        return cls

    return _wrap


__all__ = [
    "TypeRegistry",
    "device_type_registry",
    "strategy_type_registry",
    "register_device_type",
    "register_strategy_type",
]
