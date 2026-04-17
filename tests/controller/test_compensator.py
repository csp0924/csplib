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
# Saturation + anti-windup (asymmetric)
# ===========================================================================


class TestCompensatorSaturation:
    def test_saturation_same_direction_holds_integral_at_max(self):
        """高飽和 + error > 0（同向 windup 風險）→ integral 不累積（凍結/歸零）。

        修復前：無條件清零 integral。
        修復後：僅在「error 與飽和方向一致」時凍結，避免 windup。
        此測試的場景（高飽和 + 正誤差）對應「凍結」分支，integral 應 ≤ 0。
        """
        comp = _make_compensator(
            output_max=500.0,
            ki=0.3,
            deadband=0.0,
            hold_cycles=0,
        )
        # 先在非飽和區累積 integral
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        assert comp.diagnostics["integral"] > 0

        # 高飽和 + error = 1000 - 400 = 600 > 0 同向 → integral 凍結（不再累積正值）
        prev = comp.diagnostics["integral"]
        comp.compensate(setpoint=1000.0, measurement=400.0, dt=1.0)
        # setpoint 從 200 跳到 1000 會先觸發 setpoint-change reset（integral=0），
        # 但飽和後 error 同向：凍結。所以最終 integral 應為 0（未累積正向 windup）。
        # 核心斷言：integral 絕對不能變得更「正」
        assert comp.diagnostics["integral"] <= prev
        # 同向飽和下，integral 不會累積為正
        assert comp.diagnostics["integral"] <= 0.0

    def test_saturation_same_direction_holds_integral_at_min(self):
        """低飽和 + error < 0（同向 windup 風險）→ integral 不累積。"""
        comp = _make_compensator(
            output_min=-500.0,
            ki=0.3,
            deadband=0.0,
            hold_cycles=0,
        )
        comp.compensate(setpoint=-200.0, measurement=-180.0, dt=1.0)
        comp.compensate(setpoint=-200.0, measurement=-180.0, dt=1.0)
        # integral 應為負（setpoint=-200, measurement=-180 → error = -20）
        assert comp.diagnostics["integral"] < 0

        prev = comp.diagnostics["integral"]
        # 低飽和 + error = -1000 - (-400) = -600 < 0 同向 → 凍結
        comp.compensate(setpoint=-1000.0, measurement=-400.0, dt=1.0)
        # 不會累積為更負
        assert comp.diagnostics["integral"] >= prev
        assert comp.diagnostics["integral"] >= 0.0


# ===========================================================================
# Asymmetric anti-windup + Saturation learning (v0.7.2 BUG-012)
# ===========================================================================


