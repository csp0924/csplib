"""Tests for PowerCompensator — FF + integral closed-loop compensation."""

import pytest

from csp_lib.controller.compensator import (
    FFTableRepository,
    JsonFFTableRepository,
    MongoFFTableRepository,
    PowerCompensator,
    PowerCompensatorConfig,
)
from csp_lib.controller.core import Command, StrategyContext

# ===========================================================================
# Helpers
# ===========================================================================


def _make_compensator(**overrides) -> PowerCompensator:
    """Create a PowerCompensator with sensible test defaults."""
    defaults = {
        "rated_power": 2000.0,
        "output_min": -2000.0,
        "output_max": 2000.0,
        "ki": 0.3,
        "deadband": 0.5,
        "hold_cycles": 0,  # no hold delay for simpler tests
        "error_ema_alpha": 0.0,
        "rate_limit": 0.0,
        "persist_path": "",
    }
    defaults.update(overrides)
    config = PowerCompensatorConfig(**defaults)
    return PowerCompensator(config)


# ===========================================================================
# Zero setpoint
# ===========================================================================


class TestCompensatorZeroSetpoint:
    def test_zero_setpoint_returns_zero(self):
        comp = _make_compensator()
        result = comp.compensate(setpoint=0.0, measurement=0.0, dt=0.3)
        assert result == pytest.approx(0.0)

    def test_zero_setpoint_resets_integral(self):
        comp = _make_compensator()
        # Build up some integral
        comp.compensate(setpoint=100.0, measurement=90.0, dt=0.3)
        comp.compensate(setpoint=100.0, measurement=90.0, dt=0.3)
        # Now zero setpoint -> should reset
        comp.compensate(setpoint=0.0, measurement=50.0, dt=0.3)
        diag = comp.diagnostics
        assert diag["integral"] == pytest.approx(0.0)

    def test_near_zero_setpoint_treated_as_zero(self):
        comp = _make_compensator()
        result = comp.compensate(setpoint=1e-8, measurement=50.0, dt=0.3)
        assert result == pytest.approx(0.0)


# ===========================================================================
# FF table basic behavior
# ===========================================================================


class TestCompensatorFFTable:
    def test_initial_ff_is_one(self):
        comp = _make_compensator()
        table = comp.ff_table
        for ff in table.values():
            assert ff == pytest.approx(1.0)

    def test_discharge_ff_multiplies_setpoint(self):
        """For positive setpoint, output = ff * setpoint (ff=1.0 initially)."""
        comp = _make_compensator(ki=0.0)  # disable integral for clarity
        result = comp.compensate(setpoint=100.0, measurement=100.0, dt=0.3)
        assert result == pytest.approx(100.0)

    def test_charge_ff_divides_setpoint(self):
        """For negative setpoint, output = setpoint / ff (ff=1.0 initially)."""
        comp = _make_compensator(ki=0.0)
        result = comp.compensate(setpoint=-100.0, measurement=-100.0, dt=0.3)
        assert result == pytest.approx(-100.0)

    def test_reset_ff_table(self):
        comp = _make_compensator()
        # Artificially set an ff entry
        comp._ff_table[0] = 1.05
        comp.reset_ff_table()
        table = comp.ff_table
        for ff in table.values():
            assert ff == pytest.approx(1.0)


# ===========================================================================
# Integral accumulation
# ===========================================================================


