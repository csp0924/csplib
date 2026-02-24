# =============== Equipment Device Tests - Base ===============
#
# AsyncModbusDevice 非同步設備單元測試
#
# 測試覆蓋：
# - 建構與初始化
# - Lifecycle (connect/disconnect/start/stop)
# - 讀寫操作
# - 告警評估
# - 事件發射
# - 狀態屬性
# - 性能測試

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.alarm import (
    AlarmDefinition,
    AlarmLevel,
    Operator,
    ThresholdAlarmEvaluator,
    ThresholdCondition,
)
from csp_lib.equipment.core import RangeValidator, ReadPoint, WritePoint
from csp_lib.equipment.device.base import AsyncModbusDevice
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.equipment.device.events import (
    EVENT_ALARM_TRIGGERED,
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    EVENT_READ_ERROR,
    EVENT_VALUE_CHANGE,
    EVENT_WRITE_COMPLETE,
)
from csp_lib.equipment.transport import WriteStatus
from csp_lib.modbus import UInt16

# ======================== Fixtures ========================


@pytest.fixture
def mock_client() -> AsyncMock:
    """Mock Modbus client"""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.read_holding_registers = AsyncMock(return_value=[100, 200, 300])
    client.write_registers = AsyncMock()
    return client


@pytest.fixture
def device_config() -> DeviceConfig:
    """基本設備設定"""
    return DeviceConfig(
        device_id="test_device",
        unit_id=1,
        address_offset=0,
        read_interval=0.1,
        disconnect_threshold=3,
    )


@pytest.fixture
def read_points() -> list[ReadPoint]:
    """讀取點位"""
    return [
        ReadPoint(name="power", address=100, data_type=UInt16()),
        ReadPoint(name="voltage", address=101, data_type=UInt16()),
        ReadPoint(name="current", address=102, data_type=UInt16()),
    ]


@pytest.fixture
def write_points() -> list[WritePoint]:
    """寫入點位"""
    return [
        WritePoint(
            name="setpoint",
            address=200,
            data_type=UInt16(),
            validator=RangeValidator(min_value=0, max_value=100),
        ),
    ]


@pytest.fixture
def alarm_evaluators() -> list[ThresholdAlarmEvaluator]:
    """告警評估器"""
    return [
        ThresholdAlarmEvaluator(
            point_name="power",
            conditions=[
                ThresholdCondition(
                    alarm=AlarmDefinition(code="HIGH_POWER", name="功率過高", level=AlarmLevel.WARNING),
                    operator=Operator.GT,
                    value=80,
                ),
            ],
        ),
    ]


@pytest.fixture
def device(
    mock_client: AsyncMock,
    device_config: DeviceConfig,
    read_points: list[ReadPoint],
    write_points: list[WritePoint],
    alarm_evaluators: list[ThresholdAlarmEvaluator],
) -> AsyncModbusDevice:
    """完整組裝的設備"""
    return AsyncModbusDevice(
        config=device_config,
        client=mock_client,
        always_points=read_points,
        write_points=write_points,
        alarm_evaluators=alarm_evaluators,
    )


# ======================== Initialization Tests ========================


class TestAsyncModbusDeviceInit:
    """初始化測試"""

    def test_device_id(self, device: AsyncModbusDevice):
        """device_id 屬性應正確"""
        assert device.device_id == "test_device"

    def test_initial_state_disconnected(self, device: AsyncModbusDevice):
        """初始狀態應為未連線"""
        assert device.is_connected is False
        assert device.is_disconnected is True
        assert device.is_responsive is False

    def test_initial_latest_values_empty(self, device: AsyncModbusDevice):
        """初始 latest_values 應為空"""
        assert device.latest_values == {}

    def test_initial_active_alarms_empty(self, device: AsyncModbusDevice):
        """初始 active_alarms 應為空"""
        assert device.active_alarms == []

    def test_initial_is_running_false(self, device: AsyncModbusDevice):
        """初始 is_running 應為 False"""
        assert device.is_running is False


# ======================== Lifecycle Tests ========================