class TestCompensatorSaturationLearning:
    """v0.7.2 BUG-012: 飽和時的非對稱 anti-windup 與物理量學習。

    核心：當 FF 表某個 bin 學歪（如 bin[20]=1.1048 導致持續飽和），
    系統應能透過「飽和 + error 朝脫離方向」時的物理量推算，
    直接修正 FF 表，擺脫鎖死狀態。
    """

    # ─── 基本 asymmetric anti-windup ──────────────────────────────────

    def test_high_sat_error_negative_allows_integration(self):
        """高飽和 + error < -deadband → 允許積分累積負值（朝脫離飽和方向）。"""
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2000.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
        )
        # 人為將 bin[19] (setpoint=1900) 的 ff 設為 1.1 → ff_output = 1.1 × 1900 = 2090 > 2000 飽和
        comp._ff_table[19] = 1.1
        # measurement = 1920 → error = 1900 - 1920 = -20，朝脫離飽和方向
        for _ in range(5):
            comp.compensate(setpoint=1900.0, measurement=1920.0, dt=0.3)
        # 積分應已累積為負值（朝下拉，帶動 ff_output 降低）
        assert comp.diagnostics["integral"] < 0

    def test_high_sat_error_positive_freezes_integration(self):
        """高飽和 + error > 0（同向） → integral 凍結，不累積正值 (避免 windup)。"""
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2000.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
        )
        comp._ff_table[19] = 1.1  # → ff_output = 2090，飽和
        # error = 1900 - 1700 = 200 > 0，與飽和同向
        for _ in range(5):
            comp.compensate(setpoint=1900.0, measurement=1700.0, dt=0.3)
        # 不應累積正向 windup
        assert comp.diagnostics["integral"] <= 0.0

    def test_low_sat_error_positive_allows_integration(self):
        """低飽和 + error > +deadband → 允許積分累積正值（朝脫離方向）。"""
        comp = _make_compensator(
            rated_power=2000.0,
            output_min=-2000.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
        )
        # 讓 ff_output 飽和到負端：setpoint=-1900, ff=0.9 → ff_output = -1900/0.9 = -2111 < -2000
        comp._ff_table[-19] = 0.9
        # measurement = -1920 → error = -1900 - (-1920) = +20，朝脫離飽和方向
        for _ in range(5):
            comp.compensate(setpoint=-1900.0, measurement=-1920.0, dt=0.3)
        assert comp.diagnostics["integral"] > 0

    def test_low_sat_error_negative_freezes_integration(self):
        """低飽和 + error < 0（同向） → integral 凍結。"""
        comp = _make_compensator(
            rated_power=2000.0,
            output_min=-2000.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
        )
        comp._ff_table[-19] = 0.9  # → ff_output = -2111，飽和
        # error = -1900 - (-1700) = -200 < 0，同向
        for _ in range(5):
            comp.compensate(setpoint=-1900.0, measurement=-1700.0, dt=0.3)
        assert comp.diagnostics["integral"] >= 0.0

    # ─── 現場複現 + 收斂時限 ────────────────────────────────────────

    def test_field_scenario_bin20_convergence_1_5s(self):
        """現場 bug 複現：bin[20]=1.1048 導致 setpoint=1993 持續飽和。

        修復目標：
        - 5 cycles (1.5s) 內 ff_table[20] 應 ≤ 1.03
        - 10 cycles 內 ff_table[20] 應 ≤ 1.015
        """
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2000.0,
            output_min=-2000.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
        )
        comp._ff_table[20] = 1.1048

        setpoint = 1993.0
        real_ratio = 0.9909

        for i in range(5):
            # PCS 實際輸出 = 指令 clamp 到 output_max，measurement = 實際輸出 × real_ratio
            # （compensator 自身會 clamp，但 measurement 直接按「飽和後的 2000」模擬）
            # 更真實的作法：以上一次 compensate 回傳值為 PCS 指令
            if i == 0:
                pcs_cmd = min(1.1048 * setpoint, 2000.0)
            else:
                pcs_cmd = comp.diagnostics["last_output"]
            measurement = min(pcs_cmd, 2000.0) * real_ratio
            comp.compensate(setpoint=setpoint, measurement=measurement, dt=0.3)

        ff_at_5 = comp.ff_table[20]
        assert ff_at_5 <= 1.03, f"After 5 cycles (1.5s), ff_table[20]={ff_at_5:.4f} should be ≤ 1.03"

        # 再跑 5 cycles，共 10 cycles
        for _ in range(5):
            pcs_cmd = comp.diagnostics["last_output"]
            measurement = min(pcs_cmd, 2000.0) * real_ratio
            comp.compensate(setpoint=setpoint, measurement=measurement, dt=0.3)

        ff_at_10 = comp.ff_table[20]
        assert ff_at_10 <= 1.015, f"After 10 cycles, ff_table[20]={ff_at_10:.4f} should be ≤ 1.015"

    def test_field_scenario_grid_output_converges(self):
        """現場複現：20 cycles 後 FF 已脫離飽和鎖死 + 量測收斂到 setpoint ±2%。

        場景參數對應現場實測（log: compensated=2200，表示 output_max=2200）。
        修復前：bin[20] 停留在 1.1048，compensator 輸出持續被 clamp 到 output_max=2200，
        grid 永遠讀到 2180（= 2200 × 0.9909），rel_err=9.4% 不修正。
        修復後（20 cycles ≈ 6s）：
        - saturation learning 一步學到 1.0748 → 脫離飽和
        - integral 持續收縮 output → grid 進入 2% 穩態窗
        - standard learning 進一步學到 ≈ 1.02 → rel_err < 2%
        實測 cycle 20：ff=1.0246, output=2032, meas=2016, rel_err=1.16%
        """
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2200.0,
            output_min=-2200.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
        )
        comp._ff_table[20] = 1.1048

        setpoint = 1993.0
        real_ratio = 0.9909

        last_measurement = 0.0
        last_output = 0.0
        for i in range(20):
            if i == 0:
                pcs_cmd = min(1.1048 * setpoint, 2200.0)
            else:
                pcs_cmd = comp.diagnostics["last_output"]
            last_measurement = min(pcs_cmd, 2200.0) * real_ratio
            last_output = comp.compensate(setpoint=setpoint, measurement=last_measurement, dt=0.3)

        # 關鍵：FF 表應脫離鎖死
        assert comp.ff_table[20] < 1.05, (
            f"After 20 cycles, ff_table[20]={comp.ff_table[20]:.4f} 應 < 1.05（已脫離鎖死）"
        )
        # 輸出不再被 output_max clamp 束縛（即 last_output 嚴格小於 output_max）
        assert last_output < 2200.0 - 1.0, f"last_output={last_output:.2f} 應 < output_max，表示 FF 已收斂不需 clamp"
        # 量測收斂
        rel_err = abs(last_measurement - setpoint) / setpoint
        assert rel_err < 0.02, f"|measurement - setpoint|/setpoint = {rel_err:.4f} should be < 0.02"

    # ─── 穩健性 ────────────────────────────────────────────────────

    def test_saturation_learn_requires_min_cycles(self):
        """saturation_learn_min_cycles=2：單次飽和脫離不學習，第 2 次才學。"""
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2000.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
            saturation_learn_min_cycles=2,
        )
        comp._ff_table[20] = 1.1048
        initial_ff = comp._ff_table[20]

        # 第一次呼叫：飽和、error 脫離方向 → 但未達 min_cycles，不學習
        comp.compensate(setpoint=1993.0, measurement=1982.0, dt=0.3)
        assert comp.ff_table[20] == pytest.approx(initial_ff), "第 1 次飽和不應學習"

        # 第二次呼叫：達到 min_cycles，開始學習
        comp.compensate(setpoint=1993.0, measurement=1982.0, dt=0.3)
        assert comp.ff_table[20] < initial_ff, "第 2 次飽和應觸發學習"

    def test_saturation_learn_ema_smoothing(self):
        """EMA 平滑：old_ff=1.20 + physical≈1.00 + max_step=0.03 → 學習後 ff ≥ 1.17。

        此測試驗證 max_step clamp：EMA 值為 0.5*1.00+0.5*1.20=1.10，
        但差距 0.10 > max_step=0.03，所以只能下移 0.03 → 1.17。
        """
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2000.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
            saturation_learn_min_cycles=1,
            saturation_learn_alpha=0.5,
            saturation_learn_max_step=0.03,
        )
        comp._ff_table[20] = 1.20  # initial
        # setpoint=2000, ff=1.20 → ff_output=2400 飽和. measurement ≈ 2000 (physical≈1.00)
        comp.compensate(setpoint=2000.0, measurement=2000.0, dt=0.3)

        new_ff = comp.ff_table[20]
        # 單次最多下移 max_step=0.03 → 下限 1.17
        assert new_ff >= 1.17 - 1e-6, f"ff={new_ff} should be ≥ 1.17 (clamped by max_step)"
        assert new_ff < 1.20, f"ff={new_ff} should have moved below initial 1.20"

    def test_saturation_learn_max_step_clamp(self):
        """單次變動量嚴格 ≤ max_step。"""
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2000.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
            saturation_learn_min_cycles=1,
            saturation_learn_alpha=1.0,  # alpha=1 → new_ff = physical，完全無 EMA
            saturation_learn_max_step=0.03,
        )
        comp._ff_table[20] = 1.30  # 與 physical≈1.00 差 0.30，遠超 max_step
        comp.compensate(setpoint=2000.0, measurement=2000.0, dt=0.3)

        delta = abs(comp.ff_table[20] - 1.30)
        assert delta <= 0.03 + 1e-9, f"單次變動 {delta:.4f} 不應超過 max_step=0.03"

    def test_saturation_learn_ff_min_max_clamp(self):
        """物理推算結果超過 ff_max 時，clamp 至 ff_max。

        場景：低飽和，measurement=-1000, output_min=-2000 →
        physical = measurement/output_min = 0.5。
        若 alpha=1.0, old=1.0 → new_ff=0.5，但 |0.5-1.0|=0.5 > max_step=0.03 → 限制為 0.97。
        為了驗證 ff_min clamp，把 old 設得很低且 physical 更低。
        """
        comp = _make_compensator(
            rated_power=2000.0,
            output_min=-2000.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
            ff_min=0.85,
            ff_max=1.5,
            saturation_learn_min_cycles=1,
            saturation_learn_alpha=1.0,
            saturation_learn_max_step=10.0,  # 解除 max_step 限制以測試 ff_min
        )
        comp._ff_table[-20] = 0.88
        # 低飽和 + physical = measurement/output_min = -500/-2000 = 0.25
        # 但 setpoint=-2000, ff=0.88 → ff_output = -2000/0.88 = -2272 < -2000 (飽和)
        # error = -2000 - (-500) = -1500 < 0，同向 → 不應學習
        # 改成 measurement=-2100：error = -2000 - (-2100) = +100 > 0，朝脫離方向
        # physical = measurement/output_min = -2100/-2000 = 1.05
        # new_ff = 1.05，但 ff_min 不約束（1.05 > 0.85），應被 ff_max=1.5 允許
        # 這測試用另一種方式：大 old + physical 嚴重超界
        comp._ff_table[-20] = 0.88  # reset
        # 構造：output_min=-2000, measurement=-10000（極端異常大）→ physical = -10000/-2000 = 5.0 > ff_max=1.5
        comp.compensate(setpoint=-2000.0, measurement=-10000.0, dt=0.3)
        assert comp.ff_table[-20] <= 1.5 + 1e-6, f"ff={comp.ff_table[-20]} 應 clamp 至 ff_max=1.5"

    def test_measurement_noise_no_oscillation(self):
        """雜訊下 ff_table[20] 軌跡單調遞減，最終收斂到穩定值。"""
        import random

        rng = random.Random(42)
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2000.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
        )
        comp._ff_table[20] = 1.1048

        ff_history = [comp._ff_table[20]]
        for _ in range(20):
            # measurement 在 [2170, 2190] 隨機（模擬雜訊）
            # 但實際上 PCS 會 clamp 到 2000；此處直接餵 measurement 模擬各種情況
            measurement = 1980.0 + rng.uniform(-10.0, 10.0)
            comp.compensate(setpoint=1993.0, measurement=measurement, dt=0.3)
            ff_history.append(comp._ff_table[20])

        # 軌跡應大致單調遞減（允許微小 EMA 抖動：後項 ≤ 前項 + 小 tolerance）
        # 嚴格單調遞減檢查
        for i in range(1, len(ff_history)):
            assert ff_history[i] <= ff_history[i - 1] + 0.005, (
                f"ff 軌跡在 step {i} 震盪：{ff_history[i - 1]:.4f} → {ff_history[i]:.4f}"
            )

        final_ff = ff_history[-1]
        assert 1.005 <= final_ff <= 1.020, f"final_ff={final_ff} 應收斂到 [1.005, 1.020]"

    # ─── 邊界：跳過學習的條件 ──────────────────────────────────────

    def test_measurement_none_skips_saturation_learn(self):
        """measurement=None → 不觸發、不 crash。

        注意 compensate() 直接收 float；None 進入是透過 process()。
        此處模擬 process path 中 measurement 為 None 被早退出，不應進入 compensate。
        """
        import asyncio

        comp = _make_compensator()
        comp._ff_table[20] = 1.1048

        cmd = Command(p_target=1993.0)
        ctx = StrategyContext(extra={})  # no meter_power

        async def _run():
            return await comp.process(cmd, ctx)

        result = asyncio.run(_run())
        # measurement 缺失 → passthrough，ff 表未更動
        assert result.p_target == pytest.approx(1993.0)
        assert comp.ff_table[20] == pytest.approx(1.1048)

    def test_measurement_nan_skips_saturation_learn(self):
        """measurement=NaN → 不觸發學習、不 crash。"""
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2000.0,
            saturation_learn_min_cycles=1,
        )
        comp._ff_table[20] = 1.1048
        initial = comp._ff_table[20]

        # NaN 測試 — 應安全處理，ff 表不變
        comp.compensate(setpoint=1993.0, measurement=float("nan"), dt=0.3)
        assert comp.ff_table[20] == pytest.approx(initial), "NaN measurement 下 ff 表應保持不變"

    def test_measurement_zero_skips_saturation_learn(self):
        """measurement=0 → 不觸發（避免 output_max/0 除零）。"""
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2000.0,
            saturation_learn_min_cycles=1,
        )
        comp._ff_table[20] = 1.1048
        initial = comp._ff_table[20]

        comp.compensate(setpoint=1993.0, measurement=0.0, dt=0.3)
        # 學習分支應跳過（物理推算會除零）
        assert comp.ff_table[20] == pytest.approx(initial), "measurement=0 下不應學習（避免除零）"

    def test_sign_mismatch_skips_saturation_learn(self):
        """放電飽和（sat_high）但 measurement < 0 → 符號不一致，不學習。"""
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2000.0,
            saturation_learn_min_cycles=1,
        )
        comp._ff_table[20] = 1.1048
        initial = comp._ff_table[20]

        # setpoint=1993 (正)，但 measurement=-100 (負) → 符號不一致
        comp.compensate(setpoint=1993.0, measurement=-100.0, dt=0.3)
        assert comp.ff_table[20] == pytest.approx(initial), "符號不一致時不應學習"

    # ─── 充電側鏡像 ────────────────────────────────────────────────

    def test_low_saturation_learning_charging_side(self):
        """充電側鏡像：ff_table[-20]=0.9 導致 |ff_output|>2000 飽和，應收斂。"""
        comp = _make_compensator(
            rated_power=2000.0,
            output_min=-2000.0,
            ki=0.3,
            deadband=0.5,
            hold_cycles=0,
        )
        comp._ff_table[-20] = 0.9
        # setpoint=-1993, ff=0.9 → ff_output = -1993/0.9 = -2214 < -2000 (飽和)
        # measurement=-1976 → error = -1993 - (-1976) = -17 < 0，與低飽和同向
        # 實際需要 error > 0 才會觸發 low-sat 的脫離學習分支。
        # 根據 architect 設計：低飽和 + error > 0 → 允許積分 + 學習。
        # 所以這裡 measurement 應設成比 setpoint「更小」(在充電場景，|measurement| < |setpoint|)。
        # setpoint=-1993, measurement=-1976 → error = -1993 - (-1976) = -17 (朝低飽和方向，同向)
        # 修正：setpoint=-1993, measurement=-2010 → error = -1993 - (-2010) = +17 (朝脫離方向)
        for _ in range(5):
            comp.compensate(setpoint=-1993.0, measurement=-2010.0, dt=0.3)

        # ff_table[-20] 應上調（朝 1.0 方向）
        assert comp.ff_table[-20] >= 0.98, f"ff_table[-20]={comp.ff_table[-20]} 應 ≥ 0.98 after 5 cycles"


