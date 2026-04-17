# =============== Tests - AsyncCANDevice ===============
#
# 測試 CAN 設備整合

import asyncio
import time

import pytest

from csp_lib.can.clients.base import AsyncCANClientBase
from csp_lib.can.config import CANFrame
from csp_lib.equipment.device.can_device import AsyncCANDevice, CANRxFrameDefinition
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.equipment.device.events import EVENT_CONNECTED, EVENT_DISCONNECTED, EVENT_READ_COMPLETE
from csp_lib.equipment.device.protocol import DeviceProtocol
from csp_lib.equipment.processing.can_encoder import CANSignalDefinition, FrameBufferConfig
from csp_lib.equipment.processing.can_parser import CANField, CANFrameParser
from csp_lib.equipment.transport.periodic_sender import PeriodicFrameConfig
from csp_lib.equipment.transport.writer import WriteStatus


class MockCANClient(AsyncCANClientBase):
    """Mock CAN Client for testing"""

    def __init__(self):
        self.connected = False
        self.listener_running = False
        self.sent_frames: list[tuple[int, bytes]] = []
        self._handlers: dict[int, list] = {}
        self._pending: dict[int, asyncio.Future] = {}

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def is_connected(self):
        return self.connected

    async def start_listener(self):
        self.listener_running = True

    async def stop_listener(self):
        self.listener_running = False

    def subscribe(self, can_id, handler):
        if can_id not in self._handlers:
            self._handlers[can_id] = []
        self._handlers[can_id].append(handler)

        def cancel():
            if can_id in self._handlers and handler in self._handlers[can_id]:
                self._handlers[can_id].remove(handler)

        return cancel

    async def send(self, can_id, data):
        self.sent_frames.append((can_id, data))

    async def request(self, can_id, data, response_id, timeout=1.0):
        # 模擬回應
        return CANFrame(can_id=response_id, data=b"\x00" * 8)

    def inject_frame(self, can_id: int, data: bytes):
        """模擬接收到訊框"""
        frame = CANFrame(can_id=can_id, data=data)
        for handler in self._handlers.get(can_id, []):
            handler(frame)


def _make_device(client: MockCANClient | None = None) -> tuple[AsyncCANDevice, MockCANClient]:
    """建立測試用 CAN 設備"""
    if client is None:
        client = MockCANClient()

    bms_parser = CANFrameParser(
        source_name="bms",
        fields=[
            CANField("soc", 0, 8, resolution=0.4, decimals=1),
            CANField("voltage", 8, 16, resolution=0.1, decimals=1),
        ],
    )

    tx_signals = [
        CANSignalDefinition(0x200, CANField("power_target", 0, 16, resolution=1.0)),
        CANSignalDefinition(0x200, CANField("start_stop", 16, 1, resolution=1.0)),
    ]

    device = AsyncCANDevice(
        config=DeviceConfig(device_id="test_can_001"),
        client=client,
        tx_signals=tx_signals,
        tx_buffer_configs=[FrameBufferConfig(can_id=0x200)],
        tx_periodic_configs=[PeriodicFrameConfig(can_id=0x200, interval=0.1)],
        rx_frame_definitions=[
            CANRxFrameDefinition(can_id=0x100, parser=bms_parser),
        ],
    )
    return device, client


class TestAsyncCANDeviceProperties:
    """測試 CAN 設備的屬性"""

    def test_device_id(self):
        device, _ = _make_device()
        assert device.device_id == "test_can_001"

    def test_initial_state(self):
        device, _ = _make_device()
        assert not device.is_connected
        assert not device.is_responsive
        assert device.latest_values == {}
        assert device.active_alarms == []
        assert not device.is_protected


class TestAsyncCANDeviceLifecycle:
    """測試 CAN 設備的生命週期"""

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        device, client = _make_device()

        await device.connect()
        assert device.is_connected
        assert device.is_responsive
        assert client.connected
        assert client.listener_running

        await device.disconnect()
        assert not device.is_connected
        assert not device.is_responsive

    @pytest.mark.asyncio
    async def test_context_manager(self):
        client = MockCANClient()
        device, _ = _make_device(client)

        async with device:
            assert device.is_connected

        assert not device.is_connected


class TestAsyncCANDeviceWrite:
    """測試 CAN 設備的寫入功能"""

    @pytest.mark.asyncio
    async def test_write_signal(self):
        device, client = _make_device()
        await device.connect()

        result = await device.write("power_target", 5000)
        assert result.status == WriteStatus.SUCCESS
        assert result.point_name == "power_target"

        await device.disconnect()

    @pytest.mark.asyncio
    async def test_write_immediate(self):
        device, client = _make_device()
        await device.connect()

        result = await device.write("power_target", 5000, immediate=True)
        assert result.status == WriteStatus.SUCCESS

        # 應該有立即發送的訊框
        assert len(client.sent_frames) == 1
        can_id, data = client.sent_frames[0]
        assert can_id == 0x200

        await device.disconnect()

    @pytest.mark.asyncio
    async def test_write_nonexistent_signal(self):
        device, client = _make_device()
        await device.connect()

        result = await device.write("nonexistent", 100)
        assert result.status == WriteStatus.VALIDATION_FAILED

        await device.disconnect()

    @pytest.mark.asyncio
    async def test_write_preserves_other_signals(self):
        """寫入一個信號不影響其他信號"""
        device, client = _make_device()
        await device.connect()

        await device.write("power_target", 5000)
        await device.write("start_stop", 1, immediate=True)

        _, data = client.sent_frames[0]
        frame_int = int.from_bytes(data, byteorder="little")

        # power_target (bit 0-15) 應保持 5000
        assert (frame_int >> 0) & 0xFFFF == 5000
        # start_stop (bit 16) 應為 1
        assert (frame_int >> 16) & 0x1 == 1

        await device.disconnect()