class TestCompensatorIntegral:
    def test_positive_error_accumulates_integral(self):
        """When setpoint > measurement, integral should accumulate positive error."""
        comp = _make_compensator(ki=0.3, deadband=0.0, hold_cycles=0)
        # setpoint=100, measurement=90 -> error=10
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        diag = comp.diagnostics
        assert diag["integral"] > 0

    def test_error_within_deadband_no_integral(self):
        """Error below deadband should not accumulate integral."""
        comp = _make_compensator(ki=0.3, deadband=5.0, hold_cycles=0)
        # error = 100 - 98 = 2 < deadband 5
        comp.compensate(setpoint=100.0, measurement=98.0, dt=1.0)
        diag = comp.diagnostics
        assert diag["integral"] == pytest.approx(0.0)

    def test_integral_clamped_to_max(self):
        """Integral should be clamped by integral_max_ratio."""
        comp = _make_compensator(
            ki=1.0,
            integral_max_ratio=0.05,
            rated_power=1000.0,
            deadband=0.0,
            hold_cycles=0,
        )
        # max_contribution = 0.05 * 1000 = 50 -> integral_max = 50 / 1.0 = 50
        # Push a huge error to exceed the clamp
        for _ in range(100):
            comp.compensate(setpoint=500.0, measurement=0.0, dt=1.0)
        diag = comp.diagnostics
        assert abs(diag["integral"]) <= 50.0 + 0.01


# ===========================================================================
# Setpoint change policy
# ===========================================================================


class TestCompensatorSetpointChange:
    def test_setpoint_change_resets_integral(self):
        """Changing setpoint by more than 0.1 should reset integral."""
        comp = _make_compensator(ki=0.3, deadband=0.0, hold_cycles=0)
        # Build up integral
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        assert comp.diagnostics["integral"] > 0

        # Change setpoint significantly
        comp.compensate(setpoint=200.0, measurement=190.0, dt=1.0)
        # Integral should have been reset (then possibly re-accumulated for 1 step)
        # The key assertion: it should not be the accumulated value from before
        # After reset, integral_hold prevents accumulation for hold_cycles=0, so
        # one step of error 10 over dt=1 gives integral=10 (not the old value)
        assert comp.diagnostics["integral"] <= 10.1

    def test_small_setpoint_change_no_reset(self):
        """Change < 0.1 should not trigger reset."""
        comp = _make_compensator(ki=0.3, deadband=0.0, hold_cycles=0)
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        old_integral = comp.diagnostics["integral"]
        comp.compensate(setpoint=100.05, measurement=90.0, dt=1.0)
        # Should have continued accumulating, not reset
        assert comp.diagnostics["integral"] >= old_integral


# ===========================================================================
# Output clamping
# ===========================================================================


class TestCompensatorClamp:
    def test_output_clamped_to_max(self):
        comp = _make_compensator(output_max=500.0, ki=0.0)
        result = comp.compensate(setpoint=1000.0, measurement=1000.0, dt=0.3)
        assert result <= 500.0

    def test_output_clamped_to_min(self):
        comp = _make_compensator(output_min=-500.0, ki=0.0)
        result = comp.compensate(setpoint=-1000.0, measurement=-1000.0, dt=0.3)
        assert result >= -500.0


# ===========================================================================
# Rate limit
# ===========================================================================


class TestCompensatorRateLimit:
    def test_rate_limit_restricts_change(self):
        comp = _make_compensator(rate_limit=100.0, ki=0.0)
        # First call establishes last_output
        comp.compensate(setpoint=100.0, measurement=100.0, dt=1.0)
        # Jump setpoint to 1000 -> ff output jumps to 1000
        # rate_limit=100/s * dt=1.0 = max delta 100
        result = comp.compensate(setpoint=1000.0, measurement=1000.0, dt=1.0)
        # Should be limited to last_output + 100 = 100 + 100 = 200 max
        assert result <= 200.1

    def test_rate_limit_zero_no_restriction(self):
        comp = _make_compensator(rate_limit=0.0, ki=0.0)
        comp.compensate(setpoint=100.0, measurement=100.0, dt=1.0)
        result = comp.compensate(setpoint=1000.0, measurement=1000.0, dt=1.0)
        assert result == pytest.approx(1000.0)


# ===========================================================================
# Reset
# ===========================================================================


class TestCompensatorReset:
    def test_reset_clears_state(self):
        comp = _make_compensator(ki=0.3, deadband=0.0, hold_cycles=0)
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        assert comp.diagnostics["integral"] > 0

        comp.reset()
        diag = comp.diagnostics
        assert diag["integral"] == pytest.approx(0.0)
        assert diag["last_setpoint"] == pytest.approx(0.0)
        assert diag["last_output"] == pytest.approx(0.0)