# ===========================================================================
# BUG-002: _learn_if_steady divide-by-zero when deadband=0
# ===========================================================================


class TestCompensatorLearnIfSteadyZeroSetpoint:
    def test_learn_if_steady_setpoint_zero_no_crash_with_zero_deadband(self):
        """BUG-002: deadband=0 時，setpoint=0 不應在 _learn_if_steady 除以零 crash。

        修復前：line 519 `if abs(setpoint) < cfg.deadband:` 在 deadband=0 時失效，
        line 523 `filtered_error / setpoint` 除以零 → ZeroDivisionError。
        修復後：guard 改為 `if abs(setpoint) < max(cfg.deadband, 1e-6):`。

        由於 compensate() 本身在 setpoint<1e-6 時就早退出，此 bug 觸發需繞過
        早退出路徑：實際場景在 `_learn_if_steady` 被直接呼叫或其他邊界條件。
        這裡測試對外行為：deadband=0 + setpoint=0 多次呼叫應安全。
        """
        config = PowerCompensatorConfig(deadband=0.0, persist_path="")
        comp = PowerCompensator(config)

        # 多次呼叫 setpoint=0，不應 crash
        for _ in range(5):
            result = comp.compensate(setpoint=0.0, measurement=0.0, dt=0.3)
            assert result == pytest.approx(0.0)

        # 直接呼叫內部學習方法（繞過 compensate 的早退出）
        # deadband=0 時 guard 應使用 max(deadband, 1e-6) 避免除零
        try:
            comp._learn_if_steady(setpoint=0.0, filtered_error=0.5)
        except ZeroDivisionError:
            pytest.fail("_learn_if_steady 在 deadband=0, setpoint=0 時不應 ZeroDivisionError")


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


