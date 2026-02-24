# =============== Manager Device Tests - Group ===============
#
# DeviceGroup 單元測試
#
# 測試覆蓋：
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
        self.emit = lambda event, payload: None
        self.emit_await = AsyncMock()


class MockDevice:
    """Mock AsyncModbusDevice"""

    def __init__(self, device_id: str, client: MockClient | None = None):
        self.device_id = device_id
        self._client = client or MockClient()
        self._emitter = MockEmitter()
        self._client_connected = False
        self._device_responsive = False
        self._consecutive_failures = 0
        self._should_attempt_read = True
        self.read_once = AsyncMock()

    @property
    def should_attempt_read(self) -> bool:
        return self._should_attempt_read


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
        await asyncio.sleep(0.3)
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
        await asyncio.sleep(0.3)
        await group.stop()

        # 驗證順序（連續三個應是正確順序）
        if len(read_order) >= 3:
            for i in range(0, len(read_order) - 2, 3):
                assert read_order[i : i + 3] == ["device_001", "device_002", "device_003"]

    @pytest.mark.asyncio
    async def test_single_device_error_does_not_affect_others(self, group: DeviceGroup):
        """單一設備錯誤不應影響其他設備"""
        # 第一個設備拋錯
        group.devices[0].read_once = AsyncMock(side_effect=Exception("Read failed"))

        group.start()
        await asyncio.sleep(0.3)
        await group.stop()

        # 其他設備仍應被讀取
        assert group.devices[1].read_once.call_count >= 1
        assert group.devices[2].read_once.call_count >= 1


# ======================== Skip Unresponsive Tests ========================


class TestDeviceGroupSkipUnresponsive:
    """跳過無回應設備測試"""

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
    async def test_skip_unresponsive_device(self, group: DeviceGroup):
        """should_attempt_read 為 False 的設備應被跳過"""
        # 將第二個設備標記為不應嘗試讀取
        group.devices[1]._should_attempt_read = False

        group.start()
        await asyncio.sleep(0.3)
        await group.stop()

        # 第一和第三個設備應被讀取
        assert group.devices[0].read_once.call_count >= 1
        assert group.devices[2].read_once.call_count >= 1
        # 第二個設備不應被讀取
        assert group.devices[1].read_once.call_count == 0

    @pytest.mark.asyncio
    async def test_all_unresponsive_skips_all(self, group: DeviceGroup):
        """所有設備都無回應時應全部跳過"""
        for device in group.devices:
            device._should_attempt_read = False

        group.start()
        await asyncio.sleep(0.3)
        await group.stop()

        for device in group.devices:
            assert device.read_once.call_count == 0

    @pytest.mark.asyncio
    async def test_resume_after_becoming_responsive(self, group: DeviceGroup):
        """設備恢復 should_attempt_read 後應重新被讀取"""
        # 初始：第二個設備不應嘗試讀取
        group.devices[1]._should_attempt_read = False

        group.start()
        await asyncio.sleep(0.15)

        # 確認被跳過
        assert group.devices[1].read_once.call_count == 0

        # 恢復
        group.devices[1]._should_attempt_read = True
        await asyncio.sleep(0.15)
        await group.stop()

        # 恢復後應被讀取
        assert group.devices[1].read_once.call_count >= 1

    @pytest.mark.asyncio
    async def test_other_devices_not_delayed_by_skip(self, group: DeviceGroup):
        """跳過設備不應延遲其他設備的讀取"""
        read_order: list[str] = []

        def make_side_effect(device_id: str):
            async def _read():
                read_order.append(device_id)

            return _read

        for device in group.devices:
            device.read_once = AsyncMock(side_effect=make_side_effect(device.device_id))

        # 跳過中間設備
        group.devices[1]._should_attempt_read = False

        group.start()
        await asyncio.sleep(0.3)
        await group.stop()

        # 讀取順序應只有 device_001 和 device_003
        assert "device_002" not in read_order
        assert "device_001" in read_order
        assert "device_003" in read_order


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

    def test_empty_devices(self):
        """空設備列表應可建立"""
        group = DeviceGroup(devices=[])
        assert len(group) == 0

    def test_different_clients_allowed(self):
        """不同 Client 應可建立（不再驗證）"""
        device1 = MockDevice("device_001", MockClient())
        device2 = MockDevice("device_002", MockClient())

        # 不應拋出異常
        group = DeviceGroup(devices=[device1, device2])
        assert len(group) == 2
