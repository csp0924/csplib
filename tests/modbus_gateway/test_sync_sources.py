"""Tests for SEC-018: sync_source HOLDING register ban.

v0.7.3 SEC-018: ModbusGatewayServer._update_register_callback 檢查
register_type == HOLDING 時 raise PermissionError，防止 sync_sources
（Redis / polling）覆寫 EMS 控制用的 HOLDING registers。
"""

from __future__ import annotations

import asyncio

import pytest

from csp_lib.modbus.types.numeric import UInt16
from csp_lib.modbus_gateway.config import (
    GatewayRegisterDef,
    GatewayServerConfig,
    RegisterType,
    WatchdogConfig,
)
from csp_lib.modbus_gateway.sync_sources import PollingCallbackSource


def _make_server_config() -> GatewayServerConfig:
    """建立最小 gateway server config。"""
    return GatewayServerConfig(
        host="127.0.0.1",
        port=15503,
        unit_id=1,
        watchdog=WatchdogConfig(enabled=False),
    )


def _make_register_defs() -> list[GatewayRegisterDef]:
    """建立包含 HOLDING 和 INPUT register 的定義。"""
    return [
        GatewayRegisterDef(
            name="p_command",
            address=0,
            data_type=UInt16(),
            register_type=RegisterType.HOLDING,
            writable=True,
        ),
        GatewayRegisterDef(
            name="soc",
            address=100,
            data_type=UInt16(),
            register_type=RegisterType.INPUT,
            scale=10,
        ),
    ]


class TestUpdateRegisterCallbackHoldingBan:
    """SEC-018: _update_register_callback 拒絕寫入 HOLDING register。

    修復前：sync_sources 可覆寫任意 register（包含 HOLDING 的 EMS 控制命令）。
    修復後：_update_register_callback 檢查 register_type，HOLDING → raise PermissionError。
    """

    async def test_update_register_callback_raises_permission_on_holding(self):
        """呼叫 _update_register_callback 寫入 HOLDING register 應 raise PermissionError。"""
        from csp_lib.modbus_gateway.server import ModbusGatewayServer

        server = ModbusGatewayServer(_make_server_config(), _make_register_defs())
        with pytest.raises(PermissionError):
            await server._update_register_callback("p_command", 100)

    async def test_update_register_callback_allows_input_register(self):
        """INPUT register 應正常更新。"""
        from csp_lib.modbus_gateway.server import ModbusGatewayServer

        server = ModbusGatewayServer(_make_server_config(), _make_register_defs())
        await server._update_register_callback("soc", 75)
        assert server.get_register("soc") == 75


class TestPollingSourceHoldingBan:
    """SEC-018: PollingCallbackSource 推送含 HOLDING register 的 payload 時應跳過。"""

    async def test_polling_source_skips_holding_register(self):
        """Polling 推送含 HOLDING 的 payload，HOLDING register 不應被更新，INPUT 照常。"""
        from csp_lib.modbus_gateway.server import ModbusGatewayServer

        server = ModbusGatewayServer(_make_server_config(), _make_register_defs())

        # 模擬 polling callback 回傳混合 HOLDING + INPUT
        async def fake_poll():
            return {"p_command": 999, "soc": 85}

        source = PollingCallbackSource(callback=fake_poll, interval=0.05)
        await source.start(server._update_register_callback)

        # 等待至少一次 poll
        await asyncio.sleep(0.2)
        await source.stop()

        # HOLDING register 不應被更新
        assert server.get_register("p_command") == 0
        # INPUT register 應正常更新
        assert server.get_register("soc") == 85

    async def test_polling_source_permission_error_does_not_crash_loop(self):
        """PermissionError 不應中斷 polling loop。

        驗證：連續推送包含 HOLDING 的 payload，loop 應持續執行。
        """
        from csp_lib.modbus_gateway.server import ModbusGatewayServer

        server = ModbusGatewayServer(_make_server_config(), _make_register_defs())

        poll_count = [0]

        async def fake_poll():
            poll_count[0] += 1
            # 每次都推送 HOLDING + INPUT
            return {"p_command": poll_count[0], "soc": 50 + poll_count[0]}

        source = PollingCallbackSource(callback=fake_poll, interval=0.05)
        await source.start(server._update_register_callback)

        await asyncio.sleep(0.3)
        await source.stop()

        # loop 應已執行多次而非在第一次 PermissionError 後停止
        assert poll_count[0] >= 3, f"Polling loop 應持續執行，但只跑了 {poll_count[0]} 次"
        # INPUT register 應被最後一次 poll 更新
        assert server.get_register("soc") > 50
