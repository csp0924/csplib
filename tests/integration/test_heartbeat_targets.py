# =============== v0.8.1 HeartbeatTarget Tests ===============
#
# 涵蓋 Feature spec AC4：新 Protocol-driven write target API。
#
# 測試對象：
#   - HeartbeatTarget Protocol（runtime_checkable 結構子型別）
#   - DeviceHeartbeatTarget（integration 層預設實作）
#   - GatewayRegisterHeartbeatTarget（modbus_gateway 層實作）
#
# 驗證要點：
#   1. write() 正確委派給底層物件（device / gateway）
#   2. DeviceError 被吞掉，不 raise，不中斷迴圈（fire-and-forget 語義）
#   3. identity 格式符合規格，供 value-generator key 使用
#   4. Protocol 結構檢查對兩個內建 impl 均成立

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.core.errors import DeviceError
from csp_lib.integration.heartbeat_targets import (
    DeviceHeartbeatTarget,
    HeartbeatTarget,
)
from csp_lib.modbus_gateway.heartbeat_target import GatewayRegisterHeartbeatTarget

# ─────────────── DeviceHeartbeatTarget ───────────────


class TestDeviceHeartbeatTarget:
    """以 AsyncModbusDevice 點位為心跳目標的 target 實作"""

    def _make_device(self, device_id: str = "pcs1") -> MagicMock:
        """建立最小 mock device：只需 device_id property 與 async write"""
        dev = MagicMock()
        type(dev).device_id = PropertyMock(return_value=device_id)
        dev.write = AsyncMock()
        return dev

    async def test_write_calls_device_write(self):
        """AC4：write(value) 應呼叫 device.write(point_name, value)"""
        dev = self._make_device("pcs1")
        target = DeviceHeartbeatTarget(dev, point_name="heartbeat")
        await target.write(7)
        dev.write.assert_awaited_once_with("heartbeat", 7)

    async def test_write_swallows_device_error(self):
        """AC4：write 遇 DeviceError 不 raise，只 log warning（fire-and-forget）"""
        dev = self._make_device("pcs1")
        dev.write = AsyncMock(side_effect=DeviceError("pcs1", "write failed"))
        target = DeviceHeartbeatTarget(dev, point_name="heartbeat")

        # 應不 raise
        await target.write(1)
        dev.write.assert_awaited_once_with("heartbeat", 1)

    async def test_write_does_not_swallow_other_exceptions(self):
        """AC4：write 對非 DeviceError 應透傳（ex: 程式錯誤應暴露）"""
        dev = self._make_device("pcs1")
        dev.write = AsyncMock(side_effect=RuntimeError("unexpected"))
        target = DeviceHeartbeatTarget(dev, point_name="heartbeat")

        with pytest.raises(RuntimeError, match="unexpected"):
            await target.write(1)

    def test_identity_format(self):
        """AC4：identity 應為 'device:{device_id}:{point_name}'"""
        dev = self._make_device("pcs_01")
        target = DeviceHeartbeatTarget(dev, point_name="hb")
        assert target.identity == "device:pcs_01:hb"

    def test_different_point_names_produce_different_identities(self):
        """AC4：同一台設備不同點位應有不同 identity（generator key 隔離）"""
        dev = self._make_device("pcs_01")
        t1 = DeviceHeartbeatTarget(dev, point_name="hb_a")
        t2 = DeviceHeartbeatTarget(dev, point_name="hb_b")
        assert t1.identity != t2.identity

    def test_satisfies_heartbeat_target_protocol(self):
        """AC4：DeviceHeartbeatTarget 應被識別為 HeartbeatTarget（runtime_checkable）"""
        dev = self._make_device("pcs1")
        target = DeviceHeartbeatTarget(dev, point_name="hb")
        assert isinstance(target, HeartbeatTarget)


# ─────────────── GatewayRegisterHeartbeatTarget ───────────────


class TestGatewayRegisterHeartbeatTarget:
    """以 ModbusGatewayServer register 為心跳目標的 target 實作"""

    def _make_gateway(self) -> MagicMock:
        """建立 mock gateway：只需 set_register 同步方法"""
        gw = MagicMock()
        gw.set_register = MagicMock()
        return gw

    async def test_write_calls_set_register(self):
        """AC4：write(value) 應呼叫 gateway.set_register(register_name, value)"""
        gw = self._make_gateway()
        target = GatewayRegisterHeartbeatTarget(gw, register_name="controller_heartbeat")
        await target.write(9)
        gw.set_register.assert_called_once_with("controller_heartbeat", 9)

    async def test_write_does_not_await_set_register(self):
        """AC4：set_register 為同步；write 不 await 底層呼叫"""
        gw = self._make_gateway()
        target = GatewayRegisterHeartbeatTarget(gw, register_name="hb")
        # 即使 set_register 非 AsyncMock，write 也應正常執行完
        await target.write(1)
        assert gw.set_register.call_count == 1

    def test_identity_format(self):
        """AC4：identity 應為 'gateway:{register_name}'"""
        gw = self._make_gateway()
        target = GatewayRegisterHeartbeatTarget(gw, register_name="controller_hb")
        assert target.identity == "gateway:controller_hb"

    def test_satisfies_heartbeat_target_protocol(self):
        """AC4：GatewayRegisterHeartbeatTarget 應被識別為 HeartbeatTarget"""
        gw = self._make_gateway()
        target = GatewayRegisterHeartbeatTarget(gw, register_name="hb")
        assert isinstance(target, HeartbeatTarget)


# ─────────────── 自訂 Target 結構子型別 ───────────────


class TestHeartbeatTargetProtocol:
    """任何實作 async write + identity property 的物件皆應滿足 Protocol"""

    def test_custom_target_satisfies_protocol(self):
        """AC4：使用者自訂 target 可直接餵給 HeartbeatService（duck typing）"""

        class MyTarget:
            async def write(self, value: int) -> None:
                pass

            @property
            def identity(self) -> str:
                return "custom:my"

        assert isinstance(MyTarget(), HeartbeatTarget)

    def test_incomplete_impl_does_not_satisfy_protocol(self):
        """AC4：缺 identity 的類別不滿足 Protocol"""

        class MissingIdentity:
            async def write(self, value: int) -> None:
                pass

        # runtime_checkable 會檢查 identity 存在
        assert not isinstance(MissingIdentity(), HeartbeatTarget)
