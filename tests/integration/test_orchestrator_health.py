"""SystemCommandOrchestrator.health() 單元測試（WI-IH-03）

涵蓋 status decision tree：

  - last_result_status == "aborted" → DEGRADED ("registered=N last=aborted")
  - else（含 last_result_status is None）→ HEALTHY
    - None → "registered=N no executions yet"
    - "success" → "registered=N last=success"

Counter 驗證：
  - execute() 兩條終止路徑（success / aborted）都更新 _total_executions / _last_executed_at /
    _last_result_status；aborted 額外 ++ _total_aborts。
  - KeyError（未註冊指令）→ counter 不變。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.integration.orchestrator import (
    CommandStep,
    SystemCommand,
    SystemCommandOrchestrator,
)
from csp_lib.integration.registry import DeviceRegistry


def _make_orchestrator() -> SystemCommandOrchestrator:
    return SystemCommandOrchestrator(DeviceRegistry())


def _make_success_device(device_id: str = "d1") -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=True)
    type(dev).is_connected = PropertyMock(return_value=True)
    type(dev).is_protected = PropertyMock(return_value=False)

    action_result = MagicMock()
    action_result.status = MagicMock()
    action_result.status.value = "success"
    action_result.error_message = None
    dev.execute_action = AsyncMock(return_value=action_result)
    return dev


def _make_failing_device(device_id: str = "d_fail") -> MagicMock:
    dev = _make_success_device(device_id)
    dev.execute_action = AsyncMock(side_effect=RuntimeError("simulated failure"))
    return dev


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestOrchestratorHealthInitialState:
    def test_never_executed_is_healthy_no_executions(self) -> None:
        """剛建立，未呼叫 execute → HEALTHY 'registered=0 no executions yet'。"""
        orch = _make_orchestrator()
        report = orch.health()

        assert isinstance(report, HealthReport)
        assert report.component == "SystemCommandOrchestrator"
        assert report.status == HealthStatus.HEALTHY
        assert report.message == "registered=0 no executions yet"

    def test_registered_commands_count_and_names_sorted(self) -> None:
        """details 應包含 sorted command 名稱列表。"""
        orch = _make_orchestrator()
        orch.register(SystemCommand(name="zeta", steps=[]))
        orch.register(SystemCommand(name="alpha", steps=[]))
        orch.register(SystemCommand(name="mu", steps=[]))

        report = orch.health()
        assert report.details["registered_commands_count"] == 3
        assert report.details["registered_command_names"] == ["alpha", "mu", "zeta"]
        # message 也帶 N
        assert report.message == "registered=3 no executions yet"

    def test_initial_counters_are_zero_or_none(self) -> None:
        orch = _make_orchestrator()
        report = orch.health()
        assert report.details["total_executions"] == 0
        assert report.details["total_aborts"] == 0
        assert report.details["last_executed_at"] is None
        assert report.details["last_result_status"] is None


# ---------------------------------------------------------------------------
# After execute
# ---------------------------------------------------------------------------


class TestOrchestratorHealthAfterExecute:
    async def test_after_successful_execute_is_healthy_last_success(self) -> None:
        """成功執行 → HEALTHY 'registered=N last=success'，total_executions=1，total_aborts=0。"""
        reg = DeviceRegistry()
        dev = _make_success_device("d1")
        reg.register(dev)

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="ok_cmd",
                steps=[CommandStep(action="start", device_ids=["d1"])],
            )
        )

        result = await orch.execute("ok_cmd")
        assert result.status == "success"

        report = orch.health()
        assert report.status == HealthStatus.HEALTHY
        assert report.message == "registered=1 last=success"
        assert report.details["total_executions"] == 1
        assert report.details["total_aborts"] == 0
        assert report.details["last_result_status"] == "success"
        assert isinstance(report.details["last_executed_at"], float)

    async def test_after_aborted_execute_is_degraded_last_aborted(self) -> None:
        """aborted 執行 → DEGRADED 'registered=N last=aborted'，total_executions=1，total_aborts=1。"""
        reg = DeviceRegistry()
        dev = _make_failing_device("d_fail")
        reg.register(dev)

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="bad_cmd",
                steps=[CommandStep(action="start", device_ids=["d_fail"])],
            )
        )

        result = await orch.execute("bad_cmd")
        assert result.status == "aborted"

        report = orch.health()
        assert report.status == HealthStatus.DEGRADED
        assert report.message == "registered=1 last=aborted"
        assert report.details["total_executions"] == 1
        assert report.details["total_aborts"] == 1
        assert report.details["last_result_status"] == "aborted"

    async def test_success_then_abort_sticks_aborted(self) -> None:
        """先 success 後 abort → 最終 DEGRADED（最後一次黏住）。"""
        reg = DeviceRegistry()
        dev_ok = _make_success_device("d_ok")
        dev_bad = _make_failing_device("d_bad")
        reg.register(dev_ok)
        reg.register(dev_bad)

        orch = SystemCommandOrchestrator(reg)
        orch.register(SystemCommand(name="ok_cmd", steps=[CommandStep(action="start", device_ids=["d_ok"])]))
        orch.register(SystemCommand(name="bad_cmd", steps=[CommandStep(action="start", device_ids=["d_bad"])]))

        await orch.execute("ok_cmd")
        await orch.execute("bad_cmd")

        report = orch.health()
        assert report.status == HealthStatus.DEGRADED
        assert report.details["total_executions"] == 2
        assert report.details["total_aborts"] == 1
        assert report.details["last_result_status"] == "aborted"

    async def test_abort_then_success_sticks_success(self) -> None:
        """先 abort 後 success → 最終 HEALTHY（最後一次黏住）。"""
        reg = DeviceRegistry()
        dev_ok = _make_success_device("d_ok")
        dev_bad = _make_failing_device("d_bad")
        reg.register(dev_ok)
        reg.register(dev_bad)

        orch = SystemCommandOrchestrator(reg)
        orch.register(SystemCommand(name="ok_cmd", steps=[CommandStep(action="start", device_ids=["d_ok"])]))
        orch.register(SystemCommand(name="bad_cmd", steps=[CommandStep(action="start", device_ids=["d_bad"])]))

        await orch.execute("bad_cmd")
        await orch.execute("ok_cmd")

        report = orch.health()
        assert report.status == HealthStatus.HEALTHY
        assert report.message == "registered=2 last=success"
        assert report.details["total_executions"] == 2
        assert report.details["total_aborts"] == 1
        assert report.details["last_result_status"] == "success"


# ---------------------------------------------------------------------------
# KeyError 不更新 counter
# ---------------------------------------------------------------------------


class TestOrchestratorKeyErrorDoesNotMutate:
    async def test_key_error_for_unregistered_command_does_not_update_counters(self) -> None:
        """execute('not_registered') raise KeyError；counter 必須維持原狀。"""
        orch = _make_orchestrator()

        # 先確認初始狀態
        before = orch.health()
        assert before.details["total_executions"] == 0
        assert before.details["total_aborts"] == 0
        assert before.details["last_result_status"] is None

        with pytest.raises(KeyError):
            await orch.execute("does_not_exist")

        after = orch.health()
        assert after.details["total_executions"] == 0
        assert after.details["total_aborts"] == 0
        assert after.details["last_result_status"] is None
        assert after.details["last_executed_at"] is None
        # 整體仍 HEALTHY
        assert after.status == HealthStatus.HEALTHY

    async def test_key_error_does_not_update_after_prior_success(self) -> None:
        """已成功一次後再 KeyError，counter 不應額外增加。"""
        reg = DeviceRegistry()
        dev = _make_success_device("d1")
        reg.register(dev)

        orch = SystemCommandOrchestrator(reg)
        orch.register(SystemCommand(name="ok_cmd", steps=[CommandStep(action="start", device_ids=["d1"])]))

        await orch.execute("ok_cmd")
        snapshot1 = orch.health().details
        assert snapshot1["total_executions"] == 1
        last_at_1 = snapshot1["last_executed_at"]

        with pytest.raises(KeyError):
            await orch.execute("not_a_command")

        snapshot2 = orch.health().details
        # 完全沒變
        assert snapshot2["total_executions"] == 1
        assert snapshot2["total_aborts"] == 0
        assert snapshot2["last_executed_at"] == last_at_1
        assert snapshot2["last_result_status"] == "success"


# ---------------------------------------------------------------------------
# Details 驗證
# ---------------------------------------------------------------------------


class TestOrchestratorHealthDetails:
    def test_all_required_keys_present(self) -> None:
        orch = _make_orchestrator()
        report = orch.health()

        required_keys = {
            "registered_commands_count",
            "registered_command_names",
            "total_executions",
            "total_aborts",
            "last_executed_at",
            "last_result_status",
        }
        assert required_keys.issubset(set(report.details.keys()))

    def test_registered_command_names_is_sorted_list(self) -> None:
        orch = _make_orchestrator()
        for name in ("c", "a", "b"):
            orch.register(SystemCommand(name=name, steps=[]))
        names = orch.health().details["registered_command_names"]
        assert isinstance(names, list)
        assert names == sorted(names)
        assert names == ["a", "b", "c"]
