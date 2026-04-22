"""
CSP Core Module

提供全域共用的核心功能：
- get_logger: 取得模組專屬的 logger 實例
- configure_logging: 設定全域 logging 配置
- set_level: 動態調整 log 等級
- add_file_sink: 新增檔案 sink
- LogFilter / SinkManager / LogContext / LogCapture 等進階日誌元件
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

from loguru import logger as _root_logger

from .errors import (
    AlarmError,
    CommunicationError,
    ConfigurationError,
    DeviceConnectionError,
    DeviceError,
    DeviceRegistryError,
    NotLeaderError,
    ProtectionError,
    StrategyExecutionError,
)
from .health import HealthCheckable, HealthReport, HealthStatus
from .lifecycle import AsyncLifecycleMixin
from .logging import (
    DEFAULT_FORMAT,
    AsyncSinkAdapter,
    CapturedRecord,
    FileSinkConfig,
    LogCapture,
    LogContext,
    LogFilter,
    RemoteLevelSource,
    SinkInfo,
    SinkManager,
)
from .reconciler import Reconciler, ReconcilerMixin, ReconcilerStatus
from .resilience import CircuitBreaker, CircuitState, RetryPolicy
from .runtime_params import RuntimeParameters

if TYPE_CHECKING:
    from loguru import Logger


# 模組 logger 快取
_module_loggers: dict[str, Logger] = {}


def get_logger(name: str) -> Logger:
    """取得模組專屬的 logger 實例。

    Args:
        name: 模組名稱 (e.g., ``"csp_lib.mongo"``, ``"csp_lib.redis"``)。

    Returns:
        綁定模組名稱的 logger 實例。

    Example:
        ```python
        from csp_lib.core import get_logger

        logger = get_logger("csp_lib.mongo")
        logger.info("This is from mongo module")
        ```
    """
    if name not in _module_loggers:
        _module_loggers[name] = _root_logger.bind(module=name)
    return _module_loggers[name]


def set_level(level: str, module: Optional[str] = None) -> None:
    """設定 log 等級。

    委派給 SinkManager 的 LogFilter，不會 remove/re-add sink。

    Args:
        level: Log 等級 (DEBUG, INFO, WARNING, ERROR, CRITICAL 等)。
        module: 模組名稱，若為 ``None`` 則設定全域等級。

    Example:
        ```python
        from csp_lib.core import set_level

        # 設定全域等級
        set_level("DEBUG")

        # 只對 mongo 模組設定 DEBUG
        set_level("DEBUG", module="csp_lib.mongo")
        ```
    """
    SinkManager.get_instance().set_level(level, module=module)


def configure_logging(
    level: str = "INFO",
    format_string: Optional[str] = None,
    *,
    enqueue: bool = False,
    json_output: bool = False,
    diagnose: bool = False,
    env_prefix: str | None = None,
) -> None:
    """初始化 logging 配置。

    先重置 SinkManager，移除 loguru 預設 sink，然後新增 stderr sink。
    支援透過環境變數覆蓋配置。

    Args:
        level: 預設 log 等級。
        format_string: 自訂格式字串（可選）。
        enqueue: 是否啟用佇列寫入（多執行緒安全）。
        json_output: 是否以 JSON 格式輸出。
        diagnose: 是否在 exception 中顯示局部變數（生產環境建議 ``False``）。
        env_prefix: 環境變數前綴（可選）。設定後會從環境變數讀取覆蓋配置。
            例如 ``env_prefix="CSP"`` 會讀取 ``CSP_LOG_LEVEL``、``CSP_LOG_FORMAT`` 等。

    Example:
        ```python
        from csp_lib.core import configure_logging

        configure_logging(level="DEBUG")
        configure_logging(level="INFO", enqueue=True, json_output=True)
        configure_logging(level="INFO", env_prefix="CSP")
        ```
    """
    # WI-008: 環境變數覆蓋
    if env_prefix is not None:
        level, format_string, enqueue, json_output, diagnose = _load_env_config(
            env_prefix, level, format_string, enqueue, json_output, diagnose
        )

    # 重置 SinkManager（移除所有 managed sinks + 重建 filter）
    SinkManager.reset()

    # 移除 loguru 預設 sink（id=0，若仍存在）
    try:
        _root_logger.remove()
    except ValueError:
        pass

    mgr = SinkManager.get_instance()
    mgr.set_level(level)

    # 新增 stderr sink
    mgr.add_stderr_sink(
        level="TRACE",
        format=format_string,
        enqueue=enqueue,
        serialize=json_output,
        diagnose=diagnose,
    )


def _load_env_config(
    prefix: str,
    level: str,
    format_string: str | None,
    enqueue: bool,
    json_output: bool,
    diagnose: bool,
) -> tuple[str, str | None, bool, bool, bool]:
    """從環境變數載入 logging 配置覆蓋值。

    支援的環境變數：
    - ``{prefix}_LOG_LEVEL``: Log 等級
    - ``{prefix}_LOG_FORMAT``: 格式字串
    - ``{prefix}_LOG_ENQUEUE``: 是否佇列寫入（``"true"`` / ``"1"``）
    - ``{prefix}_LOG_JSON``: 是否 JSON 輸出
    - ``{prefix}_LOG_DIAGNOSE``: 是否顯示局部變數

    Args:
        prefix: 環境變數前綴。
        level: 預設等級。
        format_string: 預設格式字串。
        enqueue: 預設佇列設定。
        json_output: 預設 JSON 設定。
        diagnose: 預設診斷設定。

    Returns:
        覆蓋後的 (level, format_string, enqueue, json_output, diagnose)。
    """
    env_level = os.environ.get(f"{prefix}_LOG_LEVEL")
    if env_level is not None:
        level = env_level.upper()

    env_format = os.environ.get(f"{prefix}_LOG_FORMAT")
    if env_format is not None:
        format_string = env_format

    env_enqueue = os.environ.get(f"{prefix}_LOG_ENQUEUE")
    if env_enqueue is not None:
        enqueue = env_enqueue.lower() in ("true", "1", "yes")

    env_json = os.environ.get(f"{prefix}_LOG_JSON")
    if env_json is not None:
        json_output = env_json.lower() in ("true", "1", "yes")

    env_diagnose = os.environ.get(f"{prefix}_LOG_DIAGNOSE")
    if env_diagnose is not None:
        diagnose = env_diagnose.lower() in ("true", "1", "yes")

    return level, format_string, enqueue, json_output, diagnose


def add_file_sink(config: FileSinkConfig) -> int:
    """新增檔案 sink（便利函式）。

    委派給 ``SinkManager.get_instance().add_file_sink(config)``。

    Args:
        config: 檔案 sink 配置。

    Returns:
        loguru sink ID。
    """
    return SinkManager.get_instance().add_file_sink(config)


# 向後相容：提供預設 logger
logger = get_logger("csp_lib")

__all__ = [
    # 核心 logging API
    "get_logger",
    "set_level",
    "configure_logging",
    "add_file_sink",
    "logger",
    # Logging 元件
    "LogFilter",
    "SinkManager",
    "SinkInfo",
    "DEFAULT_FORMAT",
    "FileSinkConfig",
    "LogContext",
    "LogCapture",
    "CapturedRecord",
    "RemoteLevelSource",
    "AsyncSinkAdapter",
    # Lifecycle
    "AsyncLifecycleMixin",
    # Errors
    "DeviceError",
    "DeviceConnectionError",
    "CommunicationError",
    "AlarmError",
    "ConfigurationError",
    "StrategyExecutionError",
    "ProtectionError",
    "DeviceRegistryError",
    "NotLeaderError",
    # Health
    "HealthStatus",
    "HealthReport",
    "HealthCheckable",
    # Resilience
    "CircuitState",
    "CircuitBreaker",
    "RetryPolicy",
    # Runtime Parameters
    "RuntimeParameters",
    # Reconciler (Operator Pattern)
    "Reconciler",
    "ReconcilerMixin",
    "ReconcilerStatus",
]
