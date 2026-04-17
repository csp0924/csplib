# =============== SystemController attach_read_trigger Tests (v0.8.0 WI-V080-005) ===============
#
# 驗證 SystemController.attach_read_trigger(device_id) 的行為：
#   - 未註冊設備 → fail-fast ValueError
#   - 重複 attach 同一設備 → fail-fast ValueError
#   - EVENT_READ_COMPLETE 觸發 executor.trigger
#   - detacher 後不再觸發
#   - Builder .trigger_on_read_complete(device_id) auto-attach
#   - _on_stop 先 detach 再停 executor（順序驗證）

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.equipment.device import EVENT_READ_COMPLETE
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.system_controller import (
    SystemController,
    SystemControllerConfig,
)

# =============== Helpers ===============


def _make_device(device_id: str) -> MagicMock:
    """建立 mock device，on() 會真實管理 handler 並支援 emit 模擬"""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=True)
    type(dev).is_responsive = PropertyMock(return_value=True)
    type(dev).is_protected = PropertyMock(return_value=False)
    type(dev).is_healthy = PropertyMock(return_value=True)
    type(dev).latest_values = PropertyMock(return_value={})
    type(dev).active_alarms = PropertyMock(return_value=[])
    dev.write = AsyncMock()

    # 支援註冊 handler + 模擬 emit
    handlers: dict[str, list] = {}

    def _on(event: str, handler):
        handlers.setdefault(event, []).append(handler)

        def _detacher():
            if event in handlers and handler in handlers[event]:
                handlers[event].remove(handler)

        return _detacher

    dev.on = MagicMock(side_effect=_on)
    dev._test_handlers = handlers  # 供測試直接呼叫

    def _health():
        return HealthReport(
            status=HealthStatus.HEALTHY,
            component=f"device:{device_id}",
            details={"connected": True, "responsive": True, "protected": False, "active_alarms": 0},
        )

    dev.health = _health
    return dev


async def _simulate_read_complete(dev: MagicMock) -> None:
    """模擬設備發出 EVENT_READ_COMPLETE，逐一 await 各 handler"""
    handlers = dev._test_handlers.get(EVENT_READ_COMPLETE, [])
    for h in handlers:
        await h(None)


class _Strategy(Strategy):
    def __init__(self, mode: ExecutionMode = ExecutionMode.TRIGGERED) -> None:
        self._mode = mode
        self.execute_count = 0

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=self._mode, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        self.execute_count += 1
        return Command()


# =============== fail-fast 驗證 ===============


class TestAttachReadTriggerValidation:
    """attach_read_trigger 的 fail-fast 驗證"""

    def test_attach_unknown_device_raises(self):
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig())
        with pytest.raises(ValueError, match="not found in registry"):
            sc.attach_read_trigger("ghost")

    def test_duplicate_attach_raises(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev)
        sc = SystemController(reg, SystemControllerConfig())

        sc.attach_read_trigger("d1")
        with pytest.raises(ValueError, match="already attached"):
            sc.attach_read_trigger("d1")


# =============== EVENT_READ_COMPLETE → executor.trigger ===============


class TestReadCompleteTriggersExecutor:
    """綁定後 EVENT_READ_COMPLETE 應觸發 executor.trigger"""

    async def test_read_complete_triggers_executor(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev)
        sc = SystemController(reg, SystemControllerConfig())

        # Spy executor.trigger
        trigger_calls: list[None] = []
        original_trigger = sc.executor.trigger

        def spy_trigger():
            trigger_calls.append(None)
            return original_trigger()

        sc.executor.trigger = spy_trigger  # type: ignore[method-assign]

        sc.attach_read_trigger("d1")
        await _simulate_read_complete(dev)

        assert len(trigger_calls) == 1

    async def test_detacher_stops_future_triggers(self):
        """detacher 呼叫後再 emit EVENT_READ_COMPLETE 不再觸發"""
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev)
        sc = SystemController(reg, SystemControllerConfig())

        trigger_calls: list[None] = []
        sc.executor.trigger = lambda: trigger_calls.append(None)  # type: ignore[method-assign]

        detacher = sc.attach_read_trigger("d1")
        await _simulate_read_complete(dev)
        assert len(trigger_calls) == 1

        # Detach 後再發事件
        detacher()
        await _simulate_read_complete(dev)
        assert len(trigger_calls) == 1, "Detacher 後不應再觸發"

    async def test_detacher_releases_device_id_slot(self):
        """detacher 後再次 attach 同一 device_id 應成功（slot 已釋放）"""
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev)
        sc = SystemController(reg, SystemControllerConfig())

        detacher = sc.attach_read_trigger("d1")
        detacher()

        # 再 attach 不應拋 ValueError
        detacher2 = sc.attach_read_trigger("d1")
        detacher2()


