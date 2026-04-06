"""Pipeline 整合測試：Strategy → Protection → Compensator → Router 端到端。

驗證 SystemController 的完整命令流：
  1. ContextBuilder 建構 StrategyContext
  2. StrategyExecutor 執行策略產出 Command
  3. ProtectionGuard 套用保護規則
  4. CommandProcessor（如 PowerCompensator）後處理
  5. CommandRouter 將最終 Command 寫入設備
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system import (
    DynamicSOCProtection,
    ModePriority,
    SOCProtection,
    SOCProtectionConfig,
)
from csp_lib.core.runtime_params import RuntimeParameters
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CommandMapping, ContextMapping
from csp_lib.integration.system_controller import SystemController, SystemControllerConfig

# ─────────────── Helpers ───────────────


def _make_device(
    device_id: str,
    values: dict | None = None,
    responsive: bool = True,
    protected: bool = False,
    connected: bool = True,
) -> MagicMock:
    """建立 mock 設備，複用 test_system_controller.py 的模式。"""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=connected)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    type(dev).is_healthy = PropertyMock(return_value=connected and responsive and not protected)
    type(dev).latest_values = PropertyMock(return_value=values or {})
    type(dev).active_alarms = PropertyMock(return_value=[])
    dev.write = AsyncMock()
    unsub_fn = MagicMock()
    dev.on = MagicMock(return_value=unsub_fn)
    return dev


class MockStrategy(Strategy):
    """可控制回傳 Command 的 mock 策略。"""

    def __init__(self, return_command: Command | None = None, mode: ExecutionMode = ExecutionMode.TRIGGERED):
        self._return_command = return_command or Command()
        self._mode = mode
        self.execute_count = 0
        self.activated = False
        self.deactivated = False

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=self._mode, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        self.execute_count += 1
        return self._return_command

    async def on_activate(self) -> None:
        self.activated = True

    async def on_deactivate(self) -> None:
        self.deactivated = True


class MockCompensator:
    """
    Mock CommandProcessor：對 p_target 施加固定偏移。

    用於驗證 post_protection_processors 管線是否被正確呼叫。
    """

    def __init__(self, p_offset: float = 0.0, q_offset: float = 0.0):
        self._p_offset = p_offset
        self._q_offset = q_offset
        self.process_count = 0
        self.last_input_command: Command | None = None

    async def process(self, command: Command, context: StrategyContext) -> Command:
        self.process_count += 1
        self.last_input_command = command
        new_p = command.p_target + self._p_offset
        new_q = command.q_target + self._q_offset
        return command.with_p(new_p).with_q(new_q)


class FailingProcessor:
    """故意拋出例外的 processor，驗證 pipeline 的容錯行為。"""

    async def process(self, command: Command, context: StrategyContext) -> Command:
        raise RuntimeError("processor 爆炸")


async def _run_one_cycle(sc: SystemController) -> None:
    """啟動 SystemController、觸發一次執行、等待完成後停止。"""
    async with asyncio.timeout(5):
        await sc.start()
        sc.trigger()
        await asyncio.sleep(0.1)
        await sc.stop()


# ─────────────── 場景一：基本流程 ───────────────


class TestBasicPipeline:
    """Strategy 產出 P/Q command → Protection 通過 → Router 寫入設備。"""

    async def test_pq_command_flows_to_device(self):
        """正常 SOC 時，策略產出的 P/Q 值完整寫入設備。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
                CommandMapping(command_field="q_target", point_name="q_set", device_id="pcs1"),
            ],
            protection_rules=[SOCProtection(SOCProtectionConfig())],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=300.0, q_target=100.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        await _run_one_cycle(sc)

        # P 和 Q 都應寫入設備
        dev.write.assert_any_await("p_set", 300.0)
        dev.write.assert_any_await("q_set", 100.0)
        assert strategy.execute_count >= 1

    async def test_zero_command_still_writes(self):
        """策略產出 P=0, Q=0 時仍然寫入設備（不被跳過）。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=0.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        await _run_one_cycle(sc)

        # CommandRouter 只在 value is None 時跳過，0.0 應寫入
        # 注意：Command.p_target 預設為 0.0，getattr 回傳 0.0（非 None）
        # 但 CommandRouter 用 `if value is None: continue` 判斷
        dev.write.assert_awaited_with("p_set", 0.0)

    async def test_multi_device_routing(self):
        """多設備映射：同一 command field 寫入不同設備。"""
        reg = DeviceRegistry()
        dev1 = _make_device("pcs1", {"soc": 50.0})
        dev2 = _make_device("pcs2", {"soc": 50.0})
        reg.register(dev1)
        reg.register(dev2)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs2"),
            ],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=200.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        await _run_one_cycle(sc)

        dev1.write.assert_any_await("p_set", 200.0)
        dev2.write.assert_any_await("p_set", 200.0)


# ─────────────── 場景二：Protection 限制 ───────────────


class TestProtectionClamp:
    """Strategy 產出超限 command → Protection 削減 → Router 寫入削減後的值。"""

    async def test_soc_high_clamps_charging(self):
        """SOC 超高（96%）→ 充電命令被 clamp 到 0。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 96.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
                CommandMapping(command_field="q_target", point_name="q_set", device_id="pcs1"),
            ],
            protection_rules=[SOCProtection(SOCProtectionConfig(soc_high=95.0))],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        # P=-500 是充電，SOC=96% > soc_high=95% → clamp P to 0
        strategy = MockStrategy(Command(p_target=-500.0, q_target=100.0))
        sc.register_mode("charge", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("charge")

        await _run_one_cycle(sc)

        # P 被 clamp 到 0，Q 不受影響
        dev.write.assert_any_await("p_set", 0.0)
        dev.write.assert_any_await("q_set", 100.0)
        # 保護狀態被追蹤
        assert sc.protection_status is not None
        assert sc.protection_status.was_modified is True

    async def test_soc_low_clamps_discharging(self):
        """SOC 過低（3%）→ 放電命令被 clamp 到 0。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 3.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            protection_rules=[SOCProtection(SOCProtectionConfig(soc_low=5.0))],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        # P=500 是放電，SOC=3% < soc_low=5% → clamp P to 0
        strategy = MockStrategy(Command(p_target=500.0))
        sc.register_mode("discharge", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("discharge")

        await _run_one_cycle(sc)

        dev.write.assert_awaited_with("p_set", 0.0)

    async def test_warning_zone_gradual_limit(self):
        """SOC 在警戒區（92%，soc_high=95%, warning_band=5%）→ 充電被漸進限制。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 92.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            protection_rules=[SOCProtection(SOCProtectionConfig(soc_high=95.0, warning_band=5.0))],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        # P=-1000 充電，SOC=92% 在 warning zone [90%, 95%)
        # ratio = (95 - 92) / 5 = 0.6 → limited_p = -1000 * 0.6 = -600
        strategy = MockStrategy(Command(p_target=-1000.0))
        sc.register_mode("charge", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("charge")

        await _run_one_cycle(sc)

        dev.write.assert_awaited_with("p_set", -600.0)

    async def test_normal_soc_no_modification(self):
        """SOC 正常（50%）→ 命令不被修改。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            protection_rules=[SOCProtection(SOCProtectionConfig())],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=800.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        await _run_one_cycle(sc)

        dev.write.assert_awaited_with("p_set", 800.0)
        assert sc.protection_status.was_modified is False


# ─────────────── 場景三：Protection 阻擋 ───────────────


class TestProtectionBlock:
    """SOC 極端值 → Protection 阻擋充/放電命令 → Router 寫入 0。"""

    async def test_soc_at_boundary_blocks_charge(self):
        """SOC 剛好等於 soc_high → 充電被完全阻擋。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 95.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            protection_rules=[SOCProtection(SOCProtectionConfig(soc_high=95.0))],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=-200.0))
        sc.register_mode("charge", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("charge")

        await _run_one_cycle(sc)

        dev.write.assert_awaited_with("p_set", 0.0)

    async def test_soc_at_boundary_blocks_discharge(self):
        """SOC 剛好等於 soc_low → 放電被完全阻擋。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 5.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            protection_rules=[SOCProtection(SOCProtectionConfig(soc_low=5.0))],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=200.0))
        sc.register_mode("discharge", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("discharge")

        await _run_one_cycle(sc)

        dev.write.assert_awaited_with("p_set", 0.0)

    async def test_discharge_allowed_when_soc_high(self):
        """SOC 超高但策略要放電 → 不阻擋（SOC protection 只擋充電）。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 98.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            protection_rules=[SOCProtection(SOCProtectionConfig(soc_high=95.0))],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        # P=300 是放電，即使 SOC 很高也不應被阻擋
        strategy = MockStrategy(Command(p_target=300.0))
        sc.register_mode("discharge", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("discharge")

        await _run_one_cycle(sc)

        dev.write.assert_awaited_with("p_set", 300.0)


# ─────────────── 場景四：Compensator 修正 ───────────────


class TestCompensatorPipeline:
    """Strategy 產出 command → CommandProcessor 修正 → Router 寫入修正值。"""

    async def test_compensator_adjusts_p_target(self):
        """Compensator 對 P 施加 +50 偏移。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0})
        reg.register(dev)

        compensator = MockCompensator(p_offset=50.0)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            post_protection_processors=[compensator],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=200.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        await _run_one_cycle(sc)

        # 策略產出 200 → compensator 加 50 → 設備寫入 250
        dev.write.assert_awaited_with("p_set", 250.0)
        assert compensator.process_count >= 1

    async def test_compensator_after_protection(self):
        """Protection 先削減，再由 compensator 修正削減後的值。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 92.0})
        reg.register(dev)

        compensator = MockCompensator(p_offset=10.0)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            protection_rules=[SOCProtection(SOCProtectionConfig(soc_high=95.0, warning_band=5.0))],
            post_protection_processors=[compensator],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        # P=-1000 充電，SOC=92% → ratio=0.6 → protection 後 P=-600
        # compensator 加 10 → 最終 P=-590
        strategy = MockStrategy(Command(p_target=-1000.0))
        sc.register_mode("charge", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("charge")

        await _run_one_cycle(sc)

        # 驗證 compensator 收到的是 protection 後的值
        assert compensator.last_input_command is not None
        assert compensator.last_input_command.p_target == pytest.approx(-600.0)
        # 設備收到 compensator 修正後的值
        dev.write.assert_awaited_with("p_set", pytest.approx(-590.0))

    async def test_multiple_processors_chained(self):
        """多個 processor 鏈式執行：第一個加 50，第二個乘以 2（用偏移模擬）。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0})
        reg.register(dev)

        proc1 = MockCompensator(p_offset=50.0)  # 200 → 250
        proc2 = MockCompensator(p_offset=250.0)  # 250 → 500

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            post_protection_processors=[proc1, proc2],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=200.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        await _run_one_cycle(sc)

        # proc1: 200 + 50 = 250，proc2: 250 + 250 = 500
        dev.write.assert_awaited_with("p_set", 500.0)
        assert proc1.process_count >= 1
        assert proc2.process_count >= 1

    async def test_failing_processor_skipped(self):
        """Processor 拋出例外時被跳過，後續 processor 和 router 正常執行。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0})
        reg.register(dev)

        failing = FailingProcessor()
        compensator = MockCompensator(p_offset=10.0)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            post_protection_processors=[failing, compensator],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=200.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        await _run_one_cycle(sc)

        # failing processor 被跳過，compensator 收到原始值 200，加 10 = 210
        dev.write.assert_awaited_with("p_set", 210.0)
        assert compensator.process_count >= 1


