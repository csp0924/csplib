"""Tests for SystemCommandOrchestrator."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.integration.orchestrator import (
    CommandStep,
    StepCheck,
    SystemCommand,
    SystemCommandOrchestrator,
)
from csp_lib.integration.registry import DeviceRegistry


def _make_device(
    device_id: str,
    responsive: bool = True,
    actions: dict | None = None,
) -> MagicMock:
    """建立 mock 設備"""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_connected = PropertyMock(return_value=True)
    type(dev).is_protected = PropertyMock(return_value=False)

    action_result = MagicMock()
    action_result.status = MagicMock()
    action_result.status.value = "success"
    action_result.error_message = None
    dev.execute_action = AsyncMock(return_value=action_result)

    dev.ACTIONS = actions or {"start": None, "stop": None}
    return dev


def _make_failing_device(device_id: str, error_msg: str = "Action failed") -> MagicMock:
    """建立會失敗的 mock 設備"""
    dev = _make_device(device_id)
    dev.execute_action = AsyncMock(side_effect=RuntimeError(error_msg))
    return dev


class TestSystemCommandSchema:
    """Test schema dataclasses."""

    def test_step_check_defaults(self):
        check = StepCheck()
        assert check.trait is None
        assert check.device_ids is None
        assert check.check == "is_responsive"
        assert check.timeout == 10.0
        assert check.poll_interval == 0.5

    def test_step_check_custom(self):
        check = StepCheck(trait="pcs", check="is_connected", timeout=5.0, poll_interval=0.2)
        assert check.trait == "pcs"
        assert check.check == "is_connected"
        assert check.timeout == 5.0
        assert check.poll_interval == 0.2

    def test_command_step_defaults(self):
        step = CommandStep(action="start")
        assert step.action == "start"
        assert step.trait is None
        assert step.device_ids is None
        assert step.params == {}
        assert step.delay_before == 0.0
        assert step.check_after is None
        assert step.description == ""

    def test_command_step_with_trait(self):
        step = CommandStep(action="start", trait="mbms", description="Start MBMS")
        assert step.trait == "mbms"
        assert step.description == "Start MBMS"

    def test_command_step_with_device_ids(self):
        step = CommandStep(action="stop", device_ids=["d1", "d2"])
        assert step.device_ids == ["d1", "d2"]

    def test_command_step_with_params(self):
        step = CommandStep(action="set_power", trait="pcs", params={"p": 80})
        assert step.params == {"p": 80}

    def test_system_command(self):
        cmd = SystemCommand(
            name="system_start",
            steps=[
                CommandStep(action="start", trait="mbms"),
                CommandStep(action="start", trait="pcs"),
            ],
            description="Start all",
        )
        assert cmd.name == "system_start"
        assert len(cmd.steps) == 2
        assert cmd.description == "Start all"

    def test_system_command_frozen(self):
        cmd = SystemCommand(name="test", steps=[])
        with pytest.raises(AttributeError):
            cmd.name = "changed"  # type: ignore[misc]


class TestOrchestratorRegistration:
    """Test command registration."""

    def test_register_and_list(self):
        reg = DeviceRegistry()
        orch = SystemCommandOrchestrator(reg)
        cmd = SystemCommand(name="sys_start", steps=[])
        orch.register(cmd)
        assert "sys_start" in orch.registered_commands

    def test_register_overwrites(self):
        reg = DeviceRegistry()
        orch = SystemCommandOrchestrator(reg)
        cmd1 = SystemCommand(name="test", steps=[], description="v1")
        cmd2 = SystemCommand(name="test", steps=[], description="v2")
        orch.register(cmd1)
        orch.register(cmd2)
        assert orch.registered_commands == ["test"]

    def test_unregister(self):
        reg = DeviceRegistry()
        orch = SystemCommandOrchestrator(reg)
        orch.register(SystemCommand(name="test", steps=[]))
        orch.unregister("test")
        assert orch.registered_commands == []

    def test_unregister_nonexistent(self):
        reg = DeviceRegistry()
        orch = SystemCommandOrchestrator(reg)
        orch.unregister("nope")  # no error

    def test_registered_commands_sorted(self):
        reg = DeviceRegistry()
        orch = SystemCommandOrchestrator(reg)
        orch.register(SystemCommand(name="zzz", steps=[]))
        orch.register(SystemCommand(name="aaa", steps=[]))
        assert orch.registered_commands == ["aaa", "zzz"]


class TestOrchestratorExecute:
    """Test command execution."""

    @pytest.mark.asyncio
    async def test_execute_unregistered_raises(self):
        reg = DeviceRegistry()
        orch = SystemCommandOrchestrator(reg)
        with pytest.raises(KeyError, match="not registered"):
            await orch.execute("nope")

    @pytest.mark.asyncio
    async def test_execute_empty_steps(self):
        reg = DeviceRegistry()
        orch = SystemCommandOrchestrator(reg)
        orch.register(SystemCommand(name="empty", steps=[]))
        result = await orch.execute("empty")
        assert result.status == "success"
        assert result.step_results == []
        assert result.command_name == "empty"

    @pytest.mark.asyncio
    async def test_execute_single_step_by_trait(self):
        reg = DeviceRegistry()
        d1 = _make_device("mbms-1")
        d2 = _make_device("mbms-2")
        reg.register(d1, traits=["mbms"])
        reg.register(d2, traits=["mbms"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="start_mbms",
                steps=[CommandStep(action="start", trait="mbms")],
            )
        )

        result = await orch.execute("start_mbms")
        assert result.status == "success"
        assert len(result.step_results) == 1
        assert result.step_results[0].status == "success"
        assert result.step_results[0].device_results == {"mbms-1": "success", "mbms-2": "success"}

        d1.execute_action.assert_called_once_with("start")
        d2.execute_action.assert_called_once_with("start")

    @pytest.mark.asyncio
    async def test_execute_single_step_by_device_ids(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1")
        d2 = _make_device("d2")
        d3 = _make_device("d3")
        reg.register(d1)
        reg.register(d2)
        reg.register(d3)

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[CommandStep(action="stop", device_ids=["d1", "d3"])],
            )
        )

        result = await orch.execute("test")
        assert result.status == "success"
        d1.execute_action.assert_called_once_with("stop")
        d2.execute_action.assert_not_called()
        d3.execute_action.assert_called_once_with("stop")

    @pytest.mark.asyncio
    async def test_execute_with_params(self):
        reg = DeviceRegistry()
        d1 = _make_device("pcs-1")
        reg.register(d1, traits=["pcs"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="set_power",
                steps=[CommandStep(action="set_power", trait="pcs", params={"p": 80, "q": 10})],
            )
        )

        result = await orch.execute("set_power")
        assert result.status == "success"
        d1.execute_action.assert_called_once_with("set_power", p=80, q=10)

    @pytest.mark.asyncio
    async def test_execute_multi_step_sequence(self):
        reg = DeviceRegistry()
        mbms = _make_device("mbms-1")
        pcs = _make_device("pcs-1")
        reg.register(mbms, traits=["mbms"])
        reg.register(pcs, traits=["pcs"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="system_start",
                steps=[
                    CommandStep(action="start", trait="mbms", description="Start MBMS"),
                    CommandStep(action="start", trait="pcs", description="Start PCS"),
                ],
            )
        )

        result = await orch.execute("system_start")
        assert result.status == "success"
        assert len(result.step_results) == 2
        assert result.step_results[0].description == "Start MBMS"
        assert result.step_results[1].description == "Start PCS"
        mbms.execute_action.assert_called_once_with("start")
        pcs.execute_action.assert_called_once_with("start")

    @pytest.mark.asyncio
    async def test_execute_aborts_on_device_failure(self):
        reg = DeviceRegistry()
        mbms = _make_failing_device("mbms-1", "Connection refused")
        pcs = _make_device("pcs-1")
        reg.register(mbms, traits=["mbms"])
        reg.register(pcs, traits=["pcs"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="system_start",
                steps=[
                    CommandStep(action="start", trait="mbms", description="Start MBMS"),
                    CommandStep(action="start", trait="pcs", description="Start PCS"),
                ],
            )
        )

        result = await orch.execute("system_start")
        assert result.status == "aborted"
        assert result.aborted_at_step == 0
        assert "Connection refused" in result.error_message
        assert len(result.step_results) == 1
        # PCS step was never reached
        pcs.execute_action.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_aborts_on_partial_failure(self):
        """One device fails, one succeeds — step still aborts."""
        reg = DeviceRegistry()
        d1 = _make_device("mbms-1")
        d2 = _make_failing_device("mbms-2", "Timeout")
        reg.register(d1, traits=["mbms"])
        reg.register(d2, traits=["mbms"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[CommandStep(action="start", trait="mbms")],
            )
        )

        result = await orch.execute("test")
        assert result.status == "aborted"
        assert result.step_results[0].device_results["mbms-1"] == "success"
        assert "Timeout" in result.step_results[0].device_results["mbms-2"]

    @pytest.mark.asyncio
    async def test_execute_no_devices_found(self):
        reg = DeviceRegistry()
        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[CommandStep(action="start", trait="nonexistent")],
            )
        )

        result = await orch.execute("test")
        assert result.status == "aborted"
        assert result.step_results[0].status == "failed"
        assert "No devices found" in result.step_results[0].error_message

    @pytest.mark.asyncio
    async def test_execute_device_id_not_found_skipped(self):
        """Missing device_ids are skipped; if all missing, step fails."""
        reg = DeviceRegistry()
        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[CommandStep(action="start", device_ids=["ghost"])],
            )
        )

        result = await orch.execute("test")
        assert result.status == "aborted"
        assert result.step_results[0].status == "failed"

    @pytest.mark.asyncio
    async def test_execute_mixed_device_ids_partial_found(self):
        """Some device_ids exist, some don't — only found ones are acted on."""
        reg = DeviceRegistry()
        d1 = _make_device("d1")
        reg.register(d1)

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[CommandStep(action="start", device_ids=["d1", "ghost"])],
            )
        )

        result = await orch.execute("test")
        assert result.status == "success"
        assert result.step_results[0].device_results["d1"] == "success"
        d1.execute_action.assert_called_once_with("start")

    @pytest.mark.asyncio
    async def test_execute_action_result_with_failed_status(self):
        """Device returns ActionResult with non-success status."""
        reg = DeviceRegistry()
        dev = _make_device("d1")
        action_result = MagicMock()
        action_result.status = MagicMock()
        action_result.status.value = "write_failed"
        action_result.error_message = "Register locked"
        dev.execute_action = AsyncMock(return_value=action_result)
        reg.register(dev, traits=["test"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[CommandStep(action="start", trait="test")],
            )
        )

        result = await orch.execute("test")
        assert result.status == "aborted"
        assert "Register locked" in result.step_results[0].device_results["d1"]


