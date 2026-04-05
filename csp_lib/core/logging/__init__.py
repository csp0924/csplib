# =============== Core - Logging ===============
#
# 日誌子模組
#
# 提供進階日誌功能：
#   - LogFilter: 模組等級過濾器
#   - SinkManager / SinkInfo: 全域 sink 管理
#   - FileSinkConfig: 檔案 sink 配置
#   - LogContext: 結構化日誌上下文
#   - LogCapture / CapturedRecord: 測試用日誌捕獲
#   - RemoteLevelSource: 遠端等級來源協定
#   - AsyncSinkAdapter: 非同步 sink 轉接器

from __future__ import annotations

from .async_sink import AsyncSinkAdapter
from .capture import CapturedRecord, LogCapture
from .context import LogContext
from .file_config import FileSinkConfig
from .filter import LogFilter
from .remote import RemoteLevelSource
from .sink_manager import DEFAULT_FORMAT, SinkInfo, SinkManager

__all__ = [
    # WI-001: LogFilter
    "LogFilter",
    # WI-002: SinkManager + SinkInfo
    "SinkManager",
    "SinkInfo",
    "DEFAULT_FORMAT",
    # WI-004: FileSinkConfig
    "FileSinkConfig",
    # WI-007: LogContext
    "LogContext",
    # WI-009: LogCapture
    "LogCapture",
    "CapturedRecord",
    # WI-010: RemoteLevelSource
    "RemoteLevelSource",
    # WI-011: AsyncSinkAdapter
    "AsyncSinkAdapter",
]
