# =============== Core - Logging - Filter ===============
#
# 模組等級過濾器
#
# 提供基於模組名稱的最長前綴匹配等級過濾：
#   - LogFilter: 可呼叫的 loguru filter，取代舊有 closure

from __future__ import annotations

from typing import Any

from loguru import logger as _root_logger

from .context import LogContext

# 有效的 loguru 等級
_VALID_LEVELS: frozenset[str] = frozenset({"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"})


def _validate_level(level: str) -> str:
    """驗證並正規化 log 等級。

    Args:
        level: Log 等級字串。

    Returns:
        大寫的等級字串。

    Raises:
        ValueError: 當等級字串無效時。
    """
    normalized = level.upper()
    if normalized not in _VALID_LEVELS:
        raise ValueError(f"無效的 log 等級: {level}，有效值: {_VALID_LEVELS}")
    return normalized


class LogFilter:
    """模組等級過濾器。

    透過最長前綴匹配，決定每條 log record 是否應被輸出。
    可直接作為 loguru 的 filter 參數使用（實作 ``__call__``）。

    Attributes:
        _default_level: 預設等級。
        _module_levels: 模組 → 等級的對應表。

    Example:
        ```python
        f = LogFilter(default_level="INFO")
        f.set_module_level("csp_lib.mongo", "DEBUG")
        logger.add(sys.stderr, filter=f)
        ```
    """

    def __init__(self, default_level: str = "INFO") -> None:
        self._default_level: str = _validate_level(default_level)
        self._module_levels: dict[str, str] = {}

    # ---- properties ----

    @property
    def default_level(self) -> str:
        """取得預設 log 等級。"""
        return self._default_level

    @default_level.setter
    def default_level(self, level: str) -> None:
        """設定預設 log 等級。

        Args:
            level: 新的預設等級。

        Raises:
            ValueError: 等級無效。
        """
        self._default_level = _validate_level(level)

    @property
    def module_levels(self) -> dict[str, str]:
        """取得模組等級對應表（防禦性複製）。"""
        return dict(self._module_levels)

    # ---- 模組等級操作 ----

    def set_module_level(self, module: str, level: str) -> None:
        """設定特定模組的 log 等級。

        Args:
            module: 模組名稱（如 ``"csp_lib.mongo"``）。
            level: Log 等級。

        Raises:
            ValueError: 等級無效。
        """
        self._module_levels[module] = _validate_level(level)

    def remove_module_level(self, module: str) -> None:
        """移除特定模組的等級設定，回歸預設等級。

        Args:
            module: 模組名稱。
        """
        self._module_levels.pop(module, None)

    def get_effective_level(self, module_name: str) -> str:
        """取得模組的有效 log 等級（最長前綴匹配）。

        匹配規則：
        - 精確匹配優先
        - 其次選擇最長前綴匹配
        - 無匹配則回傳預設等級

        Args:
            module_name: 模組名稱。

        Returns:
            有效的 log 等級字串。
        """
        best_match = ""
        target_level = self._default_level

        for registered_module, level in self._module_levels.items():
            if module_name == registered_module or module_name.startswith(registered_module + "."):
                if len(registered_module) > len(best_match):
                    best_match = registered_module
                    target_level = level

        return target_level

    # ---- loguru filter 介面 ----

    def __call__(self, record: dict[str, Any]) -> bool:
        """loguru filter 函式。

        從 ``record["extra"]["module"]`` 取得模組名稱，
        以最長前綴匹配決定是否輸出。

        Args:
            record: loguru 的 log record dict。

        Returns:
            ``True`` 表示該 record 應被輸出。
        """
        # 注入 LogContext 綁定（取代 loguru 0.8+ 的 patch 參數）
        ctx = LogContext.current()
        if ctx:
            record["extra"].update(ctx)

        module_name: str = record["extra"].get("module", "")
        target_level = self.get_effective_level(module_name)
        level_no: int = _root_logger.level(target_level).no
        return record["level"].no >= level_no


__all__ = [
    "LogFilter",
]