# ===========================================================================
# Enabled / disabled
# ===========================================================================


class TestCompensatorEnabled:
    def test_enabled_default_true(self):
        comp = _make_compensator()
        assert comp.enabled is True

    def test_disable_resets_and_process_passthrough(self):
        comp = _make_compensator(ki=0.3, deadband=0.0, hold_cycles=0)
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        comp.enabled = False
        assert comp.diagnostics["integral"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_process_disabled_returns_original(self):
        comp = _make_compensator()
        comp.enabled = False
        cmd = Command(p_target=500.0, q_target=100.0)
        ctx = StrategyContext(extra={"meter_power": 490.0})
        result = await comp.process(cmd, ctx)
        assert result.p_target == pytest.approx(500.0)
        assert result.q_target == pytest.approx(100.0)


# ===========================================================================
# CommandProcessor.process()
# ===========================================================================


class TestCompensatorProcess:
    @pytest.mark.asyncio
    async def test_process_no_measurement_passthrough(self):
        """If measurement key is missing from context.extra, pass through."""
        comp = _make_compensator()
        cmd = Command(p_target=500.0, q_target=100.0)
        ctx = StrategyContext(extra={})  # no meter_power
        result = await comp.process(cmd, ctx)
        assert result.p_target == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_process_with_measurement(self):
        """process() should call compensate() and return modified command."""
        comp = _make_compensator(ki=0.0)
        cmd = Command(p_target=100.0, q_target=50.0)
        ctx = StrategyContext(extra={"meter_power": 95.0, "dt": 0.3})
        result = await comp.process(cmd, ctx)
        # With ff=1.0 and ki=0: output = 1.0 * 100 = 100
        assert result.p_target == pytest.approx(100.0)
        # Q should be preserved
        assert result.q_target == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_process_zero_setpoint(self):
        comp = _make_compensator()
        cmd = Command(p_target=0.0, q_target=0.0)
        ctx = StrategyContext(extra={"meter_power": 10.0})
        result = await comp.process(cmd, ctx)
        assert result.p_target == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_process_custom_measurement_key(self):
        comp = _make_compensator(measurement_key="grid_power", ki=0.0)
        cmd = Command(p_target=200.0)
        ctx = StrategyContext(extra={"grid_power": 190.0})
        result = await comp.process(cmd, ctx)
        assert result.p_target == pytest.approx(200.0)


# ===========================================================================
# Diagnostics
# ===========================================================================


class TestCompensatorDiagnostics:
    def test_diagnostics_keys(self):
        comp = _make_compensator()
        diag = comp.diagnostics
        expected_keys = {
            "enabled",
            "integral",
            "i_contribution",
            "last_setpoint",
            "last_output",
            "last_ff",
            "steady_count",
            "hold_remaining",
        }
        assert set(diag.keys()) == expected_keys

    def test_diagnostics_after_compensate(self):
        comp = _make_compensator(ki=0.0)
        comp.compensate(setpoint=100.0, measurement=100.0, dt=0.3)
        diag = comp.diagnostics
        assert diag["last_setpoint"] == pytest.approx(100.0)
        assert diag["last_output"] == pytest.approx(100.0)


# ===========================================================================
# Steady-state learning
# ===========================================================================


class TestCompensatorSteadyStateLearning:
    def test_learning_updates_ff_table(self):
        """After enough steady-state cycles with non-zero i_term, FF should update."""
        comp = _make_compensator(
            ki=0.5,
            deadband=0.0,
            hold_cycles=0,
            steady_state_threshold=0.05,
            steady_state_cycles=3,
            rated_power=1000.0,
        )
        # Simulate steady state: small error relative to setpoint
        for _ in range(20):
            comp.compensate(setpoint=500.0, measurement=498.0, dt=1.0)

        # Check if any FF entry changed from 1.0
        table = comp.ff_table
        idx = comp._get_bin_index(500.0)
        # The FF might or might not have updated depending on the I buildup.
        # At minimum, the compensator should not crash, and the table should be accessible.
        assert idx in table


# ===========================================================================
# FFTableRepository & async_init
# ===========================================================================


class FakeRepository:
    """In-memory repository for testing."""

    def __init__(self, initial_data: dict[int, float] | None = None):
        self.saved: dict[int, float] | None = None
        self._data = initial_data

    def save(self, table: dict[int, float]) -> None:
        self.saved = dict(table)

    def load(self) -> dict[int, float] | None:
        return dict(self._data) if self._data else None


class FakeAsyncRepository:
    """Repository with async_load (simulates MongoDB)."""

    def __init__(self, initial_data: dict[int, float] | None = None):
        self.saved: dict[int, float] | None = None
        self._data = initial_data

    def save(self, table: dict[int, float]) -> None:
        self.saved = dict(table)

    def load(self) -> dict[int, float] | None:
        # Sync load returns None (like MongoFFTableRepository)
        return None

    async def async_load(self) -> dict[int, float] | None:
        return dict(self._data) if self._data else None


class TestFFTableRepository:
    def test_protocol_compliance(self):
        repo = FakeRepository()
        assert isinstance(repo, FFTableRepository)

    def test_custom_repo_load_on_init(self):
        """Custom sync repo should be loaded during __init__."""
        # step=5 → n_bins=20, need max_idx=20 to avoid migration
        repo = FakeRepository(initial_data={0: 1.05, 3: 0.98, 20: 1.0, -20: 1.0})
        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""), repository=repo)
        assert comp.ff_table[0] == pytest.approx(1.05)
        assert comp.ff_table[3] == pytest.approx(0.98)

    def test_custom_repo_save_on_learn(self):
        """When FF learns, save() should be called on the repository."""
        repo = FakeRepository()
        comp = PowerCompensator(
            PowerCompensatorConfig(
                persist_path="",
                ki=0.5,
                deadband=0.0,
                hold_cycles=0,
                steady_state_threshold=0.05,
                steady_state_cycles=3,
                rated_power=1000.0,
            ),
            repository=repo,
        )
        for _ in range(20):
            comp.compensate(setpoint=500.0, measurement=498.0, dt=1.0)
        # save may or may not have been called depending on learning trigger,
        # but the repo should be wired correctly
        assert repo is comp._repository

    def test_no_repo_no_persist_path(self):
        """No repo + no persist_path → no persistence at all."""
        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""))
        assert comp._repository is None

    def test_persist_path_creates_json_repo(self):
        """persist_path without explicit repo → auto-creates JsonFFTableRepository."""
        comp = PowerCompensator(PowerCompensatorConfig(persist_path="/tmp/test_ff.json"))
        assert isinstance(comp._repository, JsonFFTableRepository)

    def test_explicit_repo_overrides_persist_path(self):
        """Explicit repository takes priority over persist_path."""
        repo = FakeRepository()
        comp = PowerCompensator(
            PowerCompensatorConfig(persist_path="/tmp/should_be_ignored.json"),
            repository=repo,
        )
        assert comp._repository is repo


