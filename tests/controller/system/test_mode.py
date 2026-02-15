"""Tests for ModeManager."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system.mode import ModeDefinition, ModeManager, ModePriority


class MockStrategy(Strategy):
    def __init__(self, name: str = "mock"):
        self._name = name

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command()

    def __repr__(self) -> str:
        return f"MockStrategy({self._name})"


class TestModeManagerRegister:
    def test_register_mode(self):
        mm = ModeManager()
        s = MockStrategy()
        mm.register("pq", s, ModePriority.SCHEDULE, "PQ mode")
        assert "pq" in mm.registered_modes
        mode = mm.registered_modes["pq"]
        assert mode.name == "pq"
        assert mode.strategy is s
        assert mode.priority == ModePriority.SCHEDULE
        assert mode.description == "PQ mode"

    def test_register_duplicate_raises(self):
        mm = ModeManager()
        mm.register("pq", MockStrategy(), ModePriority.SCHEDULE)
        with pytest.raises(ValueError, match="already registered"):
            mm.register("pq", MockStrategy(), ModePriority.MANUAL)

    def test_unregister_mode(self):
        mm = ModeManager()
        mm.register("pq", MockStrategy(), ModePriority.SCHEDULE)
        mm.unregister("pq")
        assert "pq" not in mm.registered_modes

    def test_unregister_not_registered_raises(self):
        mm = ModeManager()
        with pytest.raises(KeyError, match="not registered"):
            mm.unregister("nonexistent")

    @pytest.mark.asyncio
    async def test_unregister_clears_base_mode(self):
        mm = ModeManager()
        mm.register("pq", MockStrategy(), ModePriority.SCHEDULE)
        await mm.set_base_mode("pq")
        mm.unregister("pq")
        assert mm.base_mode_name is None

    @pytest.mark.asyncio
    async def test_unregister_clears_override(self):
        mm = ModeManager()
        mm.register("stop", MockStrategy(), ModePriority.PROTECTION)
        await mm.push_override("stop")
        mm.unregister("stop")
        assert mm.active_override_names == []


class TestModeManagerBaseMode:
    @pytest.mark.asyncio
    async def test_set_base_mode(self):
        mm = ModeManager()
        s = MockStrategy()
        mm.register("pq", s, ModePriority.SCHEDULE)
        await mm.set_base_mode("pq")
        assert mm.base_mode_name == "pq"
        assert mm.effective_strategy is s

    @pytest.mark.asyncio
    async def test_set_base_mode_none(self):
        mm = ModeManager()
        mm.register("pq", MockStrategy(), ModePriority.SCHEDULE)
        await mm.set_base_mode("pq")
        await mm.set_base_mode(None)
        assert mm.base_mode_name is None
        assert mm.effective_strategy is None

    @pytest.mark.asyncio
    async def test_set_base_mode_not_registered_raises(self):
        mm = ModeManager()
        with pytest.raises(KeyError, match="not registered"):
            await mm.set_base_mode("nonexistent")

    @pytest.mark.asyncio
    async def test_effective_mode_is_base_when_no_override(self):
        mm = ModeManager()
        s = MockStrategy()
        mm.register("pq", s, ModePriority.SCHEDULE)
        await mm.set_base_mode("pq")
        assert mm.effective_mode is not None
        assert mm.effective_mode.name == "pq"


class TestModeManagerOverride:
    @pytest.mark.asyncio
    async def test_push_override(self):
        mm = ModeManager()
        s_base = MockStrategy("base")
        s_override = MockStrategy("override")
        mm.register("base", s_base, ModePriority.SCHEDULE)
        mm.register("stop", s_override, ModePriority.PROTECTION)
        await mm.set_base_mode("base")
        await mm.push_override("stop")

        assert mm.active_override_names == ["stop"]
        assert mm.effective_strategy is s_override

    @pytest.mark.asyncio
    async def test_push_override_not_registered_raises(self):
        mm = ModeManager()
        with pytest.raises(KeyError, match="not registered"):
            await mm.push_override("nonexistent")

    @pytest.mark.asyncio
    async def test_push_override_duplicate_raises(self):
        mm = ModeManager()
        mm.register("stop", MockStrategy(), ModePriority.PROTECTION)
        await mm.push_override("stop")
        with pytest.raises(ValueError, match="already active"):
            await mm.push_override("stop")

    @pytest.mark.asyncio
    async def test_pop_override(self):
        mm = ModeManager()
        s_base = MockStrategy("base")
        s_override = MockStrategy("override")
        mm.register("base", s_base, ModePriority.SCHEDULE)
        mm.register("stop", s_override, ModePriority.PROTECTION)
        await mm.set_base_mode("base")
        await mm.push_override("stop")
        await mm.pop_override("stop")

        assert mm.active_override_names == []
        assert mm.effective_strategy is s_base

    @pytest.mark.asyncio
    async def test_pop_override_not_active_raises(self):
        mm = ModeManager()
        with pytest.raises(KeyError, match="not active"):
            await mm.pop_override("nonexistent")

    @pytest.mark.asyncio
    async def test_clear_overrides(self):
        mm = ModeManager()
        s_base = MockStrategy("base")
        mm.register("base", s_base, ModePriority.SCHEDULE)
        mm.register("o1", MockStrategy(), ModePriority.MANUAL)
        mm.register("o2", MockStrategy(), ModePriority.PROTECTION)
        await mm.set_base_mode("base")
        await mm.push_override("o1")
        await mm.push_override("o2")
        await mm.clear_overrides()

        assert mm.active_override_names == []
        assert mm.effective_strategy is s_base


class TestModeManagerPriority:
    @pytest.mark.asyncio
    async def test_highest_priority_override_wins(self):
        mm = ModeManager()
        s_low = MockStrategy("low")
        s_high = MockStrategy("high")
        mm.register("low", s_low, ModePriority.MANUAL)
        mm.register("high", s_high, ModePriority.PROTECTION)
        await mm.push_override("low")
        await mm.push_override("high")

        assert mm.effective_strategy is s_high

    @pytest.mark.asyncio
    async def test_override_higher_than_base(self):
        mm = ModeManager()
        s_base = MockStrategy("base")
        s_override = MockStrategy("override")
        mm.register("base", s_base, ModePriority.SCHEDULE)
        mm.register("manual", s_override, ModePriority.MANUAL)
        await mm.set_base_mode("base")
        await mm.push_override("manual")

        assert mm.effective_strategy is s_override

    @pytest.mark.asyncio
    async def test_pop_highest_falls_back_to_next(self):
        mm = ModeManager()
        s_low = MockStrategy("low")
        s_high = MockStrategy("high")
        mm.register("low", s_low, ModePriority.MANUAL)
        mm.register("high", s_high, ModePriority.PROTECTION)
        await mm.push_override("low")
        await mm.push_override("high")
        await mm.pop_override("high")

        assert mm.effective_strategy is s_low

    def test_no_mode_returns_none(self):
        mm = ModeManager()
        assert mm.effective_mode is None
        assert mm.effective_strategy is None


class TestModeManagerCallback:
    @pytest.mark.asyncio
    async def test_callback_on_base_mode_change(self):
        callback = AsyncMock()
        mm = ModeManager(on_strategy_change=callback)
        s = MockStrategy()
        mm.register("pq", s, ModePriority.SCHEDULE)

        await mm.set_base_mode("pq")
        callback.assert_awaited_once_with(None, s)

    @pytest.mark.asyncio
    async def test_callback_on_override_push(self):
        callback = AsyncMock()
        mm = ModeManager(on_strategy_change=callback)
        s_base = MockStrategy("base")
        s_override = MockStrategy("override")
        mm.register("base", s_base, ModePriority.SCHEDULE)
        mm.register("stop", s_override, ModePriority.PROTECTION)
        await mm.set_base_mode("base")
        callback.reset_mock()

        await mm.push_override("stop")
        callback.assert_awaited_once_with(s_base, s_override)

    @pytest.mark.asyncio
    async def test_callback_on_override_pop(self):
        callback = AsyncMock()
        mm = ModeManager(on_strategy_change=callback)
        s_base = MockStrategy("base")
        s_override = MockStrategy("override")
        mm.register("base", s_base, ModePriority.SCHEDULE)
        mm.register("stop", s_override, ModePriority.PROTECTION)
        await mm.set_base_mode("base")
        await mm.push_override("stop")
        callback.reset_mock()

        await mm.pop_override("stop")
        callback.assert_awaited_once_with(s_override, s_base)

    @pytest.mark.asyncio
    async def test_no_callback_when_strategy_unchanged(self):
        callback = AsyncMock()
        mm = ModeManager(on_strategy_change=callback)
        s = MockStrategy()
        mm.register("pq", s, ModePriority.SCHEDULE)
        mm.register("low_override", MockStrategy("low"), 5)
        await mm.set_base_mode("pq")
        callback.reset_mock()

        # Push an override with lower priority than base (SCHEDULE=10 > 5)
        # But override always wins over base regardless of priority
        # Let me use a proper scenario: push override that doesn't change effective
        # Actually, override always takes precedence over base, so this will change.
        # Better test: push second override when first override with higher priority exists.
        mm.register("high", MockStrategy("high"), ModePriority.PROTECTION)
        await mm.push_override("high")
        callback.reset_mock()

        # Now push low override - effective is still "high"
        await mm.push_override("low_override")
        callback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_callback_when_no_handler(self):
        mm = ModeManager()  # no callback
        mm.register("pq", MockStrategy(), ModePriority.SCHEDULE)
        # Should not raise
        await mm.set_base_mode("pq")


class TestModeDefinition:
    def test_frozen(self):
        s = MockStrategy()
        md = ModeDefinition(name="test", strategy=s, priority=10)
        with pytest.raises(AttributeError):
            md.name = "other"  # type: ignore[misc]

    def test_default_description(self):
        md = ModeDefinition(name="test", strategy=MockStrategy(), priority=10)
        assert md.description == ""
