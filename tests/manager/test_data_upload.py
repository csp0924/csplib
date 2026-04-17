# =============== Manager Data Tests - Upload ===============
#
# DataUploadManager 單元測試
#
# 測試覆蓋：
# - subscribe/unsubscribe 設備訂閱
# - read_complete 事件處理
# - disconnected 事件處理（含巢狀結構）
# - nullify_nested 工具函數

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from csp_lib.equipment.device.events import (
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    DisconnectPayload,
    ReadCompletePayload,
)
from csp_lib.manager.data.upload import DataUploadManager, nullify_nested


class MockDevice:
    """Mock AsyncModbusDevice for testing"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self._handlers: dict[str, list] = {}

    def on(self, event: str, handler):
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

        def cancel():
            if event in self._handlers and handler in self._handlers[event]:
                self._handlers[event].remove(handler)

        return cancel

    async def emit(self, event: str, payload):
        """Simulate event emission for testing"""
        for handler in self._handlers.get(event, []):
            await handler(payload)


class MockUploader:
    """Mock MongoBatchUploader for testing"""

    def __init__(self):
        self.enqueue = AsyncMock()
        self.register_collection = MagicMock()


# ======================== nullify_nested Tests ========================


class TestNullifyNested:
    """nullify_nested 工具函數測試"""

    def test_primitive_value(self):
        """原始值應轉為 None"""
        assert nullify_nested(25.5) is None
        assert nullify_nested(100) is None
        assert nullify_nested("text") is None
        assert nullify_nested(True) is None

    def test_flat_dict(self):
        """扁平 dict 應保留結構，值轉為 None"""
        result = nullify_nested({"a": 1, "b": 2, "c": 3})
        assert result == {"a": None, "b": None, "c": None}

    def test_flat_list(self):
        """扁平 list 應保留長度，值轉為 None"""
        result = nullify_nested([1, 2, 3])
        assert result == [None, None, None]

    def test_nested_dict(self):
        """巢狀 dict 應遞歸處理"""
        result = nullify_nested({"status": {"running": True, "mode": 2}})
        assert result == {"status": {"running": None, "mode": None}}

    def test_nested_list(self):
        """巢狀 list 應遞歸處理"""
        result = nullify_nested([[1, 2], [3, 4]])
        assert result == [[None, None], [None, None]]

    def test_mixed_structure(self):
        """混合結構應正確處理"""
        value = {
            "temperature": 25.5,
            "status": {"is_running": True, "mode": 2},
            "errors": [1, 2, 3],
            "config": {"limits": [10, 20], "name": "device1"},
        }
        result = nullify_nested(value)
        expected = {
            "temperature": None,
            "status": {"is_running": None, "mode": None},
            "errors": [None, None, None],
            "config": {"limits": [None, None], "name": None},
        }
        assert result == expected

    def test_empty_structures(self):
        """空結構應保持空"""
        assert nullify_nested({}) == {}
        assert nullify_nested([]) == []


# ======================== Subscribe/Unsubscribe Tests ========================


class TestDataUploadManagerSubscription:
    """訂閱/取消訂閱測試"""

    @pytest.fixture
    def uploader(self) -> MockUploader:
        return MockUploader()

    @pytest.fixture
    def manager(self, uploader: MockUploader) -> DataUploadManager:
        return DataUploadManager(uploader=uploader)

    def test_subscribe_device(self, manager: DataUploadManager, uploader: MockUploader):
        """subscribe 應註冊事件處理器"""
        device = MockDevice("device_001")

        manager.configure(device.device_id, "device_data")
        manager.subscribe(device)

        # 應有 2 個事件被註冊
        assert len(device._handlers.get(EVENT_READ_COMPLETE, [])) == 1
        assert len(device._handlers.get(EVENT_DISCONNECTED, [])) == 1

        # 應註冊 collection
        uploader.register_collection.assert_called_once_with("device_data")

    def test_subscribe_idempotent(self, manager: DataUploadManager):
        """重複 subscribe 同一設備應無效果"""
        device = MockDevice("device_001")

        manager.configure(device.device_id, "device_data")
        manager.subscribe(device)
        manager.configure(device.device_id, "device_data")
        manager.subscribe(device)  # 第二次

        # 仍只有 1 個處理器
        assert len(device._handlers.get(EVENT_READ_COMPLETE, [])) == 1

    def test_unsubscribe_device(self, manager: DataUploadManager):
        """unsubscribe 應移除所有事件處理器"""
        device = MockDevice("device_001")

        manager.configure(device.device_id, "device_data")
        manager.subscribe(device)
        manager.unsubscribe(device)

        # 所有處理器應被移除
        assert len(device._handlers.get(EVENT_READ_COMPLETE, [])) == 0
        assert len(device._handlers.get(EVENT_DISCONNECTED, [])) == 0

    def test_unsubscribe_unsubscribed_no_error(self, manager: DataUploadManager):
        """取消訂閱未訂閱的設備不應報錯"""
        device = MockDevice("device_001")
        manager.unsubscribe(device)  # 不應拋錯

    def test_subscribe_multiple_devices(self, manager: DataUploadManager):
        """應能訂閱多個設備"""
        device1 = MockDevice("device_001")
        device2 = MockDevice("device_002")

        manager.configure(device1.device_id, "device1_data")
        manager.subscribe(device1)
        manager.configure(device2.device_id, "device2_data")
        manager.subscribe(device2)

        assert len(device1._handlers.get(EVENT_READ_COMPLETE, [])) == 1
        assert len(device2._handlers.get(EVENT_READ_COMPLETE, [])) == 1


# ======================== Read Complete Event Tests ========================


class TestDataUploadManagerReadComplete:
    """read_complete 事件測試"""

    @pytest.fixture
    def uploader(self) -> MockUploader:
        return MockUploader()

    @pytest.fixture
    def manager(self, uploader: MockUploader) -> DataUploadManager:
        return DataUploadManager(uploader=uploader)

    @pytest.mark.asyncio
    async def test_on_read_complete_enqueues_data(self, manager: DataUploadManager, uploader: MockUploader):
        """read_complete 應將資料加入 queue"""
        device = MockDevice("device_001")
        manager.configure(device.device_id, "device_data")
        manager.subscribe(device)

        timestamp = datetime.now(timezone.utc)
        payload = ReadCompletePayload(
            device_id="device_001",
            values={"temperature": 25.5, "humidity": 60},
            duration_ms=50.0,
            timestamp=timestamp,
        )
        await device.emit(EVENT_READ_COMPLETE, payload)

        uploader.enqueue.assert_called_once()
        call_args = uploader.enqueue.call_args[0]
        assert call_args[0] == "device_data"
        assert call_args[1]["device_id"] == "device_001"
        assert call_args[1]["temperature"] == 25.5
        assert call_args[1]["humidity"] == 60
        assert call_args[1]["timestamp"] == timestamp

    @pytest.mark.asyncio
    async def test_on_read_complete_caches_values(self, manager: DataUploadManager, uploader: MockUploader):
        """read_complete 應快取值結構"""
        device = MockDevice("device_001")
        manager.configure(device.device_id, "device_data")
        manager.subscribe(device)

        payload = ReadCompletePayload(
            device_id="device_001",
            values={"temperature": 25.5},
            duration_ms=50.0,
        )
        await device.emit(EVENT_READ_COMPLETE, payload)

        # 檢查快取
        assert manager._last_values["device_001"] == {"temperature": 25.5}


# ======================== Disconnected Event Tests ========================


class TestDataUploadManagerDisconnected:
    """disconnected 事件測試"""

    @pytest.fixture
    def uploader(self) -> MockUploader:
        return MockUploader()

    @pytest.fixture
    def manager(self, uploader: MockUploader) -> DataUploadManager:
        return DataUploadManager(uploader=uploader)

    @pytest.mark.asyncio
    async def test_on_disconnected_enqueues_null_values(self, manager: DataUploadManager, uploader: MockUploader):
        """disconnected 應上傳空值記錄"""
        device = MockDevice("device_001")
        manager.configure(device.device_id, "device_data")
        manager.subscribe(device)

        # 先讀取一次建立快取
        read_payload = ReadCompletePayload(
            device_id="device_001",
            values={"temperature": 25.5, "humidity": 60},
            duration_ms=50.0,
        )
        await device.emit(EVENT_READ_COMPLETE, read_payload)

        uploader.enqueue.reset_mock()

        # 斷線
        disconnect_payload = DisconnectPayload(
            device_id="device_001",
            reason="timeout",
            consecutive_failures=5,
        )
        await device.emit(EVENT_DISCONNECTED, disconnect_payload)

        uploader.enqueue.assert_called_once()
        call_args = uploader.enqueue.call_args[0]
        assert call_args[0] == "device_data"
        assert call_args[1]["device_id"] == "device_001"
        assert call_args[1]["temperature"] is None
        assert call_args[1]["humidity"] is None

    @pytest.mark.asyncio
    async def test_on_disconnected_preserves_nested_structure(self, manager: DataUploadManager, uploader: MockUploader):
        """disconnected 應保留巢狀結構"""
        device = MockDevice("device_001")
        manager.configure(device.device_id, "device_data")
        manager.subscribe(device)

        # 先讀取一次建立快取（含巢狀結構）
        read_payload = ReadCompletePayload(
            device_id="device_001",
            values={
                "temperature": 25.5,
                "status": {"running": True, "mode": 2},
                "errors": [1, 2, 3],
            },
            duration_ms=50.0,
        )
        await device.emit(EVENT_READ_COMPLETE, read_payload)

        uploader.enqueue.reset_mock()

        # 斷線
        disconnect_payload = DisconnectPayload(
            device_id="device_001",
            reason="timeout",
            consecutive_failures=5,
        )
        await device.emit(EVENT_DISCONNECTED, disconnect_payload)

        call_args = uploader.enqueue.call_args[0]
        doc = call_args[1]

        assert doc["temperature"] is None
        assert doc["status"] == {"running": None, "mode": None}
        assert doc["errors"] == [None, None, None]

    @pytest.mark.asyncio
    async def test_on_disconnected_no_cache_skips_upload(self, manager: DataUploadManager, uploader: MockUploader):
        """無快取時斷線應跳過上傳"""
        device = MockDevice("device_001")
        manager.configure(device.device_id, "device_data")
        manager.subscribe(device)

        # 直接斷線（無先前讀取）
        disconnect_payload = DisconnectPayload(
            device_id="device_001",
            reason="timeout",
            consecutive_failures=5,
        )
        await device.emit(EVENT_DISCONNECTED, disconnect_payload)

        # 不應呼叫 enqueue（因為無快取結構）
        uploader.enqueue.assert_not_called()


# ======================== Save Interval (Decimation) Tests ========================


class TestDataUploadManagerSaveInterval:
    """save_interval 降頻儲存測試"""

    @pytest.fixture
    def uploader(self) -> MockUploader:
        return MockUploader()

    @pytest.fixture
    def manager(self, uploader: MockUploader) -> DataUploadManager:
        return DataUploadManager(uploader=uploader)

    def _make_payload(self, device_id: str = "device_001") -> ReadCompletePayload:
        return ReadCompletePayload(
            device_id=device_id,
            values={"temperature": 25.5},
            duration_ms=50.0,
        )

    @pytest.mark.asyncio
    async def test_no_interval_saves_every_read(self, manager: DataUploadManager, uploader: MockUploader):
        """save_interval=0（預設）時每次讀取都儲存"""
        device = MockDevice("device_001")
        manager.configure(device.device_id, "data")
        manager.subscribe(device)

        for _ in range(5):
            await device.emit(EVENT_READ_COMPLETE, self._make_payload())

        assert uploader.enqueue.call_count == 5

    @pytest.mark.asyncio
    async def test_interval_skips_within_window(self, manager: DataUploadManager, uploader: MockUploader):
        """在 save_interval 內的讀取應被跳過"""
        device = MockDevice("device_001")
        manager.configure(device.device_id, "data", save_interval=30)
        manager.subscribe(device)

        fake_time = 1000.0

        with patch("csp_lib.manager.data.upload.time.monotonic", side_effect=lambda: fake_time):
            # 第一次：應儲存
            await device.emit(EVENT_READ_COMPLETE, self._make_payload())
            assert uploader.enqueue.call_count == 1

            # 第二次（同一時間點）：應跳過
            await device.emit(EVENT_READ_COMPLETE, self._make_payload())
            assert uploader.enqueue.call_count == 1

    @pytest.mark.asyncio
    async def test_interval_saves_after_elapsed(self, manager: DataUploadManager, uploader: MockUploader):
        """超過 save_interval 後應再次儲存"""
        device = MockDevice("device_001")
        manager.configure(device.device_id, "data", save_interval=30)
        manager.subscribe(device)

        fake_time = [1000.0]

        def mock_monotonic():
            return fake_time[0]

        with patch("csp_lib.manager.data.upload.time.monotonic", side_effect=mock_monotonic):
            # t=0: 儲存
            await device.emit(EVENT_READ_COMPLETE, self._make_payload())
            assert uploader.enqueue.call_count == 1

            # t=10: 跳過
            fake_time[0] = 1010.0
            await device.emit(EVENT_READ_COMPLETE, self._make_payload())
            assert uploader.enqueue.call_count == 1

            # t=31: 儲存
            fake_time[0] = 1031.0
            await device.emit(EVENT_READ_COMPLETE, self._make_payload())
            assert uploader.enqueue.call_count == 2

    @pytest.mark.asyncio
    async def test_interval_always_caches_values(self, manager: DataUploadManager, uploader: MockUploader):
        """即使跳過儲存，仍應更新快取（供斷線空值記錄使用）"""
        device = MockDevice("device_001")
        manager.configure(device.device_id, "data", save_interval=30)
        manager.subscribe(device)

        fake_time = [1000.0]

        with patch("csp_lib.manager.data.upload.time.monotonic", side_effect=lambda: fake_time[0]):
            # 第一次讀取
            payload1 = ReadCompletePayload(
                device_id="device_001",
                values={"temperature": 20.0},
                duration_ms=50.0,
            )
            await device.emit(EVENT_READ_COMPLETE, payload1)

            # 第二次讀取（被降頻跳過）但快取應更新
            payload2 = ReadCompletePayload(
                device_id="device_001",
                values={"temperature": 30.0},
                duration_ms=50.0,
            )
            await device.emit(EVENT_READ_COMPLETE, payload2)

            assert uploader.enqueue.call_count == 1  # 只存了一次
            assert manager._last_values["device_001"]["temperature"] == 30.0  # 快取已更新

    @pytest.mark.asyncio
    async def test_different_devices_independent_intervals(self, manager: DataUploadManager, uploader: MockUploader):
        """不同設備的 save_interval 獨立運作"""
        device_fast = MockDevice("fast")
        device_slow = MockDevice("slow")
        manager.configure(device_fast.device_id, "fast_data", save_interval=0)
        manager.subscribe(device_fast)  # 每次都存
        manager.configure(device_slow.device_id, "slow_data", save_interval=60)
        manager.subscribe(device_slow)

        fake_time = [1000.0]

        with patch("csp_lib.manager.data.upload.time.monotonic", side_effect=lambda: fake_time[0]):
            for i in range(3):
                await device_fast.emit(
                    EVENT_READ_COMPLETE,
                    ReadCompletePayload(device_id="fast", values={"v": i}, duration_ms=10.0),
                )
                await device_slow.emit(
                    EVENT_READ_COMPLETE,
                    ReadCompletePayload(device_id="slow", values={"v": i}, duration_ms=10.0),
                )

        # fast: 3 次都存, slow: 只存第 1 次
        fast_calls = [c for c in uploader.enqueue.call_args_list if c[0][0] == "fast_data"]
        slow_calls = [c for c in uploader.enqueue.call_args_list if c[0][0] == "slow_data"]
        assert len(fast_calls) == 3
        assert len(slow_calls) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_cleans_interval_state(self, manager: DataUploadManager):
        """取消訂閱後應清理 interval 相關狀態"""
        device = MockDevice("device_001")
        manager.configure(device.device_id, "data", save_interval=30)
        manager.subscribe(device)

        assert "device_001" in manager._save_intervals

        manager.unsubscribe(device)

        assert "device_001" not in manager._save_intervals
        assert "device_001" not in manager._last_save_times


# ======================== v0.8.2: buffered_uploader 注入 ========================


class TestDataUploadManagerBufferedUploader:
    """
    v0.8.2：buffered_uploader 作為 fail-safe wrapper

    若提供 buffered_uploader，所有 enqueue 應走本地 SQLite buffer，
    避免下游 MongoDB 故障時資料遺失。
    """

    @pytest.mark.asyncio
    async def test_no_buffered_uploader_uses_provided_uploader(self):
        """buffered_uploader=None 時 self._uploader 應等於傳入的 uploader"""
        uploader = MockUploader()
        manager = DataUploadManager(uploader=uploader)

        assert manager._uploader is uploader

    @pytest.mark.asyncio
    async def test_buffered_uploader_replaces_normal_uploader(self):
        """提供 buffered_uploader 時 self._uploader 應改為 buffered_uploader"""
        uploader = MockUploader()
        buffered = MockUploader()  # 使用相同介面（register_collection + enqueue）
        manager = DataUploadManager(uploader=uploader, buffered_uploader=buffered)

        assert manager._uploader is buffered
        assert manager._uploader is not uploader

    @pytest.mark.asyncio
    async def test_buffered_uploader_receives_enqueue_events(self):
        """有 buffered_uploader 時，read_complete 應 enqueue 至 buffered_uploader 而非原 uploader"""
        uploader = MockUploader()
        buffered = MockUploader()
        manager = DataUploadManager(uploader=uploader, buffered_uploader=buffered)

        device = MockDevice("device_001")
        manager.configure(device.device_id, "device_data")
        manager.subscribe(device)

        payload = ReadCompletePayload(
            device_id="device_001",
            values={"t": 25.5},
            duration_ms=10.0,
        )
        await device.emit(EVENT_READ_COMPLETE, payload)

        # buffered_uploader 被呼叫，原 uploader 不應被呼叫
        buffered.enqueue.assert_awaited_once()
        uploader.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_buffered_uploader_receives_register_collection(self):
        """configure 時 register_collection 應走 buffered_uploader"""
        uploader = MockUploader()
        buffered = MockUploader()
        manager = DataUploadManager(uploader=uploader, buffered_uploader=buffered)

        manager.configure("device_001", "device_data")

        buffered.register_collection.assert_called_once_with("device_data")
        uploader.register_collection.assert_not_called()
