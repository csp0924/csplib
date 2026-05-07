"""HeartbeatService.health() 單元測試（WI-IH-01）

涵蓋 status decision tree：

  1. last_error → UNHEALTHY
  2. is_paused → DEGRADED ("paused")
  3. configured but not started → DEGRADED ("configured but not started")
  4. running → HEALTHY ("running, run_count=N")
  5. idle (no config, not started) → HEALTHY ("idle (no mappings)")
"""

from __future__ import annotations

import asyncio

from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.core.reconciler import ReconcilerStatus
from csp_lib.integration.heartbeat import HeartbeatService
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import HeartbeatMapping


def _make_service(
    *,
    mappings: list[HeartbeatMapping] | None = None,
    use_capability: bool = False,
    interval: float = 1.0,
) -> HeartbeatService:
    reg = DeviceRegistry()
    return HeartbeatService(
        reg,
        mappings=mappings,
        interval=interval,
        use_capability=use_capability,
    )


# ---------------------------------------------------------------------------
# Status decision tree
# ---------------------------------------------------------------------------


class TestHeartbeatHealthStatusDecision:
    def test_idle_no_config_yields_healthy_idle_message(self) -> None:
        """完全空配置 + 未啟動 → HEALTHY 'idle (no mappings)'。"""
        svc = _make_service()
        report = svc.health()

        assert isinstance(report, HealthReport)
        assert report.status == HealthStatus.HEALTHY
        assert report.component == "HeartbeatService"
        assert report.message == "idle (no mappings)"

    def test_mappings_configured_but_not_started_is_degraded(self) -> None:
        """有 mappings 但未 start → DEGRADED 'configured but not started'。"""
        mapping = HeartbeatMapping(point_name="hb", trait="pcs")
        svc = _make_service(mappings=[mapping])
        report = svc.health()

        assert report.status == HealthStatus.DEGRADED
        assert report.message == "configured but not started"

    def test_use_capability_path_yields_degraded_when_not_started(self) -> None:
        """use_capability=True 但未 start → DEGRADED（capability 路徑也算配置）。"""
        svc = _make_service(use_capability=True)
        report = svc.health()

        assert report.status == HealthStatus.DEGRADED
        assert report.message == "configured but not started"

    async def test_running_not_paused_yields_healthy_running(self) -> None:
        """已 start + 未 paused → HEALTHY 'running, run_count=N'。"""
        mapping = HeartbeatMapping(point_name="hb", trait="pcs")
        svc = _make_service(mappings=[mapping], interval=0.05)

        await svc.start()
        try:
            # 等至少一個 tick 完成
            await asyncio.sleep(0.12)
            report = svc.health()
            assert report.status == HealthStatus.HEALTHY
            assert report.message.startswith("running, run_count=")
            # run_count 應 >= 1
            run_count = report.details["run_count"]
            assert run_count >= 1
        finally:
            await svc.stop()

    async def test_running_but_paused_yields_degraded_paused(self) -> None:
        """已 start + paused → DEGRADED 'paused'。"""
        mapping = HeartbeatMapping(point_name="hb", trait="pcs")
        svc = _make_service(mappings=[mapping], interval=0.05)

        await svc.start()
        svc.pause()
        try:
            report = svc.health()
            assert report.status == HealthStatus.DEGRADED
            assert report.message == "paused"
            assert report.details["is_paused"] is True
        finally:
            svc.resume()
            await svc.stop()

    def test_last_error_yields_unhealthy(self) -> None:
        """注入 last_error 至 status snapshot → UNHEALTHY 'reconcile error: ...'。"""
        mapping = HeartbeatMapping(point_name="hb", trait="pcs")
        svc = _make_service(mappings=[mapping])

        # 直接覆寫 _status 模擬上一次 reconcile 失敗
        svc._status = ReconcilerStatus(
            name=svc._status.name,
            last_run_at=123.0,
            last_error="RuntimeError('boom')",
            run_count=5,
            healthy=False,
        )
        report = svc.health()

        assert report.status == HealthStatus.UNHEALTHY
        assert "RuntimeError('boom')" in report.message
        assert report.message.startswith("reconcile error: ")
        assert report.details["last_error"] == "RuntimeError('boom')"

    def test_unhealthy_takes_precedence_over_paused(self) -> None:
        """last_error 優先於 is_paused：兩者都成立時應 UNHEALTHY。"""
        mapping = HeartbeatMapping(point_name="hb", trait="pcs")
        svc = _make_service(mappings=[mapping])
        svc._paused = True
        svc._status = ReconcilerStatus(
            name=svc._status.name,
            last_error="boom",
            run_count=1,
            healthy=False,
        )
        report = svc.health()

        assert report.status == HealthStatus.UNHEALTHY
        assert "boom" in report.message


# ---------------------------------------------------------------------------
# has_config 各路徑
# ---------------------------------------------------------------------------


class TestHasConfigDetection:
    """配置判定包含 mappings / targets / use_capability 三條路徑。"""

    def test_targets_path_triggers_configured_not_started(self) -> None:
        """有 targets 但未 start → DEGRADED（targets 也算 has_config）。

        透過建構子 ``targets`` 參數注入；用最小 mock target 即可。
        """
        from unittest.mock import AsyncMock, MagicMock

        target = MagicMock()
        type(target).identity = MagicMock(return_value="t1")
        target.identity = "t1"
        target.write = AsyncMock()

        reg = DeviceRegistry()
        svc = HeartbeatService(reg, targets=[target], interval=1.0)
        report = svc.health()

        assert report.status == HealthStatus.DEGRADED
        assert report.message == "configured but not started"
        assert report.details["targets_count"] == 1


# ---------------------------------------------------------------------------
# Details 驗證
# ---------------------------------------------------------------------------


class TestHeartbeatHealthDetails:
    """report.details 必須包含所有必需 keys，型別與值正確。"""

    def test_all_required_keys_present(self) -> None:
        mapping = HeartbeatMapping(point_name="hb", trait="pcs")
        svc = _make_service(mappings=[mapping], use_capability=True, interval=2.5)
        report = svc.health()

        required_keys = {
            "is_running",
            "is_paused",
            "run_count",
            "last_run_at",
            "last_error",
            "mappings_count",
            "targets_count",
            "use_capability",
            "interval_seconds",
        }
        assert required_keys.issubset(set(report.details.keys()))

    def test_details_values_match_internal_state(self) -> None:
        mapping = HeartbeatMapping(point_name="hb", trait="pcs")
        svc = _make_service(mappings=[mapping], use_capability=True, interval=2.5)
        report = svc.health()

        assert report.details["is_running"] is False
        assert report.details["is_paused"] is False
        assert report.details["run_count"] == 0
        assert report.details["last_run_at"] is None
        assert report.details["last_error"] is None
        assert report.details["mappings_count"] == 1
        assert report.details["targets_count"] == 0
        assert report.details["use_capability"] is True
        assert report.details["interval_seconds"] == 2.5

    def test_details_types(self) -> None:
        """各 detail 欄位型別檢查。"""
        svc = _make_service()
        report = svc.health()
        d = report.details
        assert isinstance(d["is_running"], bool)
        assert isinstance(d["is_paused"], bool)
        assert isinstance(d["run_count"], int)
        assert d["last_run_at"] is None or isinstance(d["last_run_at"], float)
        assert d["last_error"] is None or isinstance(d["last_error"], str)
        assert isinstance(d["mappings_count"], int)
        assert isinstance(d["targets_count"], int)
        assert isinstance(d["use_capability"], bool)
        assert isinstance(d["interval_seconds"], float)
