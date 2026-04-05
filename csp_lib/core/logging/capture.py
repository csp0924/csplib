# =============== Core - Logging - Capture ===============
#
# 測試用日誌捕獲器
#
# 提供在 context manager 內攔截 loguru 輸出的工具：
#   - CapturedRecord: 單筆攔截記錄
#   - LogCapture: 日誌捕獲 context manager

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger as _root_logger


@dataclass
class CapturedRecord:
    """單筆捕獲的 log 記錄。

    Attributes:
        level: Log 等級名稱（如 ``"INFO"``）。
        message: 格式化前的原始訊息。
        module: 模組名稱（來自 ``extra["module"]``）。
        extra: 其餘 extra 欄位。
        time: 記錄時間。
    """

    level: str
    message: str
    module: str
    extra: dict[str, Any] = field(default_factory=dict)
    time: datetime | None = None


class LogCapture:
    """測試用日誌捕獲器。

    在 context manager 範圍內攔截所有 loguru 輸出，
    不經過 SinkManager 管理（直接操作 root logger）。

    Attributes:
        _level: 最低攔截等級。
        _records: 捕獲的記錄列表。
        _sink_id: loguru sink ID，用於離開時移除。

    Example:
        ```python
        with LogCapture(level="DEBUG") as cap:
            logger.info("hello")
        assert cap.contains("hello", level="INFO")
        ```
    """

    def __init__(self, level: str = "TRACE") -> None:
        self._level = level.upper()
        self._records: list[CapturedRecord] = []
        self._sink_id: int | None = None

    @property
    def records(self) -> list[CapturedRecord]:
        """取得所有捕獲的記錄。"""
        return self._records

    def __enter__(self) -> LogCapture:
        self._sink_id = _root_logger.add(
            self._handle,
            level=self._level,
            format="{message}",
            diagnose=False,
        )
        return self

    def __exit__(self, *args: Any) -> None:
        if self._sink_id is not None:
            _root_logger.remove(self._sink_id)
            self._sink_id = None

    def _handle(self, message: Any) -> None:
        """loguru sink handler，將 record 轉為 CapturedRecord。

        Args:
            message: loguru Message 物件（含 .record 屬性）。
        """
        record = message.record
        extra = dict(record["extra"])
        module = extra.pop("module", "")

        self._records.append(
            CapturedRecord(
                level=record["level"].name,
                message=record["message"],
                module=module,
                extra=extra,
                time=record["time"],
            )
        )

    def contains(
        self,
        message: str,
        *,
        level: str | None = None,
        module: str | None = None,
    ) -> bool:
        """檢查是否有匹配的記錄。

        Args:
            message: 訊息子字串（部分匹配）。
            level: 精確匹配等級（可選）。
            module: 精確匹配模組（可選）。

        Returns:
            ``True`` 若存在至少一筆匹配記錄。
        """
        for rec in self._records:
            if message not in rec.message:
                continue
            if level is not None and rec.level != level.upper():
                continue
            if module is not None and rec.module != module:
                continue
            return True
        return False

    def filter(
        self,
        *,
        level: str | None = None,
        module: str | None = None,
        message_pattern: str | None = None,
    ) -> list[CapturedRecord]:
        """過濾捕獲的記錄。

        Args:
            level: 精確匹配等級。
            module: 精確匹配模組。
            message_pattern: 正則表達式匹配訊息。

        Returns:
            匹配的記錄列表。
        """
        results: list[CapturedRecord] = []
        compiled = re.compile(message_pattern) if message_pattern else None

        for rec in self._records:
            if level is not None and rec.level != level.upper():
                continue
            if module is not None and rec.module != module:
                continue
            if compiled is not None and not compiled.search(rec.message):
                continue
            results.append(rec)

        return results

    def clear(self) -> None:
        """清除所有捕獲的記錄。"""
        self._records.clear()

    @property
    def text(self) -> str:
        """將所有捕獲的訊息合併為單一字串。

        Returns:
            以換行分隔的訊息文字。
        """
        return "\n".join(rec.message for rec in self._records)


__all__ = [
    "CapturedRecord",
    "LogCapture",
]
