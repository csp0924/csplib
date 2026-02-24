# =============== Core - Lifecycle ===============
#
# Async 生命週期 Mixin
#
# 提供標準的 start/stop 與 async context manager 框架：
#   - AsyncLifecycleMixin: 子類覆寫 _on_start/_on_stop 即可

from __future__ import annotations

from typing import Any, Self


class AsyncLifecycleMixin:
    """
    Async 生命週期 Mixin

    提供標準的 start/stop 與 async context manager 實作框架。
    子類別只需覆寫 ``_on_start()`` 與 ``_on_stop()`` 即可。

    使用範例::

        class MyService(AsyncLifecycleMixin):
            async def _on_start(self) -> None:
                # 啟動邏輯
                ...

            async def _on_stop(self) -> None:
                # 停止邏輯
                ...

        async with MyService() as svc:
            ...
    """

    async def start(self) -> None:
        """啟動服務"""
        await self._on_start()

    async def stop(self) -> None:
        """停止服務"""
        await self._on_stop()

    async def _on_start(self) -> None:
        """子類別覆寫此方法以實作啟動邏輯"""

    async def _on_stop(self) -> None:
        """子類別覆寫此方法以實作停止邏輯"""

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()


__all__ = [
    "AsyncLifecycleMixin",
]
