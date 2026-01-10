"""
CSP Core Module

提供全域共用的核心功能：
- get_logger: 取得模組專屬的 logger 實例
- configure_logging: 設定全域 logging 配置
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Optional

from loguru import logger as _root_logger

if TYPE_CHECKING:
    from loguru import Logger


# 模組 logger 快取
_module_loggers: dict[str, Logger] = {}

# 預設 log 等級
_default_level: str = "INFO"

# 模組專屬等級設定
_module_levels: dict[str, str] = {}


def get_logger(name: str) -> Logger:
    """
    取得模組專屬的 logger 實例

    Args:
        name: 模組名稱 (e.g., "csp_lib.mongo", "csp_lib.redis")

    Returns:
        綁定模組名稱的 logger 實例

    Example:
        ```python
        from csp_lib.core import get_logger

        logger = get_logger("csp_lib.mongo")
        logger.info("This is from mongo module")
        ```
    """
    if name not in _module_loggers:
        # 使用 bind 建立帶有模組名稱的 logger
        _module_loggers[name] = _root_logger.bind(module=name)

    return _module_loggers[name]


def set_level(level: str, module: Optional[str] = None) -> None:
    """
    設定 log 等級

    Args:
        level: Log 等級 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        module: 模組名稱，若為 None 則設定全域等級

    Example:
        ```python
        from csp_lib.core import set_level

        # 設定全域等級
        set_level("DEBUG")

        # 只對 mongo 模組設定 DEBUG
        set_level("DEBUG", module="csp_lib.mongo")
        ```
    """
    global _default_level

    level = level.upper()
    valid_levels = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
    if level not in valid_levels:
        raise ValueError(f"無效的 log 等級: {level}，有效值: {valid_levels}")

    if module is None:
        _default_level = level
    else:
        _module_levels[module] = level

    # 重新配置 logger
    _reconfigure_logger()


def _get_effective_level(module_name: str) -> str:
    """
    取得模組的有效 log 等級

    匹配規則：
    - 優先使用最精確（最長前綴）的設定
    - 例如：設定了 csp_lib.mongo 和 csp_lib.mongo.queue
      - csp_lib.mongo.writer 會使用 csp_lib.mongo 的設定
      - csp_lib.mongo.queue 會使用 csp_lib.mongo.queue 的設定（更精確）
    """
    best_match = ""
    target_level = _default_level

    for registered_module, level in _module_levels.items():
        # 檢查是否匹配（精確匹配或前綴匹配）
        if module_name == registered_module or module_name.startswith(registered_module + "."):
            # 選擇最長的匹配
            if len(registered_module) > len(best_match):
                best_match = registered_module
                target_level = level

    return target_level


def _reconfigure_logger() -> None:
    """重新配置 loguru logger"""
    _root_logger.remove()

    def _filter(record: dict) -> bool:
        """根據模組名稱過濾 log 等級"""
        module_name = record["extra"].get("module", "")
        target_level = _get_effective_level(module_name)

        # 比較等級
        level_no = _root_logger.level(target_level).no
        return record["level"].no >= level_no

    _root_logger.add(
        sys.stderr,
        filter=_filter,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[module]}</cyan> | "
            "<level>{message}</level>"
        ),
    )


def configure_logging(
    level: str = "INFO",
    format_string: Optional[str] = None,
) -> None:
    """
    初始化 logging 配置

    Args:
        level: 預設 log 等級
        format_string: 自訂格式字串 (可選)

    Example:
        ```python
        from csp_lib.core import configure_logging

        configure_logging(level="DEBUG")
        ```
    """
    global _default_level
    _default_level = level.upper()

    _root_logger.remove()

    def _filter(record: dict) -> bool:
        """根據模組名稱過濾 log 等級"""
        module_name = record["extra"].get("module", "")
        target_level = _get_effective_level(module_name)

        level_no = _root_logger.level(target_level).no
        return record["level"].no >= level_no

    default_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[module]}</cyan> | "
        "<level>{message}</level>"
    )

    _root_logger.add(
        sys.stderr,
        filter=_filter,
        format=format_string or default_format,
    )


# 向後相容：提供預設 logger
logger = get_logger("csp_lib")

__all__ = [
    "get_logger",
    "set_level",
    "configure_logging",
    "logger",
]
