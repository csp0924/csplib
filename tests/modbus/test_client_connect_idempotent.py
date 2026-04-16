# =============== Modbus Tests - PymodbusTcpClient connect idempotency ===============
#
# 重現 BUG-006：`PymodbusTcpClient.connect()` 缺重複連線保護
#
# 現象：若在 connect 過程中（或並發情境）連續呼叫兩次 connect()，而底層
# pymodbus client 的 `connected` 狀態尚未翻為 True（例如 mock 情境 / race），
# `client.connect()` 會被重複呼叫，可能造成 socket 洩漏或連線狀態混亂。
#
# 修復前：僅靠 `if not client.connected` 防護，遇到 race / mock 情境會重複 connect
# 修復後：應使用內部 flag 或 asyncio.Lock，保證底層 connect 只被呼叫一次

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from csp_lib.modbus.config import ModbusTcpConfig


class TestPymodbusTcpClientIdempotentConnect:
    """PymodbusTcpClient 重複 connect() 保護測試"""

    async def test_consecutive_connect_calls_invoke_underlying_once(self):
        """
        BUG-006：連續 await connect() 兩次，第二次應看到 client.connected=True 跳過。

        Mock 場景：第一次 connect() 後 connected 翻為 True（模擬真實 pymodbus 行為）。
        修復後若網路掉線，client.connected 翻為 False 仍可正常重連（不卡 sticky flag）。
        """
        with (
            patch("csp_lib.modbus.clients.client._ensure_pymodbus_imported"),
            patch("csp_lib.modbus.clients.client._AsyncModbusTcpClient") as MockTcpCls,
        ):
            mock_inner = AsyncMock()
            mock_inner.connected = False

            async def fake_connect() -> bool:
                # 模擬真實 pymodbus：成功 connect 後 connected 翻為 True
                mock_inner.connected = True
                return True

            mock_inner.connect = AsyncMock(side_effect=fake_connect)
            MockTcpCls.return_value = mock_inner

            from csp_lib.modbus.clients.client import PymodbusTcpClient

            config = ModbusTcpConfig(host="192.168.1.1")
            client = PymodbusTcpClient(config)

            await client.connect()
            await client.connect()

            assert mock_inner.connect.await_count == 1, (
                f"已連線後再 connect() 不應重複呼叫底層；實際 {mock_inner.connect.await_count} 次"
            )

    async def test_reconnect_after_drop(self):
        """
        BUG-006 重連場景（Copilot review #3）：
        若網路掉線，client.connected 翻為 False，再呼叫 connect() 應觸發實際重連。
        修復前的 sticky flag 設計在此情境下會 early-return 卡死無法重連。
        """
        with (
            patch("csp_lib.modbus.clients.client._ensure_pymodbus_imported"),
            patch("csp_lib.modbus.clients.client._AsyncModbusTcpClient") as MockTcpCls,
        ):
            mock_inner = AsyncMock()
            mock_inner.connected = False

            async def fake_connect() -> bool:
                mock_inner.connected = True
                return True

            mock_inner.connect = AsyncMock(side_effect=fake_connect)
            MockTcpCls.return_value = mock_inner

            from csp_lib.modbus.clients.client import PymodbusTcpClient

            client = PymodbusTcpClient(ModbusTcpConfig(host="192.168.1.1"))
            await client.connect()
            assert mock_inner.connect.await_count == 1

            # 模擬網路掉線：connected 自動翻 False
            mock_inner.connected = False

            # 再呼叫 connect() 應觸發重連
            await client.connect()
            assert mock_inner.connect.await_count == 2, (
                "掉線後 connect() 應重新呼叫底層；sticky flag 設計會在此卡死"
            )

    async def test_connect_after_successful_connected_skips_underlying(self):
        """
        已連線（connected=True）後再呼叫 connect()，底層不應被再次呼叫。

        此為既有行為（由 `if not client.connected` 守護），作為基線確認。
        """
        with (
            patch("csp_lib.modbus.clients.client._ensure_pymodbus_imported"),
            patch("csp_lib.modbus.clients.client._AsyncModbusTcpClient") as MockTcpCls,
        ):
            mock_inner = AsyncMock()
            mock_inner.connected = True  # 已連線
            mock_inner.connect = AsyncMock(return_value=True)
            MockTcpCls.return_value = mock_inner

            from csp_lib.modbus.clients.client import PymodbusTcpClient

            config = ModbusTcpConfig(host="192.168.1.1")
            client = PymodbusTcpClient(config)

            await client.connect()
            assert mock_inner.connect.await_count == 0

    async def test_concurrent_connect_calls_invoke_underlying_once(self):
        """
        BUG-006 併發情境：asyncio.gather 兩個 connect coroutine，
        底層 connect 只應被呼叫一次。

        修復前：兩個 coroutine 都看到 connected=False，兩者都會 await
                client.connect()
        修復後：用 asyncio.Lock 或 flag 避免重複
        """
        import asyncio

        with (
            patch("csp_lib.modbus.clients.client._ensure_pymodbus_imported"),
            patch("csp_lib.modbus.clients.client._AsyncModbusTcpClient") as MockTcpCls,
        ):
            mock_inner = AsyncMock()
            mock_inner.connected = False

            async def fake_connect() -> bool:
                mock_inner.connected = True
                return True

            mock_inner.connect = AsyncMock(side_effect=fake_connect)
            MockTcpCls.return_value = mock_inner

            from csp_lib.modbus.clients.client import PymodbusTcpClient

            config = ModbusTcpConfig(host="192.168.1.1")
            client = PymodbusTcpClient(config)

            await asyncio.gather(client.connect(), client.connect())

            assert mock_inner.connect.await_count == 1, (
                f"併發 connect 觸發底層 {mock_inner.connect.await_count} 次，缺 lock 保護"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