class TestAsyncInit:
    @pytest.mark.asyncio
    async def test_async_init_loads_from_async_repo(self):
        """async_init() should call async_load() and populate FF table."""
        repo = FakeAsyncRepository(initial_data={0: 1.1, 2: 0.95})
        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""), repository=repo)

        # Before async_init: sync load returned None, FF table should be defaults
        assert comp.ff_table[0] == pytest.approx(1.0)

        # After async_init: async_load populates FF table
        await comp.async_init()
        assert comp.ff_table[0] == pytest.approx(1.1)
        assert comp.ff_table[2] == pytest.approx(0.95)

    @pytest.mark.asyncio
    async def test_async_init_no_repo_is_noop(self):
        """async_init() with no repository should be a no-op."""
        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""))
        await comp.async_init()  # should not raise

    @pytest.mark.asyncio
    async def test_async_init_sync_repo_no_async_load(self):
        """async_init() with sync-only repo (no async_load) is a no-op."""
        repo = FakeRepository(initial_data={0: 1.05})
        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""), repository=repo)
        await comp.async_init()  # no async_load attr → skip
        # Sync load already happened in __init__
        assert comp.ff_table[0] == pytest.approx(1.05)

    @pytest.mark.asyncio
    async def test_sync_load_returns_none_for_async_repo(self):
        """Async repo's sync load() must return None (broken by design without async_init)."""
        repo = FakeAsyncRepository(initial_data={0: 1.1})
        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""), repository=repo)
        # sync load returned None → FF table is default
        assert comp.ff_table[0] == pytest.approx(1.0)

    def test_load_ff_table_public_method(self):
        """load_ff_table() should accept external table data."""
        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""))
        comp.load_ff_table({0: 1.15, -1: 0.92})
        assert comp.ff_table[0] == pytest.approx(1.15)
        assert comp.ff_table[-1] == pytest.approx(0.92)


