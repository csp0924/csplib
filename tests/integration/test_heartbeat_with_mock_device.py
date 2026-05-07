"""Pipeline E：HeartbeatService + MockDeviceProtocol（DeviceProtocol 鬆綁驗證）

驗證 HeartbeatService 不依賴 AsyncModbusDevice，只要設備結構性符合
DeviceProtocol 即可運作。

注意：本檔刻意 **不 import** ``AsyncModbusDevice``。
"""

from __future__ import annotations

import asyncio

from csp_lib.integration.heartbeat import HeartbeatService
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import HeartbeatMapping


class TestHeartbeatServiceAcceptsMockDeviceProtocol:
    async def test_heartbeat_writes_to_mock_device_by_id(self, mock_device_protocol) -> None:
        """device_id 路徑：HeartbeatService 對 MockDevice 寫入 heartbeat 點位。"""
        reg = DeviceRegistry()
        reg.register(mock_device_protocol, traits=["pcs"])

        mapping = HeartbeatMapping(
            point_name="heartbeat",
            device_id=mock_device_protocol.device_id,
        )
        svc = HeartbeatService(reg, [mapping], interval=0.05)

        await svc.start()
        try:
            await asyncio.sleep(0.12)  # 至少 1~2 個 tick
        finally:
            await svc.stop()

        assert mock_device_protocol.write.await_count >= 1
        # 第一次 toggle 為 1
        mock_device_protocol.write.assert_any_call("heartbeat", 1)

    async def test_heartbeat_writes_to_mock_device_by_trait(self, make_mock_device_protocol) -> None:
        """trait 路徑：HeartbeatService 對所有 trait='pcs' 的 MockDevice 寫入。"""
        dev1 = make_mock_device_protocol("mock_pcs_1")
        dev2 = make_mock_device_protocol("mock_pcs_2")
        reg = DeviceRegistry()
        reg.register(dev1, traits=["pcs"])
        reg.register(dev2, traits=["pcs"])

        mapping = HeartbeatMapping(point_name="heartbeat", trait="pcs")
        svc = HeartbeatService(reg, [mapping], interval=0.05)

        await svc.start()
        try:
            await asyncio.sleep(0.12)
        finally:
            await svc.stop()

        assert dev1.write.await_count >= 1
        assert dev2.write.await_count >= 1