class TestAsyncModbusDeviceLifecycle:
    """生命週期測試"""

    @pytest.mark.asyncio
    async def test_connect_updates_state(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """connect() 應更新狀態"""
        await device.connect()

        try:
            mock_client.connect.assert_called_once()
            assert device.is_connected is True
            assert device.is_responsive is True
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_updates_state(self, device: AsyncModbusDevice):
        """disconnect() 應更新狀態"""
        await device.connect()
        await device.disconnect()

        assert device.is_connected is False
        assert device.is_responsive is False

    @pytest.mark.asyncio
    async def test_start_creates_read_task(self, device: AsyncModbusDevice):
        """start() 應建立讀取 task"""
        await device.connect()

        try:
            await device.start()
            assert device.is_running is True
        finally:
            await device.stop()
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_stop_cancels_read_task(self, device: AsyncModbusDevice):
        """stop() 應取消讀取 task"""
        await device.connect()
        await device.start()
        await device.stop()

        try:
            assert device.is_running is False
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_context_manager(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """async context manager 應正確運作"""
        async with device:
            assert device.is_connected is True
            assert device.is_running is True

        assert device.is_connected is False
        assert device.is_running is False


# ======================== Read Tests ========================


class TestAsyncModbusDeviceRead:
    """讀取測試"""

    @pytest.mark.asyncio
    async def test_read_once_returns_values(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """read_once() 應返回讀取值"""
        mock_client.read_holding_registers.return_value = [100, 200, 300]

        await device.connect()
        try:
            values = await device.read_once()

            assert "power" in values
            assert "voltage" in values
            assert "current" in values
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_read_updates_latest_values(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """讀取應更新 latest_values"""
        mock_client.read_holding_registers.return_value = [100, 200, 300]

        await device.connect()
        await device.start()
        try:
            # 等待至少一次讀取
            await asyncio.sleep(0.2)

            values = device.latest_values
            assert len(values) > 0
        finally:
            await device.stop()
            await device.disconnect()


# ======================== Write Tests ========================


class TestAsyncModbusDeviceWrite:
    """寫入測試"""

    @pytest.mark.asyncio
    async def test_write_existing_point(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """寫入存在的點位應成功"""
        await device.connect()
        try:
            result = await device.write("setpoint", 50)

            assert result.status == WriteStatus.SUCCESS
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_write_nonexistent_point(self, device: AsyncModbusDevice):
        """寫入不存在的點位應失敗"""
        await device.connect()
        try:
            result = await device.write("nonexistent", 50)

            assert result.status == WriteStatus.VALIDATION_FAILED
            assert "不存在" in result.error_message
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_write_invalid_value(self, device: AsyncModbusDevice):
        """寫入無效值應失敗"""
        await device.connect()
        try:
            result = await device.write("setpoint", 200)  # 超出 0-100 範圍

            assert result.status == WriteStatus.VALIDATION_FAILED
        finally:
            await device.disconnect()


# ======================== Alarm Tests ========================


class TestAsyncModbusDeviceAlarm:
    """告警測試"""

    @pytest.mark.asyncio
    async def test_alarm_triggered_on_threshold(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """超過閾值應觸發告警"""
        # 返回 power=100，超過閾值 80
        mock_client.read_holding_registers.return_value = [100, 200, 300]

        await device.connect()
        await device.start()
        try:
            await asyncio.sleep(0.2)

            # 應有告警被觸發
            active = device.active_alarms
            assert len(active) == 1
            assert active[0].definition.code == "HIGH_POWER"
        finally:
            await device.stop()
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_is_protected_when_alarm_active(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """有 ALARM 級別告警時 is_protected 應為 True"""
        # 建立帶有 ALARM 級別的設備
        config = DeviceConfig(device_id="test", read_interval=0.1, disconnect_threshold=3)
        alarm_evaluator = ThresholdAlarmEvaluator(
            point_name="power",
            conditions=[
                ThresholdCondition(
                    alarm=AlarmDefinition(code="CRITICAL", name="嚴重", level=AlarmLevel.ALARM),
                    operator=Operator.GT,
                    value=50,
                ),
            ],
        )
        test_device = AsyncModbusDevice(
            config=config,
            client=mock_client,
            always_points=[ReadPoint(name="power", address=100, data_type=UInt16())],
            alarm_evaluators=[alarm_evaluator],
        )

        mock_client.read_holding_registers.return_value = [100]

        await test_device.connect()
        await test_device.start()
        try:
            await asyncio.sleep(0.2)
            assert test_device.is_protected is True
        finally:
            await test_device.stop()
            await test_device.disconnect()

    @pytest.mark.asyncio
    async def test_clear_alarm_manually(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """手動清除告警"""
        mock_client.read_holding_registers.return_value = [100, 200, 300]

        await device.connect()
        await device.start()
        try:
            await asyncio.sleep(0.2)

            # 觸發告警後手動清除
            await device.clear_alarm("HIGH_POWER")

            # 告警應被清除
            active = device.active_alarms
            assert len(active) == 0
        finally:
            await device.stop()
            await device.disconnect()


# ======================== Event Tests ========================


class TestAsyncModbusDeviceEvents:
    """事件測試"""

    @pytest.mark.asyncio
    async def test_connected_event_on_connect(self, device: AsyncModbusDevice):
        """connect() 應發射 connected 事件"""
        handler = AsyncMock()
        device.on(EVENT_CONNECTED, handler)

        await device.connect()
        try:
            await asyncio.sleep(0.1)
            handler.assert_called()
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_disconnected_event_on_disconnect(self, device: AsyncModbusDevice):
        """disconnect() 應發射 disconnected 事件"""
        handler = AsyncMock()
        device.on(EVENT_DISCONNECTED, handler)

        await device.connect()
        await device.disconnect()

        await asyncio.sleep(0.1)
        handler.assert_called()

    @pytest.mark.asyncio
    async def test_value_change_event(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """值變化應發射 value_change 事件"""
        handler = AsyncMock()
        device.on(EVENT_VALUE_CHANGE, handler)

        mock_client.read_holding_registers.return_value = [100, 200, 300]

        await device.connect()
        await device.start()
        try:
            await asyncio.sleep(0.2)
            assert handler.call_count >= 1  # 至少有一次值變化
        finally:
            await device.stop()
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_read_complete_event(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """讀取完成應發射 read_complete 事件"""
        handler = AsyncMock()
        device.on(EVENT_READ_COMPLETE, handler)

        mock_client.read_holding_registers.return_value = [100, 200, 300]

        await device.connect()
        await device.start()
        try:
            await asyncio.sleep(0.2)
            assert handler.call_count >= 1
        finally:
            await device.stop()
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_read_error_event_on_failure(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """讀取失敗應發射 read_error 事件"""
        handler = AsyncMock()
        device.on(EVENT_READ_ERROR, handler)

        mock_client.read_holding_registers.side_effect = Exception("Connection lost")

        await device.connect()
        await device.start()
        try:
            await asyncio.sleep(0.2)
            assert handler.call_count >= 1
        finally:
            await device.stop()
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_write_complete_event(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """寫入成功應發射 write_complete 事件"""
        handler = AsyncMock()
        device.on(EVENT_WRITE_COMPLETE, handler)

        await device.connect()
        try:
            await device.write("setpoint", 50)
            await asyncio.sleep(0.1)
            handler.assert_called()
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_alarm_triggered_event(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """告警觸發應發射 alarm_triggered 事件"""
        handler = AsyncMock()
        device.on(EVENT_ALARM_TRIGGERED, handler)

        mock_client.read_holding_registers.return_value = [100, 200, 300]

        await device.connect()
        await device.start()
        try:
            await asyncio.sleep(0.2)
            handler.assert_called()
        finally:
            await device.stop()
            await device.disconnect()


# ======================== State Tests ========================


class TestAsyncModbusDeviceState:
    """狀態屬性測試"""

    @pytest.mark.asyncio
    async def test_is_healthy_when_all_good(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """健康狀態：已連線、有回應、無保護告警"""
        mock_client.read_holding_registers.return_value = [50, 200, 300]  # power=50，不觸發告警

        await device.connect()
        await device.start()
        try:
            await asyncio.sleep(0.2)
            assert device.is_healthy is True
        finally:
            await device.stop()
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_is_unreachable_after_failures(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """連續失敗後 is_unreachable 應為 True"""
        mock_client.read_holding_registers.side_effect = Exception("Timeout")

        await device.connect()
        await device.start()
        try:
            # 等待超過 disconnect_threshold (3) 次失敗
            await asyncio.sleep(0.5)
            assert device.is_unreachable is True
        finally:
            await device.stop()
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_recovery_after_unreachable(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """設備恢復後 is_responsive 應恢復"""
        call_count = 0

        async def flaky_read(address, count, unit_id=1):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise Exception("Timeout")
            return [50, 200, 300]

        mock_client.read_holding_registers.side_effect = flaky_read

        await device.connect()
        await device.start()
        try:
            # 等待失敗後恢復
            await asyncio.sleep(0.6)
            assert device.is_responsive is True
        finally:
            await device.stop()
            await device.disconnect()


# ======================== Performance Tests ========================


class TestAsyncModbusDevicePerformance:
    """性能測試"""

    @pytest.mark.asyncio
    async def test_read_loop_timing_accuracy(self, mock_client: AsyncMock):
        """讀取循環間隔應精確"""
        config = DeviceConfig(
            device_id="perf_test",
            read_interval=0.1,  # 100ms 間隔
            disconnect_threshold=3,
        )
        device = AsyncModbusDevice(
            config=config,
            client=mock_client,
            always_points=[ReadPoint(name="test", address=100, data_type=UInt16())],
        )

        mock_client.read_holding_registers.return_value = [100]

        await device.connect()
        await device.start()

        try:
            start = time.monotonic()
            await asyncio.sleep(1.0)  # 執行 1 秒
            elapsed = time.monotonic() - start

            # 1 秒內應有約 10 次讀取 (100ms 間隔)
            call_count = mock_client.read_holding_registers.call_count
            expected = int(elapsed / 0.1)

            # 允許 ±2 的誤差
            assert abs(call_count - expected) <= 2, f"Expected ~{expected} reads, got {call_count}"
        finally:
            await device.stop()
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_event_throughput(self, mock_client: AsyncMock):
        """事件處理吞吐量測試"""
        config = DeviceConfig(
            device_id="throughput_test",
            read_interval=0.01,  # 10ms 間隔 - 高頻
            disconnect_threshold=3,
        )
        device = AsyncModbusDevice(
            config=config,
            client=mock_client,
            always_points=[ReadPoint(name="test", address=100, data_type=UInt16())],
        )

        event_count = 0

        async def counter(payload):
            nonlocal event_count
            event_count += 1

        device.on(EVENT_READ_COMPLETE, counter)

        # 模擬不同值以觸發 value_change
        call_count = 0

        def varying_read(address, count, unit_id=1):
            nonlocal call_count
            call_count += 1
            return [call_count % 100]

        mock_client.read_holding_registers.side_effect = varying_read

        await device.connect()
        await device.start()

        try:
            await asyncio.sleep(1.0)

            # 高頻讀取應能處理大量事件
            assert event_count >= 50, f"Expected >= 50 events, got {event_count}"
        finally:
            await device.stop()
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_memory_stability_long_running(self, mock_client: AsyncMock):
        """長時間運行記憶體穩定性"""
        import gc

        config = DeviceConfig(
            device_id="memory_test",
            read_interval=0.01,
            disconnect_threshold=3,
        )
        device = AsyncModbusDevice(
            config=config,
            client=mock_client,
            always_points=[ReadPoint(name="test", address=100, data_type=UInt16())],
        )

        mock_client.read_holding_registers.return_value = [100]

        await device.connect()
        await device.start()

        try:
            # 運行一段時間
            await asyncio.sleep(2.0)

            # 強制 GC
            gc.collect()

            # 佇列大小應保持可控
            queue_size = device._emitter.queue_size
            assert queue_size < 100, f"Queue size {queue_size} is too large"
        finally:
            await device.stop()
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_concurrent_write_operations(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """並行寫入操作"""
        await device.connect()

        try:
            # 同時發起多個寫入
            tasks = [device.write("setpoint", i) for i in range(10, 20)]

            results = await asyncio.gather(*tasks)

            # 所有寫入應成功
            for result in results:
                assert result.status == WriteStatus.SUCCESS
        finally:
            await device.disconnect()


# ======================== Edge Cases ========================


# ======================== Should Attempt Read Tests ========================


class TestAsyncModbusDeviceShouldAttemptRead:
    """should_attempt_read 屬性測試"""

    def test_initially_true(self, device: AsyncModbusDevice):
        """初始狀態應為 True（尚未失敗過）"""
        assert device.should_attempt_read is True

    @pytest.mark.asyncio
    async def test_true_when_responsive(self, device: AsyncModbusDevice):
        """設備回應中應為 True"""
        await device.connect()
        try:
            assert device._device_responsive is True
            assert device.should_attempt_read is True
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_false_after_threshold_failures(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """超過失敗閾值後應為 False（在重試間隔內）"""
        mock_client.read_holding_registers.side_effect = Exception("Timeout")

        await device.connect()
        try:
            # 讀取直到超過 disconnect_threshold (3)
            for _ in range(4):
                try:
                    await device.read_once()
                except Exception:
                    pass

            assert device._device_responsive is False
            assert device._last_failure_time is not None
            assert device.should_attempt_read is False
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_true_after_reconnect_interval(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """超過重試間隔後應恢復為 True"""
        mock_client.read_holding_registers.side_effect = Exception("Timeout")

        await device.connect()
        try:
            for _ in range(4):
                try:
                    await device.read_once()
                except Exception:
                    pass

            assert device.should_attempt_read is False

            # 模擬時間流逝（將 _last_failure_time 設為過去）
            device._last_failure_time = time.monotonic() - device._config.reconnect_interval - 1
            assert device.should_attempt_read is True
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_reset_on_successful_read(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """成功讀取後 _last_failure_time 應重置"""
        mock_client.read_holding_registers.side_effect = Exception("Timeout")

        await device.connect()
        try:
            # 製造失敗
            try:
                await device.read_once()
            except Exception:
                pass

            assert device._last_failure_time is not None

            # 恢復正常
            mock_client.read_holding_registers.side_effect = None
            mock_client.read_holding_registers.return_value = [100, 200, 300]
            await device.read_once()

            assert device._last_failure_time is None
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_reset_on_disconnect(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """正常斷線後 _last_failure_time 應重置"""
        mock_client.read_holding_registers.side_effect = Exception("Timeout")

        await device.connect()
        try:
            await device.read_once()
        except Exception:
            pass

        assert device._last_failure_time is not None

        await device.disconnect()
        assert device._last_failure_time is None

    @pytest.mark.asyncio
    async def test_failure_time_set_on_reconnect_failure(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """重連失敗也應設置 _last_failure_time"""
        await device.connect()
        # 模擬斷線狀態
        device._client_connected = False
        device._device_responsive = False

        mock_client.connect.side_effect = Exception("Connection refused")

        try:
            await device.read_once()
        except Exception:
            pass

        assert device._last_failure_time is not None
        assert device.should_attempt_read is False


# ======================== Edge Cases ========================


class TestAsyncModbusDeviceEdgeCases:
    """邊界條件測試"""

    @pytest.mark.asyncio
    async def test_double_connect(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """重複 connect 應處理正確"""
        await device.connect()
        await device.connect()  # 第二次

        try:
            assert device.is_connected is True
            # client.connect 可能被呼叫兩次（取決於實作）
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_double_disconnect(self, device: AsyncModbusDevice):
        """重複 disconnect 不應報錯"""
        await device.connect()
        await device.disconnect()
        await device.disconnect()  # 第二次不應報錯

    @pytest.mark.asyncio
    async def test_stop_without_start(self, device: AsyncModbusDevice):
        """未 start 時 stop 不應報錯"""
        await device.connect()
        try:
            await device.stop()  # 不應報錯
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_empty_read_points(self, mock_client: AsyncMock, device_config: DeviceConfig):
        """無讀取點位應正常運作"""
        device = AsyncModbusDevice(
            config=device_config,
            client=mock_client,
            always_points=[],
        )

        await device.connect()
        try:
            values = await device.read_once()
            assert values == {}
        finally:
            await device.disconnect()

    @pytest.mark.asyncio
    async def test_context_manager_exception_cleanup(self, mock_client: AsyncMock, device_config: DeviceConfig):
        """context manager 異常時應清理"""
        device = AsyncModbusDevice(
            config=device_config,
            client=mock_client,
            always_points=[ReadPoint(name="test", address=100, data_type=UInt16())],
        )

        mock_client.read_holding_registers.side_effect = Exception("Fatal error")

        try:
            async with device:
                await asyncio.sleep(0.2)
        except Exception:
            pass

        # 應已正確清理
        assert device.is_connected is False
        assert device.is_running is False