class TestAsyncCANDeviceReceive:
    """測試 CAN 設備的接收功能"""

    @pytest.mark.asyncio
    async def test_rx_passive_monitoring(self):
        """被動監聽接收"""
        device, client = _make_device()
        await device.connect()

        # 模擬接收 BMS 訊框（raw CAN bytes，Intel/little-endian 格式）
        # soc: bit 0-7 = 213 → 213 * 0.4 = 85.2
        # voltage: bit 8-23 = 3805 → 3805 * 0.1 = 380.5
        soc_raw = 213
        voltage_raw = 3805
        frame_int = soc_raw | (voltage_raw << 8)
        frame_bytes = frame_int.to_bytes(8, byteorder="little")

        client.inject_frame(0x100, frame_bytes)

        assert device.latest_values["soc"] == 85.2
        assert device.latest_values["voltage"] == 380.5

        await device.disconnect()

    @pytest.mark.asyncio
    async def test_rx_value_change_event(self):
        """接收到新值時觸發事件"""
        device, client = _make_device()
        await device.connect()

        events = []

        async def on_change(payload):
            events.append(payload)

        device.on("value_change", on_change)

        # 發送第一個訊框
        frame_int = 100  # soc_raw=100
        frame_bytes = frame_int.to_bytes(8, byteorder="little")
        client.inject_frame(0x100, frame_bytes)

        # 事件是透過 emitter 非同步處理的，需要等一下
        await asyncio.sleep(0.1)

        # 應該有 value_change 事件（soc 和 voltage 首次出現）
        assert len(events) >= 1

        await device.disconnect()


class TestAsyncCANDeviceReadOnce:
    """測試 read_once"""

    @pytest.mark.asyncio
    async def test_read_once_returns_latest_values(self):
        device, client = _make_device()
        await device.connect()

        # 先注入一些值（raw CAN bytes）
        frame_int = 200 | (1000 << 8)
        frame_bytes = frame_int.to_bytes(8, byteorder="little")
        client.inject_frame(0x100, frame_bytes)

        values = await device.read_once()
        assert "soc" in values
        assert "voltage" in values

        await device.disconnect()


class TestAsyncCANDeviceHealth:
    """測試健康檢查"""

    @pytest.mark.asyncio
    async def test_health_connected(self):
        device, _ = _make_device()
        await device.connect()

        report = device.health()
        assert report.status.value == "healthy"
        assert report.details["protocol"] == "can"

        await device.disconnect()

    def test_health_disconnected(self):
        device, _ = _make_device()
        report = device.health()
        assert report.status.value == "unhealthy"


class TestDeviceProtocol:
    """測試 DeviceProtocol 結構性滿足"""

    def test_can_device_satisfies_protocol(self):
        """AsyncCANDevice 結構性滿足 DeviceProtocol"""
        device, _ = _make_device()
        assert isinstance(device, DeviceProtocol)


class TestAsyncCANDeviceNoTx:
    """測試無 TX 配置的設備（純被動監聽）"""

    @pytest.mark.asyncio
    async def test_pure_rx_device(self):
        client = MockCANClient()
        parser = CANFrameParser(
            source_name="rx",
            fields=[CANField("temp", 0, 8, resolution=1.0, offset=-40.0, as_int=True)],
        )
        device = AsyncCANDevice(
            config=DeviceConfig(device_id="rx_only"),
            client=client,
            rx_frame_definitions=[CANRxFrameDefinition(can_id=0x100, parser=parser)],
        )

        await device.connect()

        # 寫入應該失敗（無 TX 信號）
        result = await device.write("temp", 25)
        assert result.status == WriteStatus.VALIDATION_FAILED

        await device.disconnect()


def _make_short_interval_device(
    client: MockCANClient | None = None,
    read_interval: float = 0.1,
    rx_timeout: float = 0.3,
) -> tuple[AsyncCANDevice, MockCANClient]:
    """建立短間隔的測試用 CAN 設備（方便測試 snapshot loop 和 timeout）"""
    if client is None:
        client = MockCANClient()

    bms_parser = CANFrameParser(
        source_name="bms",
        fields=[
            CANField("soc", 0, 8, resolution=0.4, decimals=1),
            CANField("voltage", 8, 16, resolution=0.1, decimals=1),
        ],
    )

    device = AsyncCANDevice(
        config=DeviceConfig(device_id="test_can_short", read_interval=read_interval),
        client=client,
        rx_frame_definitions=[
            CANRxFrameDefinition(can_id=0x100, parser=bms_parser),
        ],
        rx_timeout=rx_timeout,
    )
    return device, client


