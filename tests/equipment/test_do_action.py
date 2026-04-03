# =============== Equipment Device Tests - DO Action ===============
#
# DO 動作系統測試
#
# 測試覆蓋：
# - DOMode enum
# - DOActionConfig 驗證與不可變性
# - Actionable Protocol
# - WriteMixin.configure_do_actions
# - WriteMixin.execute_do_action (SUSTAINED / TOGGLE / PULSE)
# - WriteMixin.cancel_pending_pulses
# - AsyncModbusDevice.stop() 呼叫 cancel_pending_pulses

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.device.action import Actionable, DOActionConfig, DOMode
from csp_lib.equipment.device.base import AsyncModbusDevice
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.equipment.transport import WriteStatus
from csp_lib.modbus import UInt16

# ======================== Fixtures ========================


@pytest.fixture
def mock_client() -> AsyncMock:
    """Mock Modbus client"""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.read_holding_registers = AsyncMock(return_value=[0])
    client.write_registers = AsyncMock()
    return client


@pytest.fixture
def device_config() -> DeviceConfig:
    return DeviceConfig(
        device_id="do_test_device",
        unit_id=1,
        address_offset=0,
        read_interval=0.1,
        disconnect_threshold=3,
    )


@pytest.fixture
def write_points() -> list[WritePoint]:
    return [
        WritePoint(name="do_trip", address=200, data_type=UInt16()),
        WritePoint(name="do_reset", address=201, data_type=UInt16()),
        WritePoint(name="do_contactor", address=202, data_type=UInt16()),
    ]


@pytest.fixture
def device(mock_client, device_config, write_points) -> AsyncModbusDevice:
    """AsyncModbusDevice with write points for DO action testing."""
    return AsyncModbusDevice(
        config=device_config,
        client=mock_client,
        always_points=[ReadPoint(name="status", address=100, data_type=UInt16())],
        write_points=write_points,
    )


@pytest.fixture
def sustained_config() -> DOActionConfig:
    return DOActionConfig(point_name="do_trip", label="trip", mode=DOMode.SUSTAINED)


@pytest.fixture
def toggle_config() -> DOActionConfig:
    return DOActionConfig(point_name="do_contactor", label="contactor", mode=DOMode.TOGGLE)


@pytest.fixture
def pulse_config() -> DOActionConfig:
    return DOActionConfig(point_name="do_reset", label="reset", mode=DOMode.PULSE, pulse_duration=0.05)


# ======================== DOMode Enum ========================


class TestDOMode:
    def test_values(self):
        assert DOMode.PULSE == "pulse"
        assert DOMode.SUSTAINED == "sustained"
        assert DOMode.TOGGLE == "toggle"

    def test_is_str_enum(self):
        assert isinstance(DOMode.PULSE, str)


# ======================== DOActionConfig ========================


class TestDOActionConfig:
    def test_basic_creation(self):
        cfg = DOActionConfig(point_name="do_trip", label="trip")
        assert cfg.point_name == "do_trip"
        assert cfg.label == "trip"
        assert cfg.mode == DOMode.SUSTAINED
        assert cfg.pulse_duration == 0.5
        assert cfg.on_value == 1
        assert cfg.off_value == 0

    def test_custom_values(self):
        cfg = DOActionConfig(
            point_name="do_x",
            label="x",
            mode=DOMode.PULSE,
            pulse_duration=2.0,
            on_value=100,
            off_value=50,
        )
        assert cfg.mode == DOMode.PULSE
        assert cfg.pulse_duration == 2.0
        assert cfg.on_value == 100
        assert cfg.off_value == 50

    def test_pulse_duration_zero_raises_for_pulse_mode(self):
        with pytest.raises(ValueError, match="pulse_duration must be positive"):
            DOActionConfig(point_name="p", label="l", mode=DOMode.PULSE, pulse_duration=0)

    def test_pulse_duration_negative_raises_for_pulse_mode(self):
        with pytest.raises(ValueError, match="pulse_duration must be positive"):
            DOActionConfig(point_name="p", label="l", mode=DOMode.PULSE, pulse_duration=-1.0)

    def test_pulse_duration_zero_ok_for_non_pulse_modes(self):
        """非 PULSE 模式不驗證 pulse_duration"""
        cfg = DOActionConfig(point_name="p", label="l", mode=DOMode.SUSTAINED, pulse_duration=0)
        assert cfg.pulse_duration == 0
        cfg2 = DOActionConfig(point_name="p", label="l", mode=DOMode.TOGGLE, pulse_duration=-1.0)
        assert cfg2.pulse_duration == -1.0

    def test_frozen(self):
        cfg = DOActionConfig(point_name="p", label="l")
        with pytest.raises(AttributeError):
            cfg.label = "new"  # type: ignore[misc]

    def test_slots(self):
        cfg = DOActionConfig(point_name="p", label="l")
        assert hasattr(cfg, "__slots__")


# ======================== Actionable Protocol ========================