class TestOrchestratorActionDeviceProtocol:
    """驗證 orchestrator 對不支援 execute_action 的設備會 gracefully skip。"""

    async def test_device_without_execute_action_is_skipped(self):
        """若 device 缺 execute_action，該設備記為 'action not supported'、其他設備仍執行。"""
        from csp_lib.integration.registry import DeviceRegistry

        # d1 缺 execute_action（模擬 DerivedDevice / RemoteSnapshotDevice）
        d1 = MagicMock()
        type(d1).device_id = PropertyMock(return_value="d1")
        type(d1).is_responsive = PropertyMock(return_value=True)
        type(d1).is_connected = PropertyMock(return_value=True)
        type(d1).is_protected = PropertyMock(return_value=False)
        d1.execute_action = None  # callable(None) is False → 走 skip 分支（比 del 更可靠）

        d2 = _make_device("d2")

        reg = DeviceRegistry()
        reg.register(d1, traits=["test"])
        reg.register(d2, traits=["test"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(SystemCommand(name="test", steps=[CommandStep(action="start", trait="test")]))

        result = await orch.execute("test")

        # d1 被跳過（記 'action not supported'）、d2 正常執行（未出現在 failure list）
        assert result.status == "success"
        step = result.step_results[0]
        assert step.device_results["d1"] == "action not supported"
        assert step.device_results["d2"] == "success"
        d2.execute_action.assert_called_once_with("start")

    async def test_all_devices_without_action_still_succeeds(self):
        """若所有 device 都不支援 execute_action，step 仍視為 success（沒執行任何 action、也無 failure）。"""
        from csp_lib.integration.registry import DeviceRegistry

        d1 = MagicMock()
        type(d1).device_id = PropertyMock(return_value="d1")
        type(d1).is_responsive = PropertyMock(return_value=True)
        type(d1).is_connected = PropertyMock(return_value=True)
        type(d1).is_protected = PropertyMock(return_value=False)
        del d1.execute_action

        reg = DeviceRegistry()
        reg.register(d1, traits=["test"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(SystemCommand(name="test", steps=[CommandStep(action="start", trait="test")]))

        result = await orch.execute("test")
        assert result.status == "success"
        assert result.step_results[0].device_results["d1"] == "action not supported"


class TestOrchestratorDelayAndCheck:
    """Test delay and health check functionality."""

    @pytest.mark.asyncio
    async def test_delay_before(self):
        """Verify delay_before actually waits."""
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, traits=["test"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[CommandStep(action="start", trait="test", delay_before=0.05)],
            )
        )

        loop = asyncio.get_event_loop()
        t0 = loop.time()
        result = await orch.execute("test")
        elapsed = loop.time() - t0

        assert result.status == "success"
        assert elapsed >= 0.04  # allow small tolerance

    @pytest.mark.asyncio
    async def test_check_after_passes(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", responsive=True)
        reg.register(dev, traits=["test"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[
                    CommandStep(
                        action="start",
                        trait="test",
                        check_after=StepCheck(trait="test", check="is_responsive", timeout=1.0, poll_interval=0.05),
                    ),
                ],
            )
        )

        result = await orch.execute("test")
        assert result.status == "success"
        assert result.step_results[0].check_passed is True

    @pytest.mark.asyncio
    async def test_check_after_fails_timeout(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", responsive=False)
        reg.register(dev, traits=["test"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[
                    CommandStep(
                        action="start",
                        trait="test",
                        check_after=StepCheck(trait="test", check="is_responsive", timeout=0.1, poll_interval=0.02),
                    ),
                ],
            )
        )

        result = await orch.execute("test")
        assert result.status == "aborted"
        assert result.step_results[0].status == "check_failed"
        assert result.step_results[0].check_passed is False
        assert "timed out" in result.step_results[0].error_message

    @pytest.mark.asyncio
    async def test_check_after_with_device_ids(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True)
        d2 = _make_device("d2", responsive=True)
        reg.register(d1)
        reg.register(d2)

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[
                    CommandStep(
                        action="start",
                        device_ids=["d1", "d2"],
                        check_after=StepCheck(
                            device_ids=["d1", "d2"], check="is_responsive", timeout=1.0, poll_interval=0.05
                        ),
                    ),
                ],
            )
        )

        result = await orch.execute("test")
        assert result.status == "success"
        assert result.step_results[0].check_passed is True

    @pytest.mark.asyncio
    async def test_check_after_becomes_responsive(self):
        """Device becomes responsive during polling."""
        reg = DeviceRegistry()
        dev = MagicMock()
        type(dev).device_id = PropertyMock(return_value="d1")
        type(dev).is_connected = PropertyMock(return_value=True)
        type(dev).is_protected = PropertyMock(return_value=False)

        # Start not responsive, become responsive after first poll
        responsive_values = iter([False, False, True])
        type(dev).is_responsive = PropertyMock(side_effect=lambda: next(responsive_values, True))

        action_result = MagicMock()
        action_result.status = MagicMock()
        action_result.status.value = "success"
        action_result.error_message = None
        dev.execute_action = AsyncMock(return_value=action_result)

        reg.register(dev, traits=["test"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[
                    CommandStep(
                        action="start",
                        trait="test",
                        check_after=StepCheck(trait="test", check="is_responsive", timeout=2.0, poll_interval=0.05),
                    ),
                ],
            )
        )

        result = await orch.execute("test")
        assert result.status == "success"
        assert result.step_results[0].check_passed is True

    @pytest.mark.asyncio
    async def test_no_check_after_check_passed_is_none(self):
        """When no check_after, check_passed should be None."""
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, traits=["test"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[CommandStep(action="start", trait="test")],
            )
        )

        result = await orch.execute("test")
        assert result.step_results[0].check_passed is None

    @pytest.mark.asyncio
    async def test_check_no_devices_passes(self):
        """Health check with no matching devices passes."""
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, traits=["test"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[
                    CommandStep(
                        action="start",
                        trait="test",
                        check_after=StepCheck(trait="nonexistent", check="is_responsive", timeout=0.1),
                    ),
                ],
            )
        )

        result = await orch.execute("test")
        assert result.status == "success"


class TestOrchestratorExecuteFromDict:
    """Test execute_from_dict."""

    @pytest.mark.asyncio
    async def test_execute_from_dict_with_command_name(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, traits=["test"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(SystemCommand(name="test_cmd", steps=[CommandStep(action="start", trait="test")]))

        result = await orch.execute_from_dict({"command_name": "test_cmd"})
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_execute_from_dict_with_system_command(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, traits=["test"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(SystemCommand(name="test_cmd", steps=[CommandStep(action="start", trait="test")]))

        result = await orch.execute_from_dict({"system_command": "test_cmd"})
        assert result.status == "success"


class TestOrchestratorFullSequence:
    """Integration-style tests with full multi-step sequences."""

    @pytest.mark.asyncio
    async def test_system_start_stop_sequence(self):
        """Full system start/stop simulation."""
        reg = DeviceRegistry()
        mbms_devs = [_make_device(f"mbms-{i}") for i in range(1, 4)]
        pcs_devs = [_make_device(f"pcs-{i}") for i in range(1, 4)]
        for d in mbms_devs:
            reg.register(d, traits=["mbms"])
        for d in pcs_devs:
            reg.register(d, traits=["pcs"])

        orch = SystemCommandOrchestrator(reg)

        # Register start
        orch.register(
            SystemCommand(
                name="system_start",
                description="Start all MBMS then PCS",
                steps=[
                    CommandStep(
                        action="start",
                        trait="mbms",
                        description="Start all MBMS",
                        check_after=StepCheck(trait="mbms", check="is_responsive", timeout=1.0, poll_interval=0.05),
                    ),
                    CommandStep(
                        action="start",
                        trait="pcs",
                        delay_before=0.01,
                        description="Start all PCS",
                    ),
                ],
            )
        )

        # Register stop (reverse order)
        orch.register(
            SystemCommand(
                name="system_stop",
                description="Stop all PCS then MBMS",
                steps=[
                    CommandStep(action="stop", trait="pcs", description="Stop all PCS"),
                    CommandStep(action="stop", trait="mbms", delay_before=0.01, description="Stop all MBMS"),
                ],
            )
        )

        # Execute start
        start_result = await orch.execute("system_start")
        assert start_result.status == "success"
        assert len(start_result.step_results) == 2

        for d in mbms_devs:
            d.execute_action.assert_called_with("start")
        for d in pcs_devs:
            d.execute_action.assert_called_with("start")

        # Reset mocks
        for d in mbms_devs + pcs_devs:
            d.execute_action.reset_mock()

        # Execute stop
        stop_result = await orch.execute("system_stop")
        assert stop_result.status == "success"
        for d in pcs_devs:
            d.execute_action.assert_called_with("stop")
        for d in mbms_devs:
            d.execute_action.assert_called_with("stop")

    @pytest.mark.asyncio
    async def test_abort_skips_remaining_steps(self):
        """When step 1 of 3 fails, steps 2 and 3 are never executed."""
        reg = DeviceRegistry()
        d1 = _make_failing_device("d1")
        d2 = _make_device("d2")
        d3 = _make_device("d3")
        reg.register(d1, traits=["group1"])
        reg.register(d2, traits=["group2"])
        reg.register(d3, traits=["group3"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="test",
                steps=[
                    CommandStep(action="start", trait="group1"),
                    CommandStep(action="start", trait="group2"),
                    CommandStep(action="start", trait="group3"),
                ],
            )
        )

        result = await orch.execute("test")
        assert result.status == "aborted"
        assert result.aborted_at_step == 0
        assert len(result.step_results) == 1
        d2.execute_action.assert_not_called()
        d3.execute_action.assert_not_called()


class TestOrchestratorWithSystemController:
    """Test orchestrator integration with SystemController."""

    def test_system_controller_has_orchestrator(self):
        from csp_lib.integration.system_controller import SystemController, SystemControllerConfig

        reg = DeviceRegistry()
        config = SystemControllerConfig()
        sc = SystemController(reg, config)

        assert sc.orchestrator is not None
        assert isinstance(sc.orchestrator, SystemCommandOrchestrator)

    @pytest.mark.asyncio
    async def test_register_and_execute_via_controller(self):
        from csp_lib.integration.system_controller import SystemController, SystemControllerConfig

        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, traits=["test"])

        config = SystemControllerConfig()
        sc = SystemController(reg, config)
        sc.orchestrator.register(
            SystemCommand(
                name="test",
                steps=[CommandStep(action="start", trait="test")],
            )
        )

        result = await sc.orchestrator.execute("test")
        assert result.status == "success"
        dev.execute_action.assert_called_once_with("start")
