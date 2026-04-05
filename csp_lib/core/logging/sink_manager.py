# =============== Core - Logging - Sink Manager ===============
#
# 全域 Sink 管理器
#
# 集中管理所有 loguru sink 的新增、移除、列表：
#   - SinkInfo: Sink 資訊（不可變）
#   - SinkManager: 全域單例，統一 sink 操作

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, ClassVar

from loguru import logger as _root_logger

from .async_sink import AsyncSinkAdapter
from .file_config import FileSinkConfig
from .filter import LogFilter
from .remote import RemoteLevelSource

# 預設格式字串
DEFAULT_FORMAT: str = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[module]}</cyan> | "
    "<level>{message}</level>"
)


@dataclass(frozen=True, slots=True)
class SinkInfo:
    """Sink 資訊。

    Attributes:
        sink_id: loguru 內部 sink ID。
        name: 使用者指定的名稱。
        sink_type: Sink 類型（``"stderr"`` | ``"file"`` | ``"custom"`` | ``"async"``）。
        level: 設定的最低等級。
        is_active: 是否仍在使用中。
    """

    sink_id: int
    name: str
    sink_type: str
    level: str
    is_active: bool


class SinkManager:
    """全域 Sink 管理器（單例）。

    集中管理所有 loguru sink 的生命週期。提供新增、移除、
    列表查詢等操作，並整合 LogFilter 進行模組等級控制。

    Class Attributes:
        _instance: 單例實例。

    Attributes:
        _filter: 模組等級過濾器。
        _sinks: sink_id → SinkInfo 的對應表。
        _async_adapters: sink_id → AsyncSinkAdapter 的對應表。
        _remote_source: 目前連接的遠端等級來源。
        _remote_task: 遠端輪詢的 asyncio task。

    Example:
        ```python
        mgr = SinkManager.get_instance()
        sid = mgr.add_sink(sys.stderr, name="console", sink_type="stderr")
        mgr.set_level("DEBUG", module="csp_lib.mongo")
        mgr.remove_sink(sid)
        ```
    """

    _instance: ClassVar[SinkManager | None] = None

    def __init__(self) -> None:
        self._filter = LogFilter()
        self._sinks: dict[int, SinkInfo] = {}
        self._async_adapters: dict[int, AsyncSinkAdapter] = {}
        self._remote_source: RemoteLevelSource | None = None
        self._remote_task: asyncio.Task[None] | None = None

    # ---- 單例管理 ----

    @classmethod
    def get_instance(cls) -> SinkManager:
        """取得全域單例實例。

        Returns:
            SinkManager 單例。
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置單例（測試用）。

        移除所有 managed sinks 並重建 LogFilter。
        """
        if cls._instance is not None:
            cls._instance.remove_all()
        cls._instance = cls()

    # ---- 屬性 ----

    @property
    def filter(self) -> LogFilter:
        """取得模組等級過濾器。"""
        return self._filter

    # ---- Sink 操作 ----

    def add_sink(
        self,
        sink: Any,
        *,
        name: str,
        sink_type: str = "custom",
        level: str = "TRACE",
        format: str | None = None,
        enqueue: bool = False,
        serialize: bool = False,
        diagnose: bool = False,
        **loguru_kwargs: Any,
    ) -> int:
        """新增 sink。

        Args:
            sink: loguru 可接受的 sink（檔案路徑、callable、file-like 等）。
            name: Sink 名稱（用於查詢）。
            sink_type: Sink 類型標記。
            level: 最低 log 等級（loguru 層級，與 filter 獨立）。
            format: 格式字串，``None`` 使用預設。
            enqueue: 是否啟用佇列寫入。
            serialize: 是否以 JSON 輸出。
            diagnose: 是否顯示 exception 的局部變數。
            **loguru_kwargs: 其餘傳給 ``loguru.add()`` 的參數。

        Returns:
            loguru sink ID。
        """
        sink_id: int = _root_logger.add(
            sink,
            filter=self._filter,  # type: ignore[arg-type]
            format=format or DEFAULT_FORMAT,
            level=level,
            enqueue=enqueue,
            serialize=serialize,
            diagnose=diagnose,
            **loguru_kwargs,
        )
        self._sinks[sink_id] = SinkInfo(
            sink_id=sink_id,
            name=name,
            sink_type=sink_type,
            level=level,
            is_active=True,
        )
        return sink_id

    def remove_sink(self, sink_id: int) -> None:
        """移除指定 sink。

        Args:
            sink_id: loguru sink ID。

        Raises:
            KeyError: 找不到對應的 sink。
        """
        if sink_id not in self._sinks:
            raise KeyError(f"Sink ID {sink_id} 不存在")
        _root_logger.remove(sink_id)
        del self._sinks[sink_id]
        # 清理 async adapter（若存在）
        adapter = self._async_adapters.pop(sink_id, None)
        if adapter is not None:
            # 排程關閉（best-effort）
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(adapter.close())
            except RuntimeError:
                pass

    def remove_sink_by_name(self, name: str) -> None:
        """依名稱移除 sink。

        Args:
            name: Sink 名稱。

        Raises:
            KeyError: 找不到對應名稱的 sink。
        """
        target_id: int | None = None
        for sid, info in self._sinks.items():
            if info.name == name:
                target_id = sid
                break
        if target_id is None:
            raise KeyError(f"Sink '{name}' 不存在")
        self.remove_sink(target_id)

    def list_sinks(self) -> list[SinkInfo]:
        """列出所有 managed sinks。

        Returns:
            SinkInfo 列表。
        """
        return list(self._sinks.values())

    def get_sink(self, name: str) -> SinkInfo | None:
        """依名稱查詢 sink。

        Args:
            name: Sink 名稱。

        Returns:
            匹配的 SinkInfo，找不到則回傳 ``None``。
        """
        for info in self._sinks.values():
            if info.name == name:
                return info
        return None

    def remove_all(self) -> None:
        """移除所有 managed sinks。

        同時取消遠端等級來源的背景 task（best-effort 同步取消）。
        """
        # 取消 remote source 背景 task
        if self._remote_task is not None:
            self._remote_task.cancel()
            self._remote_task = None
        self._remote_source = None

        for sink_id in list(self._sinks.keys()):
            try:
                _root_logger.remove(sink_id)
            except ValueError:
                pass  # sink 可能已被外部移除
        self._sinks.clear()
        # 關閉所有 async adapters
        for adapter in self._async_adapters.values():
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(adapter.close())
            except RuntimeError:
                pass
        self._async_adapters.clear()

    # ---- 等級控制 ----

    def set_level(self, level: str, module: str | None = None) -> None:
        """設定 log 等級（委派給 LogFilter，不 remove/re-add sink）。

        Args:
            level: Log 等級。
            module: 模組名稱，``None`` 表示設定預設等級。
        """
        if module is None:
            self._filter.default_level = level
        else:
            self._filter.set_module_level(module, level)

    # ---- WI-005: File Sink ----

    def add_file_sink(self, config: FileSinkConfig) -> int:
        """新增檔案 sink。

        Args:
            config: 檔案 sink 配置。

        Returns:
            loguru sink ID。
        """
        name = config.name or f"file:{config.path}"
        return self.add_sink(
            config.path,
            name=name,
            sink_type="file",
            level=config.level,
            format=config.format,
            enqueue=config.enqueue,
            serialize=config.serialize,
            rotation=config.rotation,
            retention=config.retention,
            compression=config.compression,
            encoding=config.encoding,
        )

    # ---- WI-011: Async Sink ----

    def add_async_sink(
        self,
        async_handler: Callable[[str], Awaitable[None]],
        *,
        name: str,
        level: str = "TRACE",
        max_queue_size: int = 10000,
        **loguru_kwargs: Any,
    ) -> int:
        """新增非同步 sink。

        Args:
            async_handler: 非同步 handler 函式。
            name: Sink 名稱。
            level: 最低等級。
            max_queue_size: 內部佇列上限。
            **loguru_kwargs: 其餘傳給 ``add_sink`` 的參數。

        Returns:
            loguru sink ID。
        """
        adapter = AsyncSinkAdapter(
            async_handler,
            max_queue_size=max_queue_size,
        )
        sink_id = self.add_sink(
            adapter.write,
            name=name,
            sink_type="async",
            level=level,
            **loguru_kwargs,
        )
        self._async_adapters[sink_id] = adapter
        return sink_id

    # ---- WI-010: Remote Level Source ----

    async def attach_remote_source(
        self,
        source: RemoteLevelSource,
        poll_interval: float = 60.0,
    ) -> None:
        """連接遠端等級來源。

        立即拉取一次等級設定，然後啟動背景輪詢 task。

        Args:
            source: 遠端等級來源實例。
            poll_interval: 輪詢間隔秒數。
        """
        # 先中斷舊連線
        await self.detach_remote_source()

        self._remote_source = source

        # 立即拉取一次
        levels = await source.fetch_levels()
        self._apply_remote_levels(levels)

        # 訂閱即時變更
        await source.subscribe(self._on_remote_level_change)

        # 啟動背景輪詢
        self._remote_task = asyncio.create_task(self._poll_remote(source, poll_interval))

    async def detach_remote_source(self) -> None:
        """中斷遠端等級來源連線。"""
        if self._remote_task is not None:
            self._remote_task.cancel()
            try:
                await self._remote_task
            except asyncio.CancelledError:
                pass
            self._remote_task = None
        self._remote_source = None

    def _apply_remote_levels(self, levels: dict[str, str]) -> None:
        """將遠端等級設定套用至 LogFilter。

        Args:
            levels: 模組 → 等級對應表。空字串 key 代表預設等級。
        """
        for module, level in levels.items():
            if module == "":
                self._filter.default_level = level
            else:
                self._filter.set_module_level(module, level)

    def _on_remote_level_change(self, module: str, level: str) -> None:
        """遠端等級變更回呼。

        Args:
            module: 模組名稱。
            level: 新等級。
        """
        if module == "":
            self._filter.default_level = level
        else:
            self._filter.set_module_level(module, level)

    async def _poll_remote(
        self,
        source: RemoteLevelSource,
        interval: float,
    ) -> None:
        """背景輪詢遠端等級來源。

        Args:
            source: 遠端等級來源實例。
            interval: 輪詢間隔秒數。
        """
        while True:
            await asyncio.sleep(interval)
            try:
                levels = await source.fetch_levels()
                self._apply_remote_levels(levels)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                pass  # 輪詢失敗不應中斷

    # ---- 便利方法 ----

    def add_stderr_sink(
        self,
        *,
        level: str = "TRACE",
        format: str | None = None,
        enqueue: bool = False,
        serialize: bool = False,
        diagnose: bool = False,
    ) -> int:
        """新增 stderr sink（便利方法）。

        Args:
            level: 最低等級。
            format: 格式字串。
            enqueue: 是否佇列寫入。
            serialize: 是否 JSON 輸出。
            diagnose: 是否顯示 exception 局部變數。

        Returns:
            loguru sink ID。
        """
        return self.add_sink(
            sys.stderr,
            name="stderr",
            sink_type="stderr",
            level=level,
            format=format,
            enqueue=enqueue,
            serialize=serialize,
            diagnose=diagnose,
        )


__all__ = [
    "DEFAULT_FORMAT",
    "SinkInfo",
    "SinkManager",
]
