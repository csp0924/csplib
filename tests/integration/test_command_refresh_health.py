"""CommandRefreshService.health() 單元測試（WI-IH-02）

涵蓋 status decision tree：

  1. last_error → UNHEALTHY
  2. not is_running → DEGRADED ("not running")
  3. running → HEALTHY ("running, run_count=N")，run_count==0 也是 HEALTHY
"""

from __future__ import annotations

import asyncio

from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.core.reconciler import ReconcilerStatus
from csp_lib.integration.command_refresh import CommandRefreshService
from csp_lib.integration.command_router import CommandRouter
from csp_lib.integration.registry import DeviceRegistry


def _make_service(
    *,
    interval: float = 1.0,
    device_filter: frozenset[str] | None = None,
) -> CommandRefreshService:
    reg = DeviceRegistry()
    router = CommandRouter(reg, mappings=[])
    return CommandRefreshService(router, interval=interval, device_filter=device_filter)


# ---------------------------------------------------------------------------
# Status decision tree
# ---------------------------------------------------------------------------


class TestCommandRefreshHealthStatusDecision:
    def test_not_running_is_degraded(self) -> None:
        """未 start → DEGRADED 'not running'。"""
        svc = _make_service()
        report = svc.health()

        assert isinstance(report, HealthReport)
        assert report.component == "CommandRefreshService"
        assert report.status == HealthStatus.DEGRADED
        assert report.message == "not running"
        assert report.details["is_running"] is False

    async def test_running_with_zero_run_count_is_healthy(self) -> None:
        """剛 start，尚未跑完一個 tick → HEALTHY 'running, run_count=0'。

        為了取到 run_count=0 的 race window，使用較長 interval 並在
        start 後立即取 health()。
        """
        svc = _make_service(interval=5.0)
        await svc.start()
        try:
            report = svc.health()
            assert report.status == HealthStatus.HEALTHY
            # run_count 可能是 0 也可能是 1（取決於 race），無論如何都 HEALTHY
            assert report.message.startswith("running, run_count=")
            assert report.details["is_running"] is True
        finally:
            await svc.stop()

    async def test_running_with_positive_run_count_is_healthy(self) -> None:
        """跑了至少 1 個 tick → HEALTHY 'running, run_count=N'，N >= 1。"""
        svc = _make_service(interval=0.05)
        await svc.start()
        try:
            await asyncio.sleep(0.12)
            report = svc.health()
            assert report.status == HealthStatus.HEALTHY
            assert report.details["run_count"] >= 1
            assert report.message == f"running, run_count={report.details['run_count']}"
        finally:
            await svc.stop()

    def test_last_error_yields_unhealthy(self) -> None:
        """注入 last_error → UNHEALTHY。"""
        svc = _make_service()
        svc._status = ReconcilerStatus(
            name=svc._status.name,
            last_run_at=42.0,
            last_error="DeviceError('write failed')",
            run_count=3,
            healthy=False,
        )
        report = svc.health()

        assert report.status == HealthStatus.UNHEALTHY
        assert "DeviceError('write failed')" in report.message
        assert report.message.startswith("reconcile error: ")

    def test_unhealthy_takes_precedence_over_not_running(self) -> None:
        """last_error 優先於 not_running。"""
        svc = _make_service()
        svc._status = ReconcilerStatus(
            name=svc._status.name,
            last_error="boom",
            run_count=1,
            healthy=False,
        )
        # is_running 為 False（沒 start），但仍應 UNHEALTHY
        assert svc.is_running is False
        report = svc.health()
        assert report.status == HealthStatus.UNHEALTHY


# ---------------------------------------------------------------------------
# device_filter_size
# ---------------------------------------------------------------------------


class TestCommandRefreshDeviceFilterSize:
    def test_none_filter_yields_none_size(self) -> None:
        svc = _make_service(device_filter=None)
        report = svc.health()
        assert report.details["device_filter_size"] is None

    def test_filter_with_two_devices_yields_2(self) -> None:
        svc = _make_service(device_filter=frozenset({"a", "b"}))
        report = svc.health()
        assert report.details["device_filter_size"] == 2

    def test_empty_filter_yields_0(self) -> None:
        """空 frozenset 不是 None；應回 0 而非 None。"""
        svc = _make_service(device_filter=frozenset())
        report = svc.health()
        assert report.details["device_filter_size"] == 0


# ---------------------------------------------------------------------------
# Details 驗證
# ---------------------------------------------------------------------------


class TestCommandRefreshHealthDetails:
    def test_all_required_keys_present(self) -> None:
        svc = _make_service(interval=3.5)
        report = svc.health()
        required_keys = {
            "is_running",
            "run_count",
            "last_run_at",
            "last_error",
            "interval_seconds",
            "device_filter_size",
        }
        assert required_keys.issubset(set(report.details.keys()))

    def test_initial_state_details_correct(self) -> None:
        svc = _make_service(interval=3.5)
        report = svc.health()

        assert report.details["is_running"] is False
        assert report.details["run_count"] == 0
        assert report.details["last_run_at"] is None
        assert report.details["last_error"] is None
        assert report.details["interval_seconds"] == 3.5
        assert report.details["device_filter_size"] is None
