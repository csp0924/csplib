# =============== Statistics Tests - Manager ===============
#
# StatisticsManager 單元測試
#
# 測試覆蓋：
# - subscribe/unsubscribe 設備訂閱
# - read_complete 事件驅動能耗計算
# - 區間完成時上傳 energy 記錄
# - 功率加總記錄上傳
# - engine 屬性存取

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.equipment.device.events import EVENT_READ_COMPLETE, ReadCompletePayload
from csp_lib.statistics.config import (
    DeviceMeterType,
    MetricDefinition,
    PowerSumDefinition,
    StatisticsConfig,
)
from csp_lib.statistics.manager import StatisticsManager


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


class MockRegistry:
    """Mock DeviceRegistry for testing"""

    def __init__(self, trait_devices: dict[str, list] | None = None):
        self._trait_devices = trait_devices or {}

    def get_devices_by_trait(self, trait: str) -> list:
        return self._trait_devices.get(trait, [])


# ======================== Subscribe/Unsubscribe ========================


class TestStatisticsManagerSubscription:
    """訂閱/取消訂閱測試"""

    @pytest.fixture
    def uploader(self) -> MockUploader:
        return MockUploader()

    @pytest.fixture
    def config(self) -> StatisticsConfig:
        return StatisticsConfig(
            metrics=[MetricDefinition("dev_01", DeviceMeterType.CUMULATIVE, "kwh_total")],
            intervals_minutes=(15,),
        )

    @pytest.fixture
    def manager(self, config: StatisticsConfig, uploader: MockUploader) -> StatisticsManager:
        return StatisticsManager(config=config, uploader=uploader)

    def test_subscribe_registers_event(self, manager: StatisticsManager):
        device = MockDevice("dev_01")
        manager.subscribe(device)
        assert len(device._handlers.get(EVENT_READ_COMPLETE, [])) == 1

    def test_subscribe_idempotent(self, manager: StatisticsManager):
        device = MockDevice("dev_01")
        manager.subscribe(device)
        manager.subscribe(device)
        assert len(device._handlers.get(EVENT_READ_COMPLETE, [])) == 1

    def test_unsubscribe_removes_event(self, manager: StatisticsManager):
        device = MockDevice("dev_01")
        manager.subscribe(device)
        manager.unsubscribe(device)
        assert len(device._handlers.get(EVENT_READ_COMPLETE, [])) == 0

    def test_unsubscribe_unsubscribed_no_error(self, manager: StatisticsManager):
        device = MockDevice("dev_01")
        manager.unsubscribe(device)

    def test_registers_collection(self, uploader: MockUploader, config: StatisticsConfig):
        StatisticsManager(config=config, uploader=uploader)
        uploader.register_collection.assert_called_once_with("statistics")


# ======================== Energy Record Upload ========================


class TestStatisticsManagerEnergyUpload:
    """能耗記錄上傳測試"""

    @pytest.fixture
    def uploader(self) -> MockUploader:
        return MockUploader()

    @pytest.fixture
    def manager(self, uploader: MockUploader) -> StatisticsManager:
        config = StatisticsConfig(
            metrics=[MetricDefinition("dev_01", DeviceMeterType.CUMULATIVE, "kwh_total")],
            intervals_minutes=(15,),
        )
        return StatisticsManager(config=config, uploader=uploader)

    @pytest.mark.asyncio
    async def test_no_upload_before_boundary(self, manager: StatisticsManager, uploader: MockUploader):
        """未跨越邊界不應上傳"""
        device = MockDevice("dev_01")
        manager.subscribe(device)

        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(
                device_id="dev_01",
                values={"kwh_total": 100.0},
                duration_ms=50.0,
                timestamp=datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
            ),
        )
        uploader.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_on_boundary_crossing(self, manager: StatisticsManager, uploader: MockUploader):
        """跨越邊界應上傳 energy 記錄"""
        device = MockDevice("dev_01")
        manager.subscribe(device)

        # Feed readings within interval
        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(
                device_id="dev_01",
                values={"kwh_total": 100.0},
                duration_ms=50.0,
                timestamp=datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
            ),
        )
        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(
                device_id="dev_01",
                values={"kwh_total": 110.0},
                duration_ms=50.0,
                timestamp=datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc),
            ),
        )

        # Cross boundary
        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(
                device_id="dev_01",
                values={"kwh_total": 120.0},
                duration_ms=50.0,
                timestamp=datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc),
            ),
        )

        uploader.enqueue.assert_called_once()
        call_args = uploader.enqueue.call_args[0]
        assert call_args[0] == "statistics"  # collection name
        doc = call_args[1]
        assert doc["type"] == "energy"
        assert doc["device_id"] == "dev_01"
        assert doc["interval_minutes"] == 15
        assert doc["kwh"] == pytest.approx(10.0)
        assert doc["meter_type"] == "cumulative"
        assert doc["period_start"] == datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert doc["period_end"] == datetime(2025, 1, 1, 10, 15, 0, tzinfo=timezone.utc)