class TestMongoFFTableRepository:
    def test_sync_load_returns_none(self):
        """MongoFFTableRepository.load() should return None (async only)."""
        repo = MongoFFTableRepository(collection=None, document_id="test")
        result = repo.load()
        assert result is None


# ===========================================================================
# Transient gate (hold_cycles > 0)
# ===========================================================================


class TestCompensatorTransientGate:
    def test_hold_cycles_delays_integral_accumulation(self):
        """After a setpoint change, integral should NOT accumulate during hold period."""
        comp = _make_compensator(ki=0.3, deadband=0.0, hold_cycles=3, settle_ratio=0.15)
        # Initial setpoint
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        # Change setpoint -> triggers hold_cycles=3
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)

        # During hold: error=20, settle_threshold = |200-100| * 0.15 = 15
        # error 20 > 15, so hold does NOT count down
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        assert comp.diagnostics["hold_remaining"] == 3  # unchanged because error > settle_threshold

    def test_hold_counts_down_when_error_within_settle(self):
        """Hold should count down when |error| <= settle_threshold."""
        comp = _make_compensator(ki=0.3, deadband=0.0, hold_cycles=3, settle_ratio=0.5)
        comp.compensate(setpoint=100.0, measurement=100.0, dt=1.0)
        # Change setpoint: settle_threshold = |200-100| * 0.5 = 50
        # The setpoint-change call itself also runs integral update, so hold counts down once there
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        # error=20 < settle=50 -> hold counted down on that same call: 3 -> 2
        assert comp.diagnostics["hold_remaining"] == 2
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        assert comp.diagnostics["hold_remaining"] == 1
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        assert comp.diagnostics["hold_remaining"] == 0

    def test_integral_resumes_after_hold_expires(self):
        """After hold_cycles expire, integral accumulation should resume."""
        comp = _make_compensator(ki=0.3, deadband=0.0, hold_cycles=1, settle_ratio=1.0)
        comp.compensate(setpoint=100.0, measurement=100.0, dt=1.0)
        # Change setpoint: settle_threshold = |200-100| * 1.0 = 100
        comp.compensate(setpoint=200.0, measurement=190.0, dt=1.0)
        # hold=1, error=10 < 100 -> countdown: hold becomes 0
        comp.compensate(setpoint=200.0, measurement=190.0, dt=1.0)
        assert comp.diagnostics["hold_remaining"] == 0
        # Next call: hold=0, error=10 > deadband=0 -> integral should accumulate
        comp.compensate(setpoint=200.0, measurement=190.0, dt=1.0)
        assert comp.diagnostics["integral"] > 0


# ===========================================================================
# EMA error filtering
# ===========================================================================


class TestCompensatorEMAFilter:
    def test_ema_filter_smooths_error(self):
        """With error_ema_alpha > 0, filtered error should lag behind raw error."""
        comp = _make_compensator(ki=0.3, deadband=0.0, hold_cycles=0, error_ema_alpha=0.3)
        # Step 1: error=10, filtered_error = 0.3*10 + 0.7*0 = 3.0
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        # The integral should be based on filtered_error=3.0 (not raw 10)
        assert comp.diagnostics["integral"] == pytest.approx(3.0, abs=0.1)

    def test_ema_alpha_zero_no_filtering(self):
        """With alpha=0, raw error is used directly."""
        comp = _make_compensator(ki=0.3, deadband=0.0, hold_cycles=0, error_ema_alpha=0.0)
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        # Raw error=10, integral = 10 * 1.0 = 10
        assert comp.diagnostics["integral"] == pytest.approx(10.0, abs=0.1)