class TestActionableProtocol:
    def test_async_modbus_device_satisfies_protocol(self, device):
        assert isinstance(device, Actionable)

    def test_non_conforming_object_fails(self):
        assert not isinstance(object(), Actionable)


# ======================== configure_do_actions ========================


class TestConfigureDOActions:
    def test_configure_single(self, device, sustained_config):
        device.configure_do_actions([sustained_config])
        assert len(device.available_do_actions) == 1
        assert device.available_do_actions[0].label == "trip"

    def test_configure_multiple(self, device, sustained_config, toggle_config, pulse_config):
        device.configure_do_actions([sustained_config, toggle_config, pulse_config])
        labels = {c.label for c in device.available_do_actions}
        assert labels == {"trip", "contactor", "reset"}

    def test_duplicate_labels_raise(self, device):
        configs = [
            DOActionConfig(point_name="do_trip", label="dup"),
            DOActionConfig(point_name="do_reset", label="dup"),
        ]
        with pytest.raises(ValueError, match="Duplicate DO action labels"):
            device.configure_do_actions(configs)

    def test_reconfigure_replaces_actions(self, device, sustained_config, toggle_config):
        device.configure_do_actions([sustained_config])
        assert len(device.available_do_actions) == 1

        device.configure_do_actions([toggle_config])
        assert len(device.available_do_actions) == 1
        assert device.available_do_actions[0].label == "contactor"

    async def test_reconfigure_cancels_old_pulse_tasks(self, device, pulse_config, sustained_config):
        """Reconfiguring DO actions should cancel any pending pulse tasks."""
        device.configure_do_actions([pulse_config])
        # Execute a pulse to create a pending task
        await device.execute_do_action("reset")
        assert len(device._pulse_tasks) == 1

        # Reconfigure should cancel the pulse task
        device.configure_do_actions([sustained_config])
        assert len(device._pulse_tasks) == 0

    def test_empty_config(self, device):
        device.configure_do_actions([])
        assert device.available_do_actions == []


# ======================== execute_do_action — SUSTAINED ========================


class TestExecuteDOActionSustained:
    async def test_sustained_on(self, device, sustained_config):
        device.configure_do_actions([sustained_config])
        result = await device.execute_do_action("trip")
        assert result.status == WriteStatus.SUCCESS
        assert result.point_name == "do_trip"
        assert result.value == 1

    async def test_sustained_off(self, device, sustained_config):
        device.configure_do_actions([sustained_config])
        result = await device.execute_do_action("trip", turn_off=True)
        assert result.status == WriteStatus.SUCCESS
        assert result.point_name == "do_trip"
        assert result.value == 0

    async def test_sustained_custom_values(self, device):
        cfg = DOActionConfig(
            point_name="do_trip",
            label="trip",
            mode=DOMode.SUSTAINED,
            on_value=99,
            off_value=11,
        )
        device.configure_do_actions([cfg])

        result_on = await device.execute_do_action("trip")
        assert result_on.value == 99

        result_off = await device.execute_do_action("trip", turn_off=True)
        assert result_off.value == 11


# ======================== execute_do_action — TOGGLE ========================


class TestExecuteDOActionToggle:
    async def test_toggle_first_call_turns_on(self, device, toggle_config):
        """First toggle when no current value defaults to off_value, so it writes on_value."""
        device.configure_do_actions([toggle_config])
        result = await device.execute_do_action("contactor")
        assert result.status == WriteStatus.SUCCESS
        assert result.value == toggle_config.on_value

    async def test_toggle_from_on_to_off(self, device, toggle_config):
        """When current value is on_value, toggle should write off_value."""
        device.configure_do_actions([toggle_config])
        # Simulate the device already having on_value
        device._latest_values["do_contactor"] = toggle_config.on_value

        result = await device.execute_do_action("contactor")
        assert result.value == toggle_config.off_value

    async def test_toggle_from_off_to_on(self, device, toggle_config):
        """When current value is off_value, toggle should write on_value."""
        device.configure_do_actions([toggle_config])
        device._latest_values["do_contactor"] = toggle_config.off_value

        result = await device.execute_do_action("contactor")
        assert result.value == toggle_config.on_value

    async def test_toggle_ignores_turn_off_param(self, device, toggle_config):
        """turn_off parameter should be ignored; behaviour is always toggle."""
        device.configure_do_actions([toggle_config])
        device._latest_values["do_contactor"] = toggle_config.off_value

        # Even with turn_off=True, TOGGLE should still flip off->on
        result = await device.execute_do_action("contactor", turn_off=True)
        assert result.value == toggle_config.on_value

    async def test_toggle_unknown_current_treated_as_off(self, device, toggle_config):
        """If the current value is unknown (not in _latest_values), defaults to off_value, so toggles to on."""
        device.configure_do_actions([toggle_config])
        # Ensure no value exists
        device._latest_values.pop("do_contactor", None)
        result = await device.execute_do_action("contactor")
        assert result.value == toggle_config.on_value

    async def test_toggle_custom_on_off_values(self, device):
        cfg = DOActionConfig(
            point_name="do_contactor",
            label="contactor",
            mode=DOMode.TOGGLE,
            on_value=255,
            off_value=128,
        )
        device.configure_do_actions([cfg])
        device._latest_values["do_contactor"] = 128
        result = await device.execute_do_action("contactor")
        assert result.value == 255

        device._latest_values["do_contactor"] = 255
        result = await device.execute_do_action("contactor")
        assert result.value == 128


