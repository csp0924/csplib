# =============== Core - Logging - Context ===============
#
# 結構化日誌上下文
#
# 提供可巢狀的 context bindings，自動注入至 loguru record：
#   - LogContext: 同步/非同步 context manager + decorator

from __future__ import annotations

import contextvars
import functools
from typing import Any, Callable, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

# 全域 ContextVar，儲存當前執行緒/協程的 bindings
_context_var: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "log_context",
    default=None,
)


class LogContext:
    """結構化日誌上下文管理器。

    支援同步與非同步 context manager，以及 decorator 用法。
    巢狀使用時，內層會繼承外層的 bindings 並可覆蓋。

    Attributes:
        _bindings: 本次要新增/覆蓋的 key-value 對。
        _token: contextvars reset token，用於離開時還原。

    Example:
        ```python
        # context manager
        with LogContext(request_id="abc-123"):
            logger.info("處理請求")  # extra 含 request_id

        # async context manager
        async with LogContext(device_id="PCS-01"):
            logger.info("設備操作")

        # decorator
        @LogContext(operation="calibrate")
        async def calibrate():
            logger.info("校準中")
        ```
    """

    def __init__(self, **bindings: Any) -> None:
        self._bindings: dict[str, Any] = bindings
        self._token: contextvars.Token[dict[str, Any] | None] | None = None

    # ---- 同步 context manager ----

    def __enter__(self) -> LogContext:
        current = _context_var.get() or {}
        merged = {**current, **self._bindings}
        self._token = _context_var.set(merged)
        return self

    def __exit__(self, *args: Any) -> None:
        if self._token is not None:
            _context_var.reset(self._token)
            self._token = None

    # ---- 非同步 context manager ----

    async def __aenter__(self) -> LogContext:
        return self.__enter__()

    async def __aexit__(self, *args: Any) -> None:
        self.__exit__(*args)

    # ---- decorator ----

    def __call__(self, func: _F) -> _F:
        """作為 decorator 使用，自動在函式執行期間綁定上下文。

        Args:
            func: 要裝飾的函式（同步或非同步）。

        Returns:
            包裝後的函式。
        """
        if _is_coroutine_function(func):

            @functools.wraps(func)
            async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
                async with LogContext(**self._bindings):
                    return await func(*args, **kwargs)

            return _async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with LogContext(**self._bindings):
                return func(*args, **kwargs)

        return _sync_wrapper  # type: ignore[return-value]

    # ---- 靜態工具方法 ----

    @staticmethod
    def current() -> dict[str, Any]:
        """取得當前上下文的所有 bindings（防禦性複製）。

        Returns:
            當前 context bindings 的副本。
        """
        return dict(_context_var.get() or {})

    @staticmethod
    def bind(**bindings: Any) -> None:
        """直接在當前上下文新增 bindings（不需 context manager）。

        注意：此操作不可逆，除非使用 ``unbind()`` 移除。
        建議優先使用 context manager 以確保自動清理。

        Args:
            **bindings: 要新增的 key-value 對。
        """
        current = _context_var.get() or {}
        _context_var.set({**current, **bindings})

    @staticmethod
    def unbind(*keys: str) -> None:
        """從當前上下文移除指定的 bindings。

        Args:
            *keys: 要移除的 key 名稱。
        """
        current = _context_var.get() or {}
        updated = {k: v for k, v in current.items() if k not in keys}
        _context_var.set(updated)


def _is_coroutine_function(func: Any) -> bool:
    """判斷函式是否為 async 函式（Cython 相容）。

    Args:
        func: 要檢查的函式物件。

    Returns:
        ``True`` 若為 async 函式。
    """
    import asyncio

    return asyncio.iscoroutinefunction(func)


__all__ = [
    "LogContext",
]
