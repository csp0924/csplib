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
        # Wave 2b：group 模式改呼叫 public ensure_event_loop_started/stopped
        # 取代舊的 device._emitter.start/stop 私有存取。
        self.ensure_event_loop_started = AsyncMock()
        self.ensure_event_loop_stopped = AsyncMock()


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


# ======================== Type-loosening (DeviceProtocol) Tests ========================


class TestDeviceManagerAcceptsDeviceProtocol:
    """驗證 register / register_group 接受任何實作 DeviceProtocol 的設備（而非僅 AsyncModbusDevice）。

    註：DeviceManager 在 register/register_group 時會 fail-fast 檢查 lifecycle 能力
    （connect/start/stop/disconnect 或 group 的 connect/disconnect/read_once/_emitter），
    因為這些方法尚未納入 DeviceProtocol（追蹤 B-P2）。因此本節測試用
    ``mock_device_protocol_with_lifecycle`` fixture（補掛 lifecycle AsyncMock）。
    缺 lifecycle 之情境另見 ``TestDeviceManagerLifecycleFailFast``。
    """

    def test_register_accepts_mock_device_protocol(self, mock_device_protocol_with_lifecycle):
        """MockDeviceProtocol（非 AsyncModbusDevice）+ lifecycle 可被 register。"""
        manager = DeviceManager()
        manager.register(mock_device_protocol_with_lifecycle)

        assert manager.standalone_count == 1
        assert mock_device_protocol_with_lifecycle in manager.all_devices


class TestDeviceManagerLifecycleFailFast:
    """驗證 register/register_group 對缺 lifecycle 之裝置 fail-fast（PR#104 Copilot review）。"""

    def test_register_pure_protocol_without_lifecycle_raises(self, mock_device_protocol):
        """純 DeviceProtocol 實作（缺 connect/start/stop/disconnect）應在 register 時 raise。"""
        manager = DeviceManager()
        with pytest.raises(ValueError, match="lifecycle"):
            manager.register(mock_device_protocol)

    def test_register_partial_lifecycle_raises(self, mock_device_protocol):
        """僅補部分 lifecycle（缺 stop）仍應 raise。"""
        mock_device_protocol.connect = AsyncMock()
        mock_device_protocol.disconnect = AsyncMock()
        mock_device_protocol.start = AsyncMock()
        # 刻意不補 stop

        manager = DeviceManager()
        with pytest.raises(ValueError, match="stop"):
            manager.register(mock_device_protocol)

    def test_register_group_pure_protocol_raises(self, mock_device_protocol):
        """純 DeviceProtocol 實作（缺 read_once/ensure_event_loop_*）應在 register_group 時 raise。"""
        manager = DeviceManager()
        with pytest.raises(ValueError, match="lifecycle"):
            manager.register_group([mock_device_protocol])

    def test_register_group_missing_event_loop_helper_raises(self, make_mock_device_protocol):
        """補了 connect/disconnect/read_once 但缺 ensure_event_loop_started/stopped 仍應 raise。

        Wave 2b 後，group 模式不再私有存取 device._emitter.start/stop，改要求
        public ``ensure_event_loop_started`` / ``ensure_event_loop_stopped``。
        """
        device = make_mock_device_protocol("partial_group_device")
        device.connect = AsyncMock()
        device.disconnect = AsyncMock()
        # read_once 已由 MockDeviceProtocol 預設提供
        # 刻意不補 ensure_event_loop_started / ensure_event_loop_stopped

        manager = DeviceManager()
        with pytest.raises(ValueError, match="ensure_event_loop_started"):
            manager.register_group([device])


# ======================== Unregister (Standalone) Tests ========================