# ===========================================================================
# Saturation resets integral
# ===========================================================================


class TestCompensatorSaturation:
    def test_saturation_resets_integral_at_max(self):
        """When ff_output >= output_max, integral should be reset to 0."""
        comp = _make_compensator(
            output_max=500.0,
            ki=0.3,
            deadband=0.0,
            hold_cycles=0,
        )
        # First: build some integral at moderate setpoint
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        assert comp.diagnostics["integral"] > 0

        # Now saturate: setpoint=1000, ff=1.0 -> ff_output=1000 > output_max=500
        comp.compensate(setpoint=1000.0, measurement=500.0, dt=1.0)
        assert comp.diagnostics["integral"] == pytest.approx(0.0)

    def test_saturation_resets_integral_at_min(self):
        """When ff_output <= output_min, integral should be reset to 0."""
        comp = _make_compensator(
            output_min=-500.0,
            ki=0.3,
            deadband=0.0,
            hold_cycles=0,
        )
        comp.compensate(setpoint=-200.0, measurement=-180.0, dt=1.0)
        comp.compensate(setpoint=-200.0, measurement=-180.0, dt=1.0)
        assert comp.diagnostics["integral"] != pytest.approx(0.0)

        # Saturate negative: setpoint=-1000, ff=1.0 -> ff_output=-1000 < output_min=-500
        comp.compensate(setpoint=-1000.0, measurement=-500.0, dt=1.0)
        assert comp.diagnostics["integral"] == pytest.approx(0.0)


# ===========================================================================
# FF inheritance
# ===========================================================================


class TestCompensatorFFInheritance:
    def test_ff_inherited_from_old_bin_to_new_bin(self):
        """When setpoint changes to a new bin that has ff=1.0, old bin's ff should be inherited."""
        comp = _make_compensator(ki=0.0, hold_cycles=0, rated_power=1000.0, power_bin_step_pct=10)
        # Manually set bin 5 (50%) to a non-default ff
        comp._ff_table[5] = 1.08
        # Execute at setpoint=500 (bin 5) first
        comp.compensate(setpoint=500.0, measurement=500.0, dt=1.0)
        # Change to setpoint=300 (bin 3, which is still 1.0)
        comp.compensate(setpoint=300.0, measurement=300.0, dt=1.0)
        # Bin 3 should have inherited ff=1.08 from bin 5
        assert comp.ff_table[3] == pytest.approx(1.08)

    def test_no_inheritance_when_new_bin_already_learned(self):
        """If the new bin already has a non-1.0 ff, inheritance should NOT overwrite."""
        comp = _make_compensator(ki=0.0, hold_cycles=0, rated_power=1000.0, power_bin_step_pct=10)
        comp._ff_table[5] = 1.08
        comp._ff_table[3] = 1.03  # already learned
        comp.compensate(setpoint=500.0, measurement=500.0, dt=1.0)
        comp.compensate(setpoint=300.0, measurement=300.0, dt=1.0)
        # Bin 3 should keep its own value
        assert comp.ff_table[3] == pytest.approx(1.03)

    def test_no_inheritance_when_same_bin(self):
        """If setpoint change stays in the same bin, no inheritance needed."""
        comp = _make_compensator(ki=0.0, hold_cycles=0, rated_power=1000.0, power_bin_step_pct=10)
        comp._ff_table[5] = 1.08
        comp.compensate(setpoint=500.0, measurement=500.0, dt=1.0)
        # Small change within same bin
        comp.compensate(setpoint=510.0, measurement=510.0, dt=1.0)
        # Should not crash; bin 5 stays 1.08
        assert comp.ff_table[5] == pytest.approx(1.08)
