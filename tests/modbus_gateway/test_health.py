"""Tests for ModbusGatewayServer.health() — 實作 HealthCheckable Protocol 的單元測試。

不依賴 pymodbus，不實際啟動 server；用 property/field 直接驗證 health() 對
internal state 的反映，以及 WritePipeline 寫入 hook 觸發 last_write_ts 更新。
"""

from __future__ import annotations

from csp_lib.core.health import HealthCheckable, HealthStatus
from csp_lib.modbus.types.numeric import Int32, UInt16
from csp_lib.modbus_gateway.config import (
    GatewayRegisterDef,
    GatewayServerConfig,
    RegisterType,
    WatchdogConfig,
)
from csp_lib.modbus_gateway.server import ModbusGatewayServer


def _make_server(*, watchdog_enabled: bool = False) -> ModbusGatewayServer:
    """建立一個未啟動的 server 實例（不占用 port）。"""
    config = GatewayServerConfig(
        host="127.0.0.1",
        port=15599,
        unit_id=1,
        watchdog=WatchdogConfig(enabled=watchdog_enabled, timeout_seconds=5.0),
    )
    registers = [
        GatewayRegisterDef(
            name="p_command",
            address=0,
            data_type=Int32(),
            register_type=RegisterType.HOLDING,
            writable=True,
        ),
        GatewayRegisterDef(
            name="soc",
            address=0,
            data_type=UInt16(),
            register_type=RegisterType.INPUT,
        ),
    ]
    return ModbusGatewayServer(config, registers)


class TestHealthCheckProtocol:
    def test_server_implements_health_checkable(self):
        """ModbusGatewayServer 結構性滿足 HealthCheckable Protocol。"""
        server = _make_server()
        assert isinstance(server, HealthCheckable)


class TestHealthStatus:
    def test_health_unhealthy_when_not_started(self):
        """尚未 _on_start → UNHEALTHY。"""
        server = _make_server()
        report = server.health()

        assert report.status == HealthStatus.UNHEALTHY
        assert report.component == "ModbusGatewayServer"
        assert "not running" in report.message
        assert report.details["running"] is False

    def test_health_details_expose_config(self):
        """details 揭露 host/port/unit_id/registers_count 等配置。"""
        server = _make_server()
        report = server.health()

        assert report.details["host"] == "127.0.0.1"
        assert report.details["port"] == 15599
        assert report.details["unit_id"] == 1
        assert report.details["registers_count"] == 2
        # internal hook 會 +1（_record_write）；若使用者另行 add_hook 會再增
        assert report.details["hooks_count"] >= 1
        assert report.details["sync_sources_count"] == 0

    def test_health_healthy_when_simulated_running(self):
        """mock _server 非 None 模擬 running → HEALTHY（watchdog 未啟用）。"""
        server = _make_server(watchdog_enabled=False)
        server._server = object()  # mock pymodbus server

        report = server.health()

        assert report.status == HealthStatus.HEALTHY
        assert report.details["running"] is True
        assert report.details["watchdog"]["enabled"] is False
        assert report.details["watchdog"]["is_timed_out"] is False

    def test_health_degraded_when_watchdog_timed_out(self):
        """watchdog 判定 timed_out → DEGRADED。"""
        server = _make_server(watchdog_enabled=True)
        server._server = object()  # 模擬 running
        server._watchdog._timed_out = True
        # elapsed 有值（從 construction 到現在）
        report = server.health()

        assert report.status == HealthStatus.DEGRADED
        assert "watchdog timeout" in report.message
        assert report.details["watchdog"]["is_timed_out"] is True
        assert "elapsed_seconds" in report.details["watchdog"]


class TestWriteTracking:
    async def test_last_write_ts_initially_none(self):
        """從未接收到寫入 → last_write_ts = None。"""
        server = _make_server()
        report = server.health()

        assert report.details["last_write_ts"] is None
        assert report.details["total_writes"] == 0

    async def test_internal_hook_updates_last_write_ts(self):
        """internal CallbackHook(_record_write) 觸發後，last_write_ts 與 total_writes 更新。"""
        server = _make_server()

        # 模擬 WritePipeline 成功寫入後呼叫 hook（不實際啟動 pymodbus server）
        await server._record_write("p_command", 0, 1500)
        await server._record_write("p_command", 1500, 2000)

        report = server.health()
        assert report.details["total_writes"] == 2
        assert report.details["last_write_ts"] is not None
        assert report.details["last_write_ts"] > 0  # unix timestamp
