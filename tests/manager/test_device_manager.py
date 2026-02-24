# =============== Manager Device Tests - Manager ===============
#
# DeviceManager 單元測試
#
# 測試覆蓋：
# - 設備註冊
# - 群組註冊
# - 生命週期管理
# - Context Manager

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from csp_lib.manager.device import DeviceGroup, DeviceManager


class MockClient:
    """Mock Modbus Client"""

    def __init__(self):
        self.connect = AsyncMock()
        self.disconnect = AsyncMock()


class MockEmitter:
    """Mock DeviceEventEmitter"""

    def __init__(self):
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.emit = lambda event, payload: None  # 非阻塞發送
        self.emit_await = AsyncMock()  # 阻塞發送


class MockDevice:
    """Mock AsyncModbusDevice"""

    def __init__(self, device_id: str, client: MockClient | None = None):
        self.device_id = device_id
        self._client = client or MockClient()
        self._emitter = MockEmitter()
        self._client_connected = False
        self._device_responsive = False
        self._consecutive_failures = 0
        self.connect = AsyncMock()
        self.disconnect = AsyncMock()
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.read_once = AsyncMock()


# ======================== Registration Tests ========================


class TestDeviceManagerRegistration:
    """設備註冊測試"""

    def test_register_standalone(self):
        """register 應註冊獨立設備"""
        manager = DeviceManager()
        device = MockDevice("device_001")

        manager.register(device)

        assert manager.standalone_count == 1
        assert device in manager.all_devices

    def test_register_multiple_standalone(self):
        """應能註冊多個獨立設備"""
        manager = DeviceManager()
        devices = [MockDevice(f"device_{i}") for i in range(3)]

        for device in devices:
            manager.register(device)

        assert manager.standalone_count == 3

    def test_register_group(self):
        """register_group 應註冊設備群組"""
        manager = DeviceManager()
        client = MockClient()
        devices = [
            MockDevice("device_001", client),
            MockDevice("device_002", client),
        ]

        manager.register_group(devices, interval=1.0)

        assert manager.group_count == 1
        assert manager.standalone_count == 0
        assert len(manager.all_devices) == 2

    def test_register_multiple_groups(self):
        """應能註冊多個群組"""
        manager = DeviceManager()

        client1 = MockClient()
        group1 = [MockDevice("d1", client1), MockDevice("d2", client1)]

        client2 = MockClient()
        group2 = [MockDevice("d3", client2), MockDevice("d4", client2)]

        manager.register_group(group1)
        manager.register_group(group2)

        assert manager.group_count == 2
        assert len(manager.all_devices) == 4

    def test_register_group_allows_different_clients(self):
        """不同 Client 應可建立群組（不再驗證）"""
        manager = DeviceManager()
        devices = [
            MockDevice("device_001", MockClient()),
            MockDevice("device_002", MockClient()),
        ]

        # 不應拋出異常
        manager.register_group(devices)
        assert manager.group_count == 1


# ======================== Lifecycle Tests ========================


class TestDeviceManagerLifecycle:
    """生命週期測試"""

    @pytest.fixture
    def manager(self) -> DeviceManager:
        return DeviceManager()

    @pytest.mark.asyncio
    async def test_start_standalone(self, manager: DeviceManager):
        """start 應啟動獨立設備"""
        device = MockDevice("device_001")
        manager.register(device)

        await manager.start()

        device.connect.assert_called_once()
        device.start.assert_called_once()
        assert manager.is_running is True

        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_standalone(self, manager: DeviceManager):
        """stop 應停止獨立設備"""
        device = MockDevice("device_001")
        manager.register(device)

        await manager.start()
        await manager.stop()

        device.stop.assert_called_once()
        device.disconnect.assert_called_once()
        assert manager.is_running is False

    @pytest.mark.asyncio
    async def test_start_group(self, manager: DeviceManager):
        """start 應啟動群組設備"""
        client = MockClient()
        devices = [MockDevice("d1", client), MockDevice("d2", client)]
        manager.register_group(devices, interval=0.1)

        await manager.start()

        # 各設備的 connect 應被呼叫
        for device in devices:
            device.connect.assert_called_once()

        # 群組應在運行
        assert manager.groups[0].is_running is True

        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_group(self, manager: DeviceManager):
        """stop 應停止群組設備"""
        client = MockClient()
        devices = [MockDevice("d1", client), MockDevice("d2", client)]
        manager.register_group(devices, interval=0.1)

        await manager.start()
        await manager.stop()

        # 各設備的 disconnect 應被呼叫
        for device in devices:
            device.disconnect.assert_called_once()

        # 群組應停止
        assert manager.groups[0].is_running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self, manager: DeviceManager):
        """重複 start 應無效果"""
        device = MockDevice("device_001")
        manager.register(device)

        await manager.start()
        await manager.start()  # 第二次

        device.connect.assert_called_once()  # 仍只呼叫一次

        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, manager: DeviceManager):
        """重複 stop 應無效果"""
        device = MockDevice("device_001")
        manager.register(device)

        await manager.start()
        await manager.stop()
        await manager.stop()  # 第二次

        device.disconnect.assert_called_once()


# ======================== Context Manager Tests ========================


class TestDeviceManagerContextManager:
    """Context Manager 測試"""

    @pytest.mark.asyncio
    async def test_async_with(self):
        """async with 應正確管理生命週期"""
        manager = DeviceManager()
        device = MockDevice("device_001")
        manager.register(device)

        async with manager:
            device.connect.assert_called_once()
            device.start.assert_called_once()
            assert manager.is_running is True

        device.stop.assert_called_once()
        device.disconnect.assert_called_once()
        assert manager.is_running is False

    @pytest.mark.asyncio
    async def test_async_with_mixed(self):
        """async with 應處理混合設備"""
        manager = DeviceManager()

        # 獨立設備
        standalone = MockDevice("standalone")
        manager.register(standalone)

        # 群組設備
        client = MockClient()
        group_devices = [MockDevice("g1", client), MockDevice("g2", client)]
        manager.register_group(group_devices, interval=0.1)

        async with manager:
            assert manager.is_running is True
            assert manager.standalone_count == 1
            assert manager.group_count == 1

        assert manager.is_running is False


# ======================== Properties Tests ========================


class TestDeviceManagerProperties:
    """屬性測試"""

    def test_all_devices(self):
        """all_devices 應返回所有設備"""
        manager = DeviceManager()

        standalone = MockDevice("standalone")
        manager.register(standalone)

        client = MockClient()
        group_devices = [MockDevice("g1", client), MockDevice("g2", client)]
        manager.register_group(group_devices)

        all_devices = manager.all_devices
        assert len(all_devices) == 3
        assert standalone in all_devices
        assert group_devices[0] in all_devices
        assert group_devices[1] in all_devices

    def test_groups(self):
        """groups 應返回所有群組"""
        manager = DeviceManager()

        client = MockClient()
        devices = [MockDevice("d1", client), MockDevice("d2", client)]
        manager.register_group(devices)

        assert len(manager.groups) == 1
        assert isinstance(manager.groups[0], DeviceGroup)

    def test_repr(self):
        """__repr__ 應包含關鍵資訊"""
        manager = DeviceManager()
        manager.register(MockDevice("d1"))

        repr_str = repr(manager)
        assert "standalone=1" in repr_str
        assert "groups=0" in repr_str