class TestDeviceManagerUnregister:
    """單一 standalone 設備 unregister 測試。

    注意：source code 的 ``unregister`` 回傳 ``bool``（不存在時 False，不 raise KeyError）。
    若未來改為 raise KeyError，此測試需同步調整。
    """

    async def test_unregister_nonexistent_returns_false(self):
        """不存在的 device_id 回傳 False（非 running）。"""
        manager = DeviceManager()
        result = await manager.unregister("nonexistent")
        assert result is False

    async def test_unregister_group_device_returns_false(self):
        """device 屬於某 group 時，unregister（單一）找不到，回傳 False。
        （呼叫者應改用 unregister_group）"""
        manager = DeviceManager()
        client = MockClient()
        devices = [MockDevice("g1", client), MockDevice("g2", client)]
        manager.register_group(devices)

        result = await manager.unregister("g1")
        assert result is False
        # group 應完整保留
        assert manager.group_count == 1
        assert len(manager.all_devices) == 2

    async def test_unregister_standalone_when_not_running(self):
        """未 running 時 unregister standalone 設備 → True、從清單移除、不呼叫 stop/disconnect。"""
        manager = DeviceManager()
        device = MockDevice("dev_001")
        manager.register(device)

        result = await manager.unregister("dev_001")
        assert result is True
        assert manager.standalone_count == 0
        assert device not in manager.all_devices
        # 未 running 不應觸發 stop/disconnect
        device.stop.assert_not_called()
        device.disconnect.assert_not_called()

    async def test_unregister_standalone_while_running_calls_stop_disconnect(self):
        """running 時 unregister 應先呼叫 stop + disconnect。"""
        manager = DeviceManager()
        device = MockDevice("dev_001")
        manager.register(device)
        await manager.start()

        try:
            result = await manager.unregister("dev_001")
            assert result is True
            device.stop.assert_called_once()
            device.disconnect.assert_called_once()
            assert manager.standalone_count == 0
        finally:
            await manager.stop()

    async def test_unregister_standalone_stop_exception_is_warned(self):
        """running 時 stop 拋 Exception，函式仍完成（警告被記錄，CancelledError 不被吃）。"""
        manager = DeviceManager()
        device = MockDevice("dev_err")
        device.stop = AsyncMock(side_effect=RuntimeError("stop boom"))
        manager.register(device)
        await manager.start()

        try:
            result = await manager.unregister("dev_err")
            # 即使 stop 失敗也應回 True 並完成移除
            assert result is True
            device.stop.assert_called_once()
            device.disconnect.assert_called_once()
            assert manager.standalone_count == 0
        finally:
            # already unregistered，stop 應為 no-op
            await manager.stop()

    async def test_unregister_standalone_disconnect_exception_is_warned(self):
        """running 時 disconnect 拋 Exception，函式仍完成。"""
        manager = DeviceManager()
        device = MockDevice("dev_dc_err")
        device.disconnect = AsyncMock(side_effect=RuntimeError("dc boom"))
        manager.register(device)
        await manager.start()

        try:
            result = await manager.unregister("dev_dc_err")
            assert result is True
            assert manager.standalone_count == 0
        finally:
            await manager.stop()

    async def test_unregister_accepts_device_protocol(self, mock_device_protocol_with_lifecycle):
        """非 AsyncModbusDevice（MockDeviceProtocol + lifecycle）亦可 unregister（非 running 狀態）。"""
        manager = DeviceManager()
        manager.register(mock_device_protocol_with_lifecycle)

        result = await manager.unregister(mock_device_protocol_with_lifecycle.device_id)
        assert result is True
        assert manager.standalone_count == 0


# ======================== Unregister Group Tests ========================


class TestDeviceManagerUnregisterGroup:
    """群組 unregister 測試。

    source code ``unregister_group`` 要求「完全匹配」：給定的 ids 集合必須等於某群組的 ids 集合，
    否則回傳 False（不 raise ValueError）。
    """

    async def test_unregister_group_nonexistent_returns_false(self):
        manager = DeviceManager()
        result = await manager.unregister_group(["does_not_exist"])
        assert result is False

    async def test_unregister_group_partial_match_returns_false(self):
        """部分匹配（ids 子集）不視為匹配，回傳 False，群組保持不變。"""
        manager = DeviceManager()
        client = MockClient()
        devices = [MockDevice("g1", client), MockDevice("g2", client), MockDevice("g3", client)]
        manager.register_group(devices)

        result = await manager.unregister_group(["g1", "g2"])  # 缺 g3
        assert result is False
        assert manager.group_count == 1
        assert len(manager.all_devices) == 3

    async def test_unregister_group_exact_match_when_not_running(self):
        manager = DeviceManager()
        client = MockClient()
        devices = [MockDevice("g1", client), MockDevice("g2", client)]
        manager.register_group(devices)

        result = await manager.unregister_group(["g1", "g2"])
        assert result is True
        assert manager.group_count == 0
        assert len(manager.all_devices) == 0

    async def test_unregister_group_exact_match_order_independent(self):
        """順序無關（以 set 匹配）。"""
        manager = DeviceManager()
        client = MockClient()
        devices = [MockDevice("a", client), MockDevice("b", client)]
        manager.register_group(devices)

        result = await manager.unregister_group(["b", "a"])
        assert result is True
        assert manager.group_count == 0

    async def test_unregister_group_while_running_stops_and_disconnects(self):
        manager = DeviceManager()
        client = MockClient()
        devices = [MockDevice("g1", client), MockDevice("g2", client)]
        manager.register_group(devices, interval=0.05)
        await manager.start()

        try:
            result = await manager.unregister_group(["g1", "g2"])
            assert result is True
            for d in devices:
                d.disconnect.assert_called_once()
            assert manager.group_count == 0
        finally:
            await manager.stop()

    async def test_unregister_group_disconnect_failures_are_warned(self):
        """群組內兩個 disconnect 都失敗時，函式仍完成、不拋錯。"""
        manager = DeviceManager()
        client = MockClient()
        d1 = MockDevice("g1", client)
        d2 = MockDevice("g2", client)
        d1.disconnect = AsyncMock(side_effect=RuntimeError("dc1"))
        d2.disconnect = AsyncMock(side_effect=RuntimeError("dc2"))
        manager.register_group([d1, d2], interval=0.05)
        await manager.start()

        try:
            result = await manager.unregister_group(["g1", "g2"])
            assert result is True
            d1.disconnect.assert_called_once()
            d2.disconnect.assert_called_once()
            assert manager.group_count == 0
        finally:
            await manager.stop()