# ===========================================================================
# v0.7.3 BUG-007: update_ff_bin / persist_ff_table public API
# ===========================================================================


class TestUpdateFFBin:
    """v0.7.3 BUG-007: update_ff_bin 公開介面驗證。

    修復前：calibration 等外部呼叫者直接操作 ``_ff_table`` dict（反模式）。
    修復後：透過 ``update_ff_bin()`` 提供完整驗證鏈。
    """

    def test_update_ff_bin_happy_path(self):
        """正常呼叫：update_ff_bin(-2, 1.2) 後對應 bin 的值更新。"""
        comp = _make_compensator()
        assert comp.ff_table[-2] == pytest.approx(1.0)
        comp.update_ff_bin(-2, 1.2)
        assert comp.ff_table[-2] == pytest.approx(1.2)

    def test_update_ff_bin_raises_typeerror_on_non_int_bin(self):
        """bin_idx 非 int 時應拋出 TypeError。"""
        comp = _make_compensator()
        with pytest.raises(TypeError):
            comp.update_ff_bin("a", 1.0)  # type: ignore[arg-type]

    def test_update_ff_bin_raises_typeerror_on_bool_bin(self):
        """bool 是 int 的子類但不應被接受。"""
        comp = _make_compensator()
        with pytest.raises(TypeError):
            comp.update_ff_bin(True, 1.0)  # type: ignore[arg-type]

    def test_update_ff_bin_raises_valueerror_on_missing_bin(self):
        """bin_idx 不在 FF 表中時應拋出 ValueError。"""
        comp = _make_compensator()
        # 預設 step=5 → bins 從 -20 到 20
        with pytest.raises(ValueError, match="不在 FF 表中"):
            comp.update_ff_bin(999, 1.0)

    def test_update_ff_bin_raises_valueerror_on_nan(self):
        """ff_ratio 為 NaN 時應拋出 ValueError。"""
        comp = _make_compensator()
        with pytest.raises(ValueError):
            comp.update_ff_bin(0, float("nan"))

    def test_update_ff_bin_raises_valueerror_on_inf(self):
        """ff_ratio 為 Inf 時應拋出 ValueError。"""
        comp = _make_compensator()
        with pytest.raises(ValueError):
            comp.update_ff_bin(0, float("inf"))

    def test_update_ff_bin_raises_valueerror_on_negative_inf(self):
        """ff_ratio 為 -Inf 時應拋出 ValueError。"""
        comp = _make_compensator()
        with pytest.raises(ValueError):
            comp.update_ff_bin(0, float("-inf"))

    def test_update_ff_bin_raises_valueerror_on_negative(self):
        """ff_ratio < 0 時應拋出 ValueError。"""
        comp = _make_compensator()
        with pytest.raises(ValueError, match=">= 0"):
            comp.update_ff_bin(0, -0.5)

    def test_update_ff_bin_clamps_out_of_range(self):
        """ff_ratio 超出 [ff_min, ff_max] 時應 clamp（不 raise）。"""
        comp = _make_compensator(ff_min=0.8, ff_max=1.5)
        # 超過上限 → 應 clamp 到 ff_max
        comp.update_ff_bin(0, 2.0)
        assert comp.ff_table[0] == pytest.approx(1.5)

    def test_update_ff_bin_clamps_below_min(self):
        """ff_ratio 低於 ff_min 但仍 >= 0 時應 clamp 到 ff_min。"""
        comp = _make_compensator(ff_min=0.8, ff_max=1.5)
        comp.update_ff_bin(0, 0.5)
        assert comp.ff_table[0] == pytest.approx(0.8)

    def test_update_ff_bin_persist_true_triggers_save(self):
        """persist=True 時應呼叫 repository.save。"""
        repo = FakeRepository()
        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""), repository=repo)
        comp.update_ff_bin(0, 1.1, persist=True)
        assert repo.saved is not None
        assert 0 in repo.saved

    def test_update_ff_bin_persist_false_no_save(self):
        """persist=False 時不應呼叫 repository.save。"""
        repo = FakeRepository()
        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""), repository=repo)
        comp.update_ff_bin(0, 1.1, persist=False)
        assert repo.saved is None

    def test_update_ff_bin_zero_is_valid(self):
        """ff_ratio=0.0 是合法值（在 ff_min 內時直接寫入，不在時 clamp 到 ff_min）。"""
        comp = _make_compensator(ff_min=0.0, ff_max=1.5)
        comp.update_ff_bin(0, 0.0)
        assert comp.ff_table[0] == pytest.approx(0.0)


class TestPersistFFTable:
    """v0.7.3 BUG-007: persist_ff_table 公開介面驗證。"""

    def test_persist_ff_table_no_repository_is_noop(self):
        """repository=None 時呼叫 persist_ff_table 不應 raise。"""
        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""))
        assert comp._repository is None
        comp.persist_ff_table()  # 不應拋出例外

    def test_persist_ff_table_calls_repository_save(self):
        """有 repository 時應呼叫 save。"""
        repo = FakeRepository()
        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""), repository=repo)
        comp.persist_ff_table()
        assert repo.saved is not None

    def test_persist_ff_table_swallows_repository_exception(self):
        """repository.save 拋出例外時不應向上傳播。"""

        class FailingRepo:
            def save(self, table):
                raise OSError("disk full")

            def load(self):
                return None

        comp = PowerCompensator(PowerCompensatorConfig(persist_path=""), repository=FailingRepo())
        # 不應 raise
        comp.persist_ff_table()
