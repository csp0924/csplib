"""Tests for csp_lib.equipment.device.mixins (AlarmMixin + WriteMixin)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from csp_lib.equipment.alarm import AlarmEventType
from csp_lib.equipment.device.events import (
    EVENT_ALARM_CLEARED,
    EVENT_ALARM_TRIGGERED,
    EVENT_WRITE_COMPLETE,
    EVENT_WRITE_ERROR,
)
from csp_lib.equipment.device.mixins import AlarmMixin, WriteMixin
from csp_lib.equipment.transport import WriteResult, WriteStatus


# ======================== AlarmMixin ========================


class _AlarmHost(AlarmMixin):
    """Minimal host for AlarmMixin testing."""

    def __init__(self):
        self._alarm_manager = MagicMock()
        self._alarm_evaluators = []
        self._emitter = MagicMock()
        self._emitter.emit_await = AsyncMock()
        self._config = MagicMock()
        self._config.device_id = "test_device"


class TestAlarmMixin:
    def test_is_protected(self):
        host = _AlarmHost()
        host._alarm_manager.has_protection_alarm.return_value = True
        assert host.is_protected is True

        host._alarm_manager.has_protection_alarm.return_value = False
        assert host.is_protected is False

    def test_active_alarms(self):
        host = _AlarmHost()
        mock_alarms = [MagicMock(), MagicMock()]
        host._alarm_manager.get_active_alarms.return_value = mock_alarms
        assert host.active_alarms == mock_alarms

    @pytest.mark.asyncio
    async def test_clear_alarm_emits_event(self):
        host = _AlarmHost()
        mock_event = MagicMock()
        host._alarm_manager.clear_alarm.return_value = mock_event

        await host.clear_alarm("OVER_TEMP")

        host._alarm_manager.clear_alarm.assert_called_once_with("OVER_TEMP")
        host._emitter.emit_await.assert_awaited_once()
        call_args = host._emitter.emit_await.call_args
        assert call_args[0][0] == EVENT_ALARM_CLEARED

    @pytest.mark.asyncio
    async def test_clear_alarm_no_event_if_not_found(self):
        host = _AlarmHost()
        host._alarm_manager.clear_alarm.return_value = None

        await host.clear_alarm("NONEXISTENT")

        host._emitter.emit_await.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_evaluate_alarm_triggered(self):
        host = _AlarmHost()
        mock_evaluator = MagicMock()
        mock_evaluator.point_name = "temperature"
        mock_evaluator.evaluate.return_value = [MagicMock()]

        trigger_event = MagicMock()
        trigger_event.event_type = AlarmEventType.TRIGGERED
        host._alarm_manager.update.return_value = [trigger_event]
        host._alarm_evaluators = [mock_evaluator]

        await host._evaluate_alarm({"temperature": 95.0})

        host._emitter.emit_await.assert_awaited_once()
        call_args = host._emitter.emit_await.call_args
        assert call_args[0][0] == EVENT_ALARM_TRIGGERED

    @pytest.mark.asyncio
    async def test_evaluate_alarm_cleared(self):
        host = _AlarmHost()
        mock_evaluator = MagicMock()
        mock_evaluator.point_name = "temperature"
        mock_evaluator.evaluate.return_value = [MagicMock()]

        clear_event = MagicMock()
        clear_event.event_type = AlarmEventType.CLEARED
        host._alarm_manager.update.return_value = [clear_event]
        host._alarm_evaluators = [mock_evaluator]

        await host._evaluate_alarm({"temperature": 30.0})

        call_args = host._emitter.emit_await.call_args
        assert call_args[0][0] == EVENT_ALARM_CLEARED

    @pytest.mark.asyncio
    async def test_evaluate_alarm_skips_missing_point(self):
        host = _AlarmHost()
        mock_evaluator = MagicMock()
        mock_evaluator.point_name = "temperature"
        host._alarm_evaluators = [mock_evaluator]

        await host._evaluate_alarm({"power": 100})  # no temperature key

        mock_evaluator.evaluate.assert_not_called()


# ======================== WriteMixin ========================


class _WriteHost(WriteMixin):
    """Minimal host for WriteMixin testing."""

    ACTIONS: dict[str, str] = {"start": "_do_start", "stop": "_do_stop"}

    def __init__(self):
        self._write_points = {}
        self._writer = MagicMock()
        self._writer.write = AsyncMock()
        self._emitter = MagicMock()
        self._config = MagicMock()
        self._config.device_id = "test_device"

    async def _do_start(self):
        pass

    async def _do_stop(self):
        pass


class TestWriteMixin:
    @pytest.mark.asyncio
    async def test_write_success_emits_event(self):
        host = _WriteHost()
        mock_point = MagicMock()
        host._write_points["p_set"] = mock_point
        host._writer.write.return_value = WriteResult(
            status=WriteStatus.SUCCESS, point_name="p_set", value=100.0
        )

        result = await host.write("p_set", 100.0)

        assert result.status == WriteStatus.SUCCESS
        host._emitter.emit.assert_called_once()
        call_args = host._emitter.emit.call_args
        assert call_args[0][0] == EVENT_WRITE_COMPLETE

    @pytest.mark.asyncio
    async def test_write_failure_emits_error(self):
        host = _WriteHost()
        mock_point = MagicMock()
        host._write_points["p_set"] = mock_point
        host._writer.write.return_value = WriteResult(
            status=WriteStatus.WRITE_FAILED, point_name="p_set", value=100.0, error_message="timeout"
        )

        result = await host.write("p_set", 100.0)

        assert result.status == WriteStatus.WRITE_FAILED
        host._emitter.emit.assert_called_once()
        call_args = host._emitter.emit.call_args
        assert call_args[0][0] == EVENT_WRITE_ERROR

    @pytest.mark.asyncio
    async def test_write_nonexistent_point(self):
        host = _WriteHost()
        result = await host.write("nonexistent", 50.0)
        assert result.status == WriteStatus.VALIDATION_FAILED

    @pytest.mark.asyncio
    async def test_execute_action_success(self):
        host = _WriteHost()
        result = await host.execute_action("start")
        assert result.status == WriteStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_execute_action_unsupported(self):
        host = _WriteHost()
        result = await host.execute_action("restart")
        assert result.status == WriteStatus.VALIDATION_FAILED
        assert "not supported" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_action_method_not_found(self):
        host = _WriteHost()
        host.ACTIONS = {"broken": "nonexistent_method"}
        result = await host.execute_action("broken")
        assert result.status == WriteStatus.VALIDATION_FAILED
        assert "not found" in result.error_message

    def test_available_actions(self):
        host = _WriteHost()
        assert sorted(host.available_actions) == ["start", "stop"]


class TestMixinMRO:
    def test_async_modbus_device_inherits_mixins(self):
        from csp_lib.equipment.device.base import AsyncModbusDevice

        assert issubclass(AsyncModbusDevice, AlarmMixin)
        assert issubclass(AsyncModbusDevice, WriteMixin)

    def test_mro_order(self):
        from csp_lib.equipment.device.base import AsyncModbusDevice

        mro = AsyncModbusDevice.__mro__
        alarm_idx = mro.index(AlarmMixin)
        write_idx = mro.index(WriteMixin)
        assert alarm_idx < write_idx  # AlarmMixin before WriteMixin