# ======================== execute_do_action — PULSE ========================


class TestExecuteDOActionPulse:
    async def test_pulse_writes_on_immediately(self, device, pulse_config):
        device.configure_do_actions([pulse_config])
        result = await device.execute_do_action("reset")
        assert result.status == WriteStatus.SUCCESS
        assert result.value == pulse_config.on_value

    async def test_pulse_writes_off_after_duration(self, device, pulse_config):
        """After pulse_duration, the off_value should be written automatically."""
        device.configure_do_actions([pulse_config])
        written_values: list[tuple[str, int]] = []
        original_write = device.write

        async def tracking_write(name, value, verify=False):
            written_values.append((name, value))
            return await original_write(name, value, verify=verify)

        device.write = tracking_write  # type: ignore[assignment]

        await device.execute_do_action("reset")

        # Wait for pulse to complete (duration is 0.05s)
        await asyncio.sleep(0.15)

        # The write should have been called twice: on then off
        assert len(written_values) >= 2
        assert written_values[0] == ("do_reset", pulse_config.on_value)
        assert written_values[1] == ("do_reset", pulse_config.off_value)

    async def test_pulse_task_self_cleans(self, device, pulse_config):
        """After pulse completes, the task should be removed from _pulse_tasks."""
        device.configure_do_actions([pulse_config])
        await device.execute_do_action("reset")
        assert len(device._pulse_tasks) == 1

        # Wait for pulse to complete
        await asyncio.sleep(0.15)
        assert len(device._pulse_tasks) == 0

    async def test_pulse_ignores_turn_off_param(self, device, pulse_config):
        """turn_off param should be ignored; PULSE always does on -> delay -> off."""
        device.configure_do_actions([pulse_config])
        result = await device.execute_do_action("reset", turn_off=True)
        # Should still write on_value first
        assert result.value == pulse_config.on_value

    async def test_multiple_pulses_create_multiple_tasks(self, device, pulse_config):
        device.configure_do_actions([pulse_config])
        await device.execute_do_action("reset")
        await device.execute_do_action("reset")
        assert len(device._pulse_tasks) == 2

        # Wait for all pulses to finish
        await asyncio.sleep(0.15)
        assert len(device._pulse_tasks) == 0


# ======================== execute_do_action — Errors ========================


class TestExecuteDOActionErrors:
    async def test_unknown_label_raises(self, device, sustained_config):
        device.configure_do_actions([sustained_config])
        with pytest.raises(ValueError, match="Unknown DO action: 'nonexistent'"):
            await device.execute_do_action("nonexistent")

    async def test_no_actions_configured_raises(self, device):
        with pytest.raises(ValueError, match="Unknown DO action"):
            await device.execute_do_action("anything")


# ======================== cancel_pending_pulses ========================


class TestCancelPendingPulses:
    async def test_cancel_no_tasks(self, device):
        """Calling cancel_pending_pulses with no tasks should not raise."""
        await device.cancel_pending_pulses()
        assert device._pulse_tasks == []

    async def test_cancel_pending_pulse_tasks(self, device, pulse_config):
        device.configure_do_actions([pulse_config])
        await device.execute_do_action("reset")
        await device.execute_do_action("reset")
        assert len(device._pulse_tasks) == 2

        await device.cancel_pending_pulses()
        assert device._pulse_tasks == []

    async def test_cancel_prevents_off_write(self, device, pulse_config):
        """Cancelling the pulse should prevent the off_value write."""
        device.configure_do_actions([pulse_config])
        written_values: list[tuple[str, int]] = []
        original_write = device.write

        async def tracking_write(name, value, verify=False):
            written_values.append((name, value))
            return await original_write(name, value, verify=verify)

        device.write = tracking_write  # type: ignore[assignment]

        await device.execute_do_action("reset")

        # Cancel immediately before pulse_duration elapses
        await device.cancel_pending_pulses()

        # Wait past the pulse duration
        await asyncio.sleep(0.1)

        # Only the on_value write should have happened
        assert len(written_values) == 1
        assert written_values[0] == ("do_reset", pulse_config.on_value)


# ======================== stop() calls cancel_pending_pulses ========================


class TestStopCancelsPulses:
    async def test_stop_cancels_pulse_tasks(self, device, pulse_config):
        """AsyncModbusDevice.stop() must call cancel_pending_pulses."""
        device.configure_do_actions([pulse_config])
        await device.execute_do_action("reset")
        assert len(device._pulse_tasks) == 1

        await device.stop()
        assert device._pulse_tasks == []