# ─────────────── 場景五：Mode Switch ───────────────


class TestModeSwitch:
    """切換策略模式 → 新策略執行 → 正確 command 寫入。"""

    async def test_switch_mode_changes_output(self):
        """從 PQ 模式切換到停機模式，設備收到不同的 command。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)

        s_pq = MockStrategy(Command(p_target=500.0))
        s_stop = MockStrategy(Command(p_target=0.0))
        sc.register_mode("pq", s_pq, ModePriority.SCHEDULE)
        sc.register_mode("stop", s_stop, ModePriority.MANUAL)

        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)

            # 驗證 PQ 模式寫入
            dev.write.assert_any_await("p_set", 500.0)
            assert s_pq.execute_count >= 1

            # 切換到 stop override，等待 executor loop 重新進入 wait
            dev.write.reset_mock()
            await sc.push_override("stop")
            await asyncio.sleep(0.05)  # 讓 executor loop 處理 strategy_changed_event
            sc.trigger()
            await asyncio.sleep(0.15)

            # 驗證停機模式寫入
            dev.write.assert_awaited_with("p_set", 0.0)
            assert s_stop.execute_count >= 1

            await sc.stop()

    async def test_pop_override_restores_base(self):
        """Override 彈出後恢復 base mode。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)

        s_pq = MockStrategy(Command(p_target=500.0))
        s_override = MockStrategy(Command(p_target=0.0))
        sc.register_mode("pq", s_pq, ModePriority.SCHEDULE)
        sc.register_mode("emergency", s_override, ModePriority.MANUAL)

        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()

            # Push override，等待 executor loop 處理 strategy change
            await sc.push_override("emergency")
            await asyncio.sleep(0.05)
            sc.trigger()
            await asyncio.sleep(0.15)
            dev.write.assert_awaited_with("p_set", 0.0)

            # Pop override → 回到 pq
            dev.write.reset_mock()
            await sc.pop_override("emergency")
            await asyncio.sleep(0.05)
            sc.trigger()
            await asyncio.sleep(0.15)
            dev.write.assert_awaited_with("p_set", 500.0)

            await sc.stop()

    async def test_mode_switch_with_protection_and_compensator(self):
        """模式切換後，protection 和 compensator 對新模式的 command 生效。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 96.0})
        reg.register(dev)

        compensator = MockCompensator(p_offset=10.0)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            protection_rules=[SOCProtection(SOCProtectionConfig(soc_high=95.0))],
            post_protection_processors=[compensator],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)

        # 模式 A：充電 → SOC 超高會被 protection clamp 到 0 → compensator 加 10 → 寫入 10
        s_charge = MockStrategy(Command(p_target=-500.0))
        # 模式 B：放電 → SOC 超高不影響放電 → 300 + 10 = 310
        s_discharge = MockStrategy(Command(p_target=300.0))
        sc.register_mode("charge", s_charge, ModePriority.SCHEDULE)
        sc.register_mode("discharge", s_discharge, ModePriority.MANUAL)

        await sc.set_base_mode("charge")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)

            # 充電模式：P=-500 → protection clamp 0 → compensator +10 → 寫入 10
            dev.write.assert_awaited_with("p_set", 10.0)

            # 切換到放電模式，等待 executor loop 處理 strategy change
            dev.write.reset_mock()
            await sc.push_override("discharge")
            await asyncio.sleep(0.05)
            sc.trigger()
            await asyncio.sleep(0.15)

            # 放電模式：P=300 → protection 不介入 → compensator +10 → 寫入 310
            dev.write.assert_awaited_with("p_set", 310.0)

            await sc.stop()


# ─────────────── 場景六：DynamicSOCProtection + RuntimeParameters ───────────────


class TestDynamicProtectionPipeline:
    """使用 DynamicSOCProtection 搭配 RuntimeParameters 的端到端測試。"""

    async def test_dynamic_soc_protection_with_runtime_params(self):
        """RuntimeParameters 動態設定 SOC 上限，protection 正確套用。"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 92.0})
        reg.register(dev)

        params = RuntimeParameters()
        params.set("soc_max", 90.0)  # 動態上限設為 90%
        params.set("soc_min", 10.0)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            protection_rules=[DynamicSOCProtection(params)],
            runtime_params=params,
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        # SOC=92% > soc_max=90% → 充電被 clamp 到 0
        strategy = MockStrategy(Command(p_target=-500.0))
        sc.register_mode("charge", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("charge")

        await _run_one_cycle(sc)

        dev.write.assert_awaited_with("p_set", 0.0)