# ======================== Power Sum Upload ========================


class TestStatisticsManagerPowerSumUpload:
    """功率加總記錄上傳測試"""

    @pytest.fixture
    def uploader(self) -> MockUploader:
        return MockUploader()

    @pytest.fixture
    def manager(self, uploader: MockUploader) -> StatisticsManager:
        mock_dev1 = MagicMock()
        mock_dev1.device_id = "pcs_01"
        mock_dev2 = MagicMock()
        mock_dev2.device_id = "pcs_02"

        registry = MockRegistry(trait_devices={"pcs": [mock_dev1, mock_dev2]})

        config = StatisticsConfig(
            metrics=[MetricDefinition("pcs_01", DeviceMeterType.CUMULATIVE, "kwh_total")],
            power_sums=[PowerSumDefinition("p_total_pcs", "pcs", "active_power")],
            intervals_minutes=(15,),
        )
        return StatisticsManager(config=config, uploader=uploader, registry=registry)

    @pytest.mark.asyncio
    async def test_power_sum_uploaded_on_boundary(self, manager: StatisticsManager, uploader: MockUploader):
        """區間完成時應同時上傳 power_sum 記錄"""
        device = MockDevice("pcs_01")
        manager.subscribe(device)

        # Feed device with both energy and power data
        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(
                device_id="pcs_01",
                values={"kwh_total": 100.0, "active_power": 50.0},
                duration_ms=50.0,
                timestamp=datetime(2025, 1, 1, 10, 2, 0, tzinfo=timezone.utc),
            ),
        )
        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(
                device_id="pcs_01",
                values={"kwh_total": 110.0, "active_power": 60.0},
                duration_ms=50.0,
                timestamp=datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc),
            ),
        )

        # Cross boundary
        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(
                device_id="pcs_01",
                values={"kwh_total": 120.0, "active_power": 70.0},
                duration_ms=50.0,
                timestamp=datetime(2025, 1, 1, 10, 16, 0, tzinfo=timezone.utc),
            ),
        )

        # Should have 2 uploads: 1 energy + 1 power_sum
        assert uploader.enqueue.call_count == 2

        # Find the power_sum document
        docs = [call.args[1] for call in uploader.enqueue.call_args_list]
        power_doc = next(d for d in docs if d["type"] == "power_sum")
        assert power_doc["name"] == "p_total_pcs"
        assert power_doc["total_power"] == pytest.approx(70.0)  # latest value (updated before snapshot)
        assert power_doc["device_count"] == 2


# ======================== Engine Access ========================


class TestStatisticsManagerEngine:
    """engine 屬性存取測試"""

    def test_engine_property(self):
        config = StatisticsConfig(
            power_sums=[PowerSumDefinition("p_total", "pcs", "active_power")],
        )
        uploader = MockUploader()
        manager = StatisticsManager(config=config, uploader=uploader)

        assert manager.engine is not None
        assert manager.engine.get_power_sum("p_total") == 0.0