# =============== Builder auto-attach ===============


class TestBuilderAutoAttach:
    """builder.trigger_on_read_complete(device_id) 啟動時 auto-attach"""

    async def test_trigger_on_read_complete_auto_attaches_on_start(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev)

        config = SystemControllerConfig.builder().trigger_on_read_complete("d1").build()
        sc = SystemController(reg, config)

        trigger_calls: list[None] = []
        sc.executor.trigger = lambda: trigger_calls.append(None)  # type: ignore[method-assign]

        async with asyncio.timeout(3):
            await sc.start()
            try:
                # 確認 attach 生效 — 模擬讀取完成
                await _simulate_read_complete(dev)
                assert len(trigger_calls) >= 1
            finally:
                await sc.stop()

    async def test_auto_attach_with_unknown_device_logs_warning_and_continues(self):
        """config 裡的 device_id 未註冊 → log warning，不阻斷啟動"""
        reg = DeviceRegistry()
        # 沒註冊任何 device
        config = SystemControllerConfig.builder().trigger_on_read_complete("ghost").build()
        sc = SystemController(reg, config)

        async with asyncio.timeout(3):
            await sc.start()
            try:
                assert sc.is_running
            finally:
                await sc.stop()


# =============== _on_stop 先 detach ===============


class TestStopDetachOrder:
    """_on_stop 必須先呼叫 auto-attach 的 detacher，再停 executor

    驗證方式：在 detacher 與 executor.stop 上各加 spy，檢查呼叫順序。
    """

    async def test_on_stop_calls_detacher_before_executor_stop(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev)

        config = SystemControllerConfig.builder().trigger_on_read_complete("d1").build()
        sc = SystemController(reg, config)

        call_order: list[str] = []

        # Spy executor.stop
        original_executor_stop = sc.executor.stop

        def spy_executor_stop():
            call_order.append("executor.stop")
            return original_executor_stop()

        sc.executor.stop = spy_executor_stop  # type: ignore[method-assign]

        async with asyncio.timeout(3):
            await sc.start()
            # 此時 _auto_trigger_detachers 裡有 1 個 detacher

            # Wrap detacher spy
            assert len(sc._auto_trigger_detachers) == 1
            original_detacher = sc._auto_trigger_detachers[0]

            def spy_detacher():
                call_order.append("detacher")
                original_detacher()

            sc._auto_trigger_detachers[0] = spy_detacher

            await sc.stop()

        # 檢查順序：detacher 必先於 executor.stop
        assert call_order.index("detacher") < call_order.index("executor.stop"), (
            f"detacher 應在 executor.stop 之前被呼叫，實際 order={call_order}"
        )

    async def test_on_stop_clears_auto_trigger_detachers(self):
        """_on_stop 結束後 _auto_trigger_detachers 應清空"""
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev)

        config = SystemControllerConfig.builder().trigger_on_read_complete("d1").build()
        sc = SystemController(reg, config)

        async with asyncio.timeout(3):
            await sc.start()
            assert len(sc._auto_trigger_detachers) == 1
            await sc.stop()
            assert sc._auto_trigger_detachers == []


# =============== 多設備並存 ===============


class TestMultipleDevicesAttach:
    """多個設備同時 attach 各自獨立運作"""

    async def test_multiple_devices_each_trigger_once(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1")
        d2 = _make_device("d2")
        reg.register(d1)
        reg.register(d2)
        sc = SystemController(reg, SystemControllerConfig())

        trigger_calls: list[None] = []
        sc.executor.trigger = lambda: trigger_calls.append(None)  # type: ignore[method-assign]

        sc.attach_read_trigger("d1")
        sc.attach_read_trigger("d2")

        await _simulate_read_complete(d1)
        await _simulate_read_complete(d2)
        await _simulate_read_complete(d1)

        assert len(trigger_calls) == 3
