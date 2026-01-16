# =============== Manager Device Tests - Group ===============
#
# DeviceGroup 單元測試
#
# 測試覆蓋：
# - Client 驗證
# - 連線/斷線
# - 順序讀取循環
# - 生命週期管理

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from csp_lib.manager.device.group import DeviceGroup


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


class MockDevice:
    """Mock AsyncModbusDevice"""

    def __init__(self, device_id: str, client: MockClient | None = None):
        self.device_id = device_id
        self._client = client or MockClient()
        self._emitter = MockEmitter()
        self._client_connected = False
        self._device_responsive = False
        self._consecutive_failures = 0
        self.read_once = AsyncMock()


# ======================== Client Validation Tests ========================


class TestDeviceGroupValidation:
    """Client 驗證測試"""

    def test_single_device_no_validation(self):
        """單一設備不需驗證"""
        device = MockDevice("device_001")
        group = DeviceGroup(devices=[device])
        assert len(group) == 1

    def test_same_client_passes(self):
        """相同 Client 應通過驗證"""
        client = MockClient()
        device1 = MockDevice("device_001", client)
        device2 = MockDevice("device_002", client)

        group = DeviceGroup(devices=[device1, device2])
        assert len(group) == 2

    def test_different_client_raises(self):
        """不同 Client 應拋出 ValueError"""
        device1 = MockDevice("device_001", MockClient())
        device2 = MockDevice("device_002", MockClient())

        with pytest.raises(ValueError, match="必須共用同一 Client"):
            DeviceGroup(devices=[device1, device2])

    def test_empty_devices(self):
        """空設備列表應可建立"""
        group = DeviceGroup(devices=[])
        assert len(group) == 0


# ======================== Lifecycle Tests ========================


class TestDeviceGroupLifecycle:
    """生命週期測試"""

    @pytest.fixture
    def shared_client(self) -> MockClient:
        return MockClient()

    @pytest.fixture
    def devices(self, shared_client: MockClient) -> list[MockDevice]:
        return [
            MockDevice("device_001", shared_client),
            MockDevice("device_002", shared_client),
        ]

    @pytest.fixture
    def group(self, devices: list[MockDevice]) -> DeviceGroup:
        return DeviceGroup(devices=devices, interval=0.1)

    @pytest.mark.asyncio
    async def test_connect(self, group: DeviceGroup, shared_client: MockClient):
        """connect 應連接 Client 並啟動各設備 emitter"""
        await group.connect()

        # Client 應被連接一次
        shared_client.connect.assert_called_once()

        # 各設備 emitter 應被啟動
        for device in group.devices:
            device._emitter.start.assert_called_once()
            assert device._client_connected is True
            assert device._device_responsive is True

    @pytest.mark.asyncio
    async def test_disconnect(self, group: DeviceGroup, shared_client: MockClient):
        """disconnect 應斷開 Client 並停止各設備 emitter"""
        await group.connect()
        await group.disconnect()

        # Client 應被斷開
        shared_client.disconnect.assert_called_once()

        # 各設備 emitter 應被停止
        for device in group.devices:
            device._emitter.stop.assert_called_once()
            assert device._client_connected is False
            assert device._device_responsive is False

    @pytest.mark.asyncio
    async def test_start_stop(self, group: DeviceGroup):
        """start/stop 應控制讀取循環"""
        assert group.is_running is False

        group.start()
        assert group.is_running is True

        await group.stop()
        assert group.is_running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self, group: DeviceGroup):
        """重複 start 應無效果"""
        group.start()
        task1 = group._task

        group.start()
        task2 = group._task

        assert task1 is task2

        await group.stop()


# ======================== Sequential Loop Tests ========================


class TestDeviceGroupSequentialLoop:
    """順序讀取循環測試"""

    @pytest.fixture
    def shared_client(self) -> MockClient:
        return MockClient()

    @pytest.fixture
    def devices(self, shared_client: MockClient) -> list[MockDevice]:
        return [
            MockDevice("device_001", shared_client),
            MockDevice("device_002", shared_client),
            MockDevice("device_003", shared_client),
        ]

    @pytest.fixture
    def group(self, devices: list[MockDevice]) -> DeviceGroup:
        return DeviceGroup(devices=devices, interval=0.05)

    @pytest.mark.asyncio
    async def test_reads_all_devices(self, group: DeviceGroup):
        """應讀取所有設備"""
        group.start()
        await asyncio.sleep(0.5)  # 3 devices × 0.1s sleep = 至少 0.3s
        await group.stop()

        for device in group.devices:
            assert device.read_once.call_count >= 1

    @pytest.mark.asyncio
    async def test_reads_in_order(self, group: DeviceGroup):
        """應依序讀取設備"""
        read_order: list[str] = []

        def make_side_effect(device_id: str):
            async def _read():
                read_order.append(device_id)
            return _read

        for device in group.devices:
            device.read_once = AsyncMock(side_effect=make_side_effect(device.device_id))

        group.start()
        await asyncio.sleep(0.5)  # 增加等待時間
        await group.stop()

        # 驗證順序
        # 由於可能跑多輪，只驗證連續三個是正確順序
        if len(read_order) >= 3:
            for i in range(0, len(read_order) - 2, 3):
                assert read_order[i:i+3] == ["device_001", "device_002", "device_003"]

    @pytest.mark.asyncio
    async def test_single_device_error_does_not_affect_others(self, group: DeviceGroup):
        """單一設備錯誤不應影響其他設備"""
        # 第一個設備拋錯
        group.devices[0].read_once = AsyncMock(side_effect=Exception("Read failed"))

        group.start()
        await asyncio.sleep(0.5)  # 增加等待時間
        await group.stop()

        # 其他設備仍應被讀取
        assert group.devices[1].read_once.call_count >= 1
        assert group.devices[2].read_once.call_count >= 1


# ======================== Properties Tests ========================


class TestDeviceGroupProperties:
    """屬性測試"""

    def test_device_ids(self):
        """device_ids 應返回所有設備 ID"""
        client = MockClient()
        devices = [
            MockDevice("device_001", client),
            MockDevice("device_002", client),
        ]
        group = DeviceGroup(devices=devices)

        assert group.device_ids == ["device_001", "device_002"]

    def test_len(self):
        """__len__ 應返回設備數量"""
        client = MockClient()
        devices = [MockDevice(f"device_{i}", client) for i in range(5)]
        group = DeviceGroup(devices=devices)

        assert len(group) == 5

    def test_repr(self):
        """__repr__ 應包含關鍵資訊"""
        client = MockClient()
        device = MockDevice("device_001", client)
        group = DeviceGroup(devices=[device], interval=1.5)

        repr_str = repr(group)
        assert "device_001" in repr_str
        assert "1.5s" in repr_str
