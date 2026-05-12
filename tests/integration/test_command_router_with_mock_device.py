"""Pipeline E：CommandRouter + MockDeviceProtocol（DeviceProtocol 鬆綁驗證）

驗證 CommandRouter 不依賴 AsyncModbusDevice，只要設備結構性符合 DeviceProtocol
即可運作（PR #103/#109/#119 的鬆綁實際生效）。

注意：本檔刻意 **不 import** ``csp_lib.equipment.device.AsyncModbusDevice``，
也不 import 任何 modbus client，以便此測試在未安裝 ``[modbus]`` extra
的情境下仍可通過。
"""

from __future__ import annotations

from csp_lib.controller.core import Command
from csp_lib.integration.command_router import CommandRouter
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CommandMapping


class TestCommandRouterAcceptsMockDeviceProtocol:
    async def test_route_writes_to_mock_device(self, mock_device_protocol) -> None:
        """register MockDevice → CommandRouter.route(...) → MockDevice.write 被呼叫。"""
        reg = DeviceRegistry()
        reg.register(mock_device_protocol)

        mappings = [
            CommandMapping(
                command_field="p_target",
                point_name="p_set",
                device_id=mock_device_protocol.device_id,
            ),
            CommandMapping(
                command_field="q_target",
                point_name="q_set",
                device_id=mock_device_protocol.device_id,
            ),
        ]
        router = CommandRouter(reg, mappings)

        cmd = Command(p_target=100.0, q_target=50.0)
        await router.route(cmd)

        # 兩次寫入：p_set / q_set
        assert mock_device_protocol.write.await_count == 2
        call_args = {c.args for c in mock_device_protocol.write.await_args_list}
        assert ("p_set", 100.0) in call_args
        assert ("q_set", 50.0) in call_args

    async def test_try_write_single_returns_true_on_mock_device(self, mock_device_protocol) -> None:
        reg = DeviceRegistry()
        reg.register(mock_device_protocol)
        router = CommandRouter(reg, mappings=[])

        ok = await router.try_write_single(mock_device_protocol.device_id, "p_set", 75.0)

        assert ok is True
        mock_device_protocol.write.assert_awaited_once_with("p_set", 75.0)
        # desired-state 表也應該被更新
        snapshot = router.get_last_written(mock_device_protocol.device_id)
        assert snapshot == {"p_set": 75.0}

    async def test_route_skips_protected_mock_device(self, make_mock_device_protocol) -> None:
        """is_protected=True 時應跳過寫入，與 AsyncModbusDevice 行為一致。"""
        dev = make_mock_device_protocol("dev_protected", protected=True)
        reg = DeviceRegistry()
        reg.register(dev)

        mappings = [
            CommandMapping(command_field="p_target", point_name="p_set", device_id=dev.device_id),
        ]
        router = CommandRouter(reg, mappings)

        await router.route(Command(p_target=42.0))
        dev.write.assert_not_called()

    async def test_route_skips_unresponsive_mock_device(self, make_mock_device_protocol) -> None:
        dev = make_mock_device_protocol("dev_offline", responsive=False)
        reg = DeviceRegistry()
        reg.register(dev)

        mappings = [
            CommandMapping(command_field="p_target", point_name="p_set", device_id=dev.device_id),
        ]
        router = CommandRouter(reg, mappings)

        await router.route(Command(p_target=42.0))
        dev.write.assert_not_called()