class TestSnapshotLoop:
    """測試 snapshot loop 週期性行為"""

    @pytest.mark.asyncio
    async def test_snapshot_loop_emits_read_complete(self):
        """驗證 snapshot loop 按 read_interval 發射 READ_COMPLETE"""
        device, client = _make_short_interval_device(read_interval=0.05)

        read_complete_events = []

        async def on_read_complete(payload):
            read_complete_events.append(payload)

        device.on(EVENT_READ_COMPLETE, on_read_complete)

        await device.connect()
        await device.start()

        # 等待足夠時間讓 snapshot loop 至少觸發 2 次
        await asyncio.sleep(0.15)

        await device.stop()
        await device.disconnect()

        assert len(read_complete_events) >= 2
        assert read_complete_events[0].device_id == "test_can_short"

    @pytest.mark.asyncio
    async def test_rx_no_read_complete_per_frame(self):
        """驗證收到 RX 訊框時不發射額外 READ_COMPLETE。

        snapshot loop 採 work-first 絕對時間錨定（v0.7.2 WI-TD-101），
        startup 會立即 emit 一次基準 READ_COMPLETE；之後在 read_interval=10s 內
        不會再觸發。注入 RX 訊框後 snapshot 計數應與 baseline 相同。
        """
        device, client = _make_short_interval_device(read_interval=10.0)

        read_complete_events = []

        async def on_read_complete(payload):
            read_complete_events.append(payload)

        device.on(EVENT_READ_COMPLETE, on_read_complete)

        await device.connect()
        await device.start()

        # 等 startup snapshot tick 完成（work-first：開始時會 emit 一次）
        await asyncio.sleep(0.05)
        baseline_count = len(read_complete_events)

        # 注入多個 RX 訊框
        for i in range(5):
            frame_int = (i * 10) | (1000 << 8)
            frame_bytes = frame_int.to_bytes(8, byteorder="little")
            client.inject_frame(0x100, frame_bytes)

        # 等一下讓事件處理完
        await asyncio.sleep(0.05)

        await device.stop()
        await device.disconnect()

        # RX 訊框不應觸發額外 READ_COMPLETE（snapshot 計數應等於 baseline）
        assert len(read_complete_events) == baseline_count


class TestRxTimeout:
    """測試 RX timeout 斷線偵測"""

    @pytest.mark.asyncio
    async def test_rx_timeout_sets_not_responsive(self):
        """驗證超過 rx_timeout 後 is_responsive=False + DISCONNECTED 事件"""
        device, client = _make_short_interval_device(read_interval=0.05, rx_timeout=0.1)

        disconnect_events = []

        async def on_disconnect(payload):
            disconnect_events.append(payload)

        device.on(EVENT_DISCONNECTED, on_disconnect)

        await device.connect()
        await device.start()

        assert device.is_responsive

        # 將 _last_rx_time 往前推使其超時
        device._last_rx_time = time.monotonic() - 0.5

        # 等 snapshot loop 執行 timeout 檢查（至少 2 個 read_interval）
        await asyncio.sleep(0.15)

        await device.stop()

        assert not device.is_responsive

        # 等事件處理
        await asyncio.sleep(0.05)

        await device.disconnect()

        # 應該有 rx_timeout 的 DISCONNECTED 事件
        timeout_events = [e for e in disconnect_events if e.reason == "rx_timeout"]
        assert len(timeout_events) >= 1

    @pytest.mark.asyncio
    async def test_rx_timeout_recovery(self):
        """驗證恢復收到訊框後 is_responsive=True + CONNECTED 事件"""
        device, client = _make_short_interval_device(read_interval=0.05, rx_timeout=0.1)

        connected_events = []

        async def on_connected(payload):
            connected_events.append(payload)

        device.on(EVENT_CONNECTED, on_connected)

        await device.connect()
        await device.start()

        # 模擬 timeout
        device._last_rx_time = time.monotonic() - 0.5

        # 等 snapshot loop 偵測到 timeout（至少 2 個 read_interval）
        await asyncio.sleep(0.15)

        assert not device.is_responsive

        # 注入一個訊框恢復
        frame_int = 100 | (2000 << 8)
        frame_bytes = frame_int.to_bytes(8, byteorder="little")
        client.inject_frame(0x100, frame_bytes)

        assert device.is_responsive

        # 等事件處理
        await asyncio.sleep(0.05)

        await device.stop()
        await device.disconnect()

        # 應有恢復的 CONNECTED 事件（排除 connect() 時的初始事件）
        # connect() 用 emit_await，這裡的恢復用 emit，兩者都會觸發 handler
        assert len(connected_events) >= 1
