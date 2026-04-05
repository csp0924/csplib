# =============== Core - Logging - Remote ===============
#
# 遠端等級來源協定
#
# 定義遠端 log 等級來源的介面：
#   - RemoteLevelSource: Protocol，供 Redis / HTTP 等實作

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class RemoteLevelSource(Protocol):
    """遠端 log 等級來源協定。

    定義從外部系統取得模組 log 等級設定的介面。
    實作者需提供一次性拉取與即時訂閱兩種模式。

    Example:
        ```python
        class MySource:
            async def fetch_levels(self) -> dict[str, str]:
                return {"csp_lib.mongo": "DEBUG"}

            async def subscribe(self, callback):
                # 監聽等級變更事件
                ...
        ```
    """

    async def fetch_levels(self) -> dict[str, str]:
        """從遠端拉取所有模組等級設定。

        Returns:
            模組名稱 → 等級字串的對應表。
            空字串 key 代表預設等級。
        """
        ...

    async def subscribe(self, callback: Callable[[str, str], None]) -> None:
        """訂閱等級變更事件。

        當遠端等級變更時，呼叫 callback(module, level)。

        Args:
            callback: 等級變更回呼函式，接收 (module, level)。
        """
        ...


__all__ = [
    "RemoteLevelSource",
]
