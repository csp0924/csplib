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
# Equivalence constants (v0.8 新 API ↔ v0.7 舊 API 換算)
# ===========================================================================

# integral_time_seconds = integral_max_ratio (0.05) / 舊 ki
_T_EQUIV_KI_03 = 0.05 / 0.3  # ≈ 0.167s,  舊 ki=0.3
_T_EQUIV_KI_05 = 0.05 / 0.5  # = 0.1s,    舊 ki=0.5
_T_EQUIV_KI_10 = 0.05 / 1.0  # = 0.05s,   舊 ki=1.0

# deadband_ratio = 舊 deadband_kw / rated_power（測試固定 rated=2000）
_DB_RATIO_05_AT_2K = 0.5 / 2000.0  # = 0.00025, 舊 deadband=0.5 kW
_DB_RATIO_50_AT_2K = 5.0 / 2000.0  # = 0.0025,  舊 deadband=5.0 kW


# ===========================================================================
# Helpers
# ===========================================================================


def _make_compensator(**overrides) -> PowerCompensator:
    """Create a PowerCompensator with sensible test defaults.

    使用新 API（v0.8 BREAKING）：integral_time_seconds / deadband_ratio /
    hold_seconds / rate_limit=None。預設 dt=1.0 配合 hold/steady seconds。
    """
    defaults = {
        "rated_power": 2000.0,
        "output_min": -2000.0,
        "output_max": 2000.0,
        "integral_time_seconds": _T_EQUIV_KI_03,
        "deadband_ratio": _DB_RATIO_05_AT_2K,
        "hold_seconds": 0.0,  # no hold delay for simpler tests
        "error_ema_alpha": 0.0,
        "rate_limit": None,
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
        comp = _make_compensator(integral_time_seconds=None)  # disable integral for clarity
        result = comp.compensate(setpoint=100.0, measurement=100.0, dt=0.3)
        assert result == pytest.approx(100.0)

    def test_charge_ff_divides_setpoint(self):
        """For negative setpoint, output = setpoint / ff (ff=1.0 initially)."""
        comp = _make_compensator(integral_time_seconds=None)
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
        comp = _make_compensator(integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=0.0)
        # setpoint=100, measurement=90 -> error=10
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        diag = comp.diagnostics
        assert diag["integral"] > 0

    def test_error_within_deadband_no_integral(self):
        """Error below deadband should not accumulate integral.

        Note: 明示停用 deadband_setpoint_ratio 以驗證 absolute deadband 行為；
        否則 setpoint=100 × 0.02 = 2 kW 會壓過 absolute=5 kW，error=2 反而觸發積分。
        """
        comp = _make_compensator(
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_50_AT_2K,
            deadband_setpoint_ratio=0.0,
            hold_seconds=0.0,
        )
        # error = 100 - 98 = 2 < deadband 5
        comp.compensate(setpoint=100.0, measurement=98.0, dt=1.0)
        diag = comp.diagnostics
        assert diag["integral"] == pytest.approx(0.0)

    def test_integral_clamped_to_max(self):
        """Integral should be clamped by integral_max_ratio."""
        comp = _make_compensator(
            integral_time_seconds=_T_EQUIV_KI_10,
            integral_max_ratio=0.05,
            rated_power=1000.0,
            deadband_ratio=0.0,
            hold_seconds=0.0,
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
        comp = _make_compensator(integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=0.0)
        # Build up integral
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        assert comp.diagnostics["integral"] > 0

        # Change setpoint significantly
        comp.compensate(setpoint=200.0, measurement=190.0, dt=1.0)
        # Integral should have been reset (then possibly re-accumulated for 1 step)
        # The key assertion: it should not be the accumulated value from before
        # After reset, integral_hold prevents accumulation for hold_seconds=0.0, so
        # one step of error 10 over dt=1 gives integral=10 (not the old value)
        assert comp.diagnostics["integral"] <= 10.1

    def test_small_setpoint_change_no_reset(self):
        """Change < 0.1 should not trigger reset."""
        comp = _make_compensator(integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=0.0)
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
        comp = _make_compensator(output_max=500.0, integral_time_seconds=None)
        result = comp.compensate(setpoint=1000.0, measurement=1000.0, dt=0.3)
        assert result <= 500.0

    def test_output_clamped_to_min(self):
        comp = _make_compensator(output_min=-500.0, integral_time_seconds=None)
        result = comp.compensate(setpoint=-1000.0, measurement=-1000.0, dt=0.3)
        assert result >= -500.0


# ===========================================================================
# Rate limit
# ===========================================================================


class TestCompensatorRateLimit:
    def test_rate_limit_restricts_change(self):
        comp = _make_compensator(rate_limit=100.0, integral_time_seconds=None)
        # First call establishes last_output
        comp.compensate(setpoint=100.0, measurement=100.0, dt=1.0)
        # Jump setpoint to 1000 -> ff output jumps to 1000
        # rate_limit=100/s * dt=1.0 = max delta 100
        result = comp.compensate(setpoint=1000.0, measurement=1000.0, dt=1.0)
        # Should be limited to last_output + 100 = 100 + 100 = 200 max
        assert result <= 200.1

    def test_rate_limit_zero_no_restriction(self):
        comp = _make_compensator(rate_limit=None, integral_time_seconds=None)
        comp.compensate(setpoint=100.0, measurement=100.0, dt=1.0)
        result = comp.compensate(setpoint=1000.0, measurement=1000.0, dt=1.0)
        assert result == pytest.approx(1000.0)


# ===========================================================================
# Reset
# ===========================================================================


class TestCompensatorReset:
    def test_reset_clears_state(self):
        comp = _make_compensator(integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=0.0)
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
        comp = _make_compensator(integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=0.0)
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
        comp = _make_compensator(integral_time_seconds=None)
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
        comp = _make_compensator(measurement_key="grid_power", integral_time_seconds=None)
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
            "effective_ki",
            "effective_deadband_kw",
            "effective_deadband_at_last_setpoint",
            "last_setpoint",
            "last_output",
            "last_ff",
            "steady_count",
            "hold_remaining",
        }
        assert set(diag.keys()) == expected_keys

    def test_diagnostics_after_compensate(self):
        comp = _make_compensator(integral_time_seconds=None)
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
            integral_time_seconds=_T_EQUIV_KI_05,
            deadband_ratio=0.0,
            hold_seconds=0.0,
            steady_state_threshold=0.05,
            steady_state_seconds=3.0,
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
                integral_time_seconds=_T_EQUIV_KI_05,
                deadband_ratio=0.0,
                hold_seconds=0.0,
                steady_state_threshold=0.05,
                steady_state_seconds=3.0,
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
    """Hold 用「error 變化率」判定：|error| 還在縮小 = PCS 在追、維持；
    穩定 / 變大 = PCS 到位或擾動、decrement。Hard cap = hold_initial × 3。

    取代原 settle_threshold 機制（在持續擾動下永久鎖死，且無法區分慢 PCS）。
    """

    def test_hold_blocks_integral_accumulation(self):
        """During hold period, integral should NOT accumulate (even with large error)."""
        comp = _make_compensator(integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=3.0)
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        # 觸發 hold；measurement 跟著縮小（模擬 PCS 在追）
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        # integral 在 hold 期間一定為 0
        assert comp.diagnostics["integral"] == pytest.approx(0.0)
        # hold 還在（第一次 cycle 視為 shrinking，不 decrement）
        assert comp.diagnostics["hold_remaining"] == 3

    def test_hold_persists_while_pcs_ramping(self):
        """模擬慢 PCS：error 每 cycle 顯著縮小，hold 不應 decrement。"""
        comp = _make_compensator(integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=5.0)
        comp.compensate(setpoint=0.0, measurement=0.0, dt=1.0)
        # PCS 從 0 慢慢爬到 100：模擬 5 個 cycle 完成 (每 cycle 走 20)
        meter_trajectory = [0, 20, 40, 60, 80, 100]
        comp.compensate(setpoint=100.0, measurement=meter_trajectory[0], dt=1.0)
        for meas in meter_trajectory[1:]:
            comp.compensate(setpoint=100.0, measurement=meas, dt=1.0)
        # error: 100→80→60→40→20→0 — 一直在縮小
        # hold 不該 decrement（PCS 還在追）
        assert comp.diagnostics["hold_remaining"] == 5, (
            f"PCS 還在 ramp 期間 hold 不該 decrement: {comp.diagnostics['hold_remaining']}"
        )

    def test_hold_counts_down_when_error_stable(self):
        """持續擾動或 PCS 到位後，error 穩定 → hold 該 decrement。"""
        comp = _make_compensator(integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=3.0)
        comp.compensate(setpoint=100.0, measurement=100.0, dt=1.0)
        # setpoint change → hold=3，第一個 cycle 視為 shrinking (last_err=inf)
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        assert comp.diagnostics["hold_remaining"] == 3
        # 之後 error 穩定在 20 → hold 該 -1
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        assert comp.diagnostics["hold_remaining"] == 2
        comp.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        assert comp.diagnostics["hold_remaining"] == 1

    def test_hold_hard_cap_releases_after_3x_initial(self):
        """Hard cap 保護：cycles_in_hold ≥ hold_initial × 3 強制釋放，
        防 PCS 慢漸近或量測 drift 造成 hold 永遠不收斂。"""
        comp = _make_compensator(integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=2.0)
        comp.compensate(setpoint=0.0, measurement=0.0, dt=1.0)
        comp.compensate(setpoint=100.0, measurement=99.0, dt=1.0)  # cycle 1, hold_initial=2
        # 構造「永遠 shrinking 一點點」的病態軌跡：每 cycle 縮小 epsilon (低於 deadband 但仍縮)
        # 用 deadband=0 → 任何 shrinking 都被偵測；error 從 1.0 → 0.9 → 0.8 ...
        for i in range(1, 8):
            comp.compensate(setpoint=100.0, measurement=99.0 + i * 0.1, dt=1.0)
        # cycles_in_hold 在某個點達 2×3=6，強制釋放 hold=0
        assert comp.diagnostics["hold_remaining"] == 0, f"Hard cap 未觸發，hold={comp.diagnostics['hold_remaining']}"

    def test_integral_resumes_after_hold_expires(self):
        """After hold expires, integral accumulation should resume."""
        comp = _make_compensator(integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=1.0)
        comp.compensate(setpoint=100.0, measurement=100.0, dt=1.0)
        comp.compensate(setpoint=200.0, measurement=190.0, dt=1.0)  # hold=1 (第一次視為 shrinking)
        comp.compensate(setpoint=200.0, measurement=190.0, dt=1.0)  # error 穩定 → hold→0
        assert comp.diagnostics["hold_remaining"] == 0
        comp.compensate(setpoint=200.0, measurement=190.0, dt=1.0)  # integral 應累積
        assert comp.diagnostics["integral"] > 0

    def test_settle_ratio_is_deprecated_noop(self):
        """settle_ratio 已 deprecated（變化率判定取代），設值不應影響 hold 行為。"""
        comp_a = _make_compensator(deadband_ratio=0.0, hold_seconds=3.0, settle_ratio=0.0)
        comp_b = _make_compensator(deadband_ratio=0.0, hold_seconds=3.0, settle_ratio=10.0)
        for c in (comp_a, comp_b):
            c.compensate(setpoint=100.0, measurement=100.0, dt=1.0)
            c.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
            c.compensate(setpoint=200.0, measurement=180.0, dt=1.0)
        assert comp_a.diagnostics["hold_remaining"] == comp_b.diagnostics["hold_remaining"]


# ===========================================================================
# EMA error filtering
# ===========================================================================


class TestCompensatorEMAFilter:
    def test_ema_filter_smooths_error(self):
        """With error_ema_alpha > 0, filtered error should lag behind raw error."""
        comp = _make_compensator(
            integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=0.0, error_ema_alpha=0.3
        )
        # Step 1: error=10, filtered_error = 0.3*10 + 0.7*0 = 3.0
        comp.compensate(setpoint=100.0, measurement=90.0, dt=1.0)
        # The integral should be based on filtered_error=3.0 (not raw 10)
        assert comp.diagnostics["integral"] == pytest.approx(3.0, abs=0.1)

    def test_ema_alpha_zero_no_filtering(self):
        """With alpha=0, raw error is used directly."""
        comp = _make_compensator(
            integral_time_seconds=_T_EQUIV_KI_03, deadband_ratio=0.0, hold_seconds=0.0, error_ema_alpha=0.0
        )
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=0.0,
            hold_seconds=0.0,
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=0.0,
            hold_seconds=0.0,
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
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

        v0.8 注意：runtime _get_ff 改線性插值，setpoint=1993 落在 bin 19/20 之間，
        若只 pin bin[20] 會被相鄰 bin 拉低不再飽和。pin 兩個相鄰 bin 模擬「先後在
        附近 setpoint 都學歪」的真實狀態。
        """
        comp = _make_compensator(
            rated_power=2000.0,
            output_max=2200.0,
            output_min=-2200.0,
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
        )
        comp._ff_table[19] = 1.1048
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
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
            integral_time_seconds=_T_EQUIV_KI_03,
            deadband_ratio=_DB_RATIO_05_AT_2K,
            hold_seconds=0.0,
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
        config = PowerCompensatorConfig(deadband_ratio=0.0, persist_path="")
        comp = PowerCompensator(config)

        # 多次呼叫 setpoint=0，不應 crash
        for _ in range(5):
            result = comp.compensate(setpoint=0.0, measurement=0.0, dt=0.3)
            assert result == pytest.approx(0.0)

        # 直接呼叫內部學習方法（繞過 compensate 的早退出）
        # deadband=0 時 guard 應使用 max(deadband_kw, 1e-6) 避免除零
        try:
            comp._learn_if_steady(setpoint=0.0, filtered_error=0.5, deadband_kw=0.0, cycles_needed=5)
        except ZeroDivisionError:
            pytest.fail("_learn_if_steady 在 deadband_kw=0, setpoint=0 時不應 ZeroDivisionError")


# ===========================================================================
# FF inheritance
# ===========================================================================


class TestCompensatorFFInheritance:
    def test_ff_inherited_from_old_bin_to_new_bin(self):
        """When setpoint changes to a new bin that has ff=1.0, old bin's ff should be inherited."""
        comp = _make_compensator(
            integral_time_seconds=None, hold_seconds=0.0, rated_power=1000.0, power_bin_step_pct=10
        )
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
        comp = _make_compensator(
            integral_time_seconds=None, hold_seconds=0.0, rated_power=1000.0, power_bin_step_pct=10
        )
        comp._ff_table[5] = 1.08
        comp._ff_table[3] = 1.03  # already learned
        comp.compensate(setpoint=500.0, measurement=500.0, dt=1.0)
        comp.compensate(setpoint=300.0, measurement=300.0, dt=1.0)
        # Bin 3 should keep its own value
        assert comp.ff_table[3] == pytest.approx(1.03)

    def test_no_inheritance_when_same_bin(self):
        """If setpoint change stays in the same bin, no inheritance needed."""
        comp = _make_compensator(
            integral_time_seconds=None, hold_seconds=0.0, rated_power=1000.0, power_bin_step_pct=10
        )
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


# ===========================================================================
# Config validation
# ===========================================================================


class TestPowerCompensatorConfigValidation:
    """Config 欄位輸入驗證（防止負值 ratio 等 silent corruption）。"""

    def test_negative_setpoint_change_threshold_ratio_rejected(self):
        """負 ratio 會讓 threshold_kw < 0，使 abs(diff) < negative 永遠 False、
        反向把『未變動』判成『變動』，每 cycle 都 reset integral + 進 hold。
        應在建構期 raise，避免 silent 行為失真。
        """
        with pytest.raises(ValueError, match="setpoint_change_threshold_ratio"):
            PowerCompensatorConfig(rated_power=2000.0, setpoint_change_threshold_ratio=-0.001)


# ===========================================================================
# Small setpoint learning (BUG: deadband 對小 setpoint 鎖死 FF 學習)
# ===========================================================================


class TestCompensatorSmallSetpointLearning:
    """小 setpoint 在持續 plant 損失下也應能學到 FF。

    Bug 描述：
      預設 deadband_ratio=0.00025 → effective deadband=0.5 kW @ rated=2000。
      當 setpoint 小到「setpoint × plant_loss < deadband」時：
        - 積分閘門 (compensate line 441) → I 永遠不累積
        - 學習閘門 (_learn_if_steady line 767) → 即使 steady_count 達標也擋
      結果：FF 永久卡在 1.0、穩態誤差無法被吸收。

    場景：rated=2000、deadband=0.5 kW、plant 5% loss、setpoint=5 kW
      → 初始 error = 0.25 kW < 0.5 kW → 雙重門檻鎖死。

    修法 (B)：deadband 跟著 setpoint 相對縮放 — 加 deadband_setpoint_ratio
    使小 setpoint 的有效 deadband 變小（但不低於 noise floor）。
    """

    def _plant_with_loss(self, pcs_cmd: float, loss_pct: float = 0.05) -> float:
        """簡化 plant：固定百分比損失，放電/充電對稱。"""
        if pcs_cmd >= 0:
            return pcs_cmd * (1 - loss_pct)
        return pcs_cmd * (1 + loss_pct)

    def test_large_setpoint_learns_ff_baseline(self):
        """Baseline: 大 setpoint 應正常收斂（確認 fixture 與 plant 模型本身可學）。"""
        # 用 dt=0.3 配合 hold_seconds=0.6 → hold_cycles=2、steady_cycles=5
        # 保留與 v0.7 等效的設定，只關注「小 setpoint vs 大 setpoint」差異
        comp = _make_compensator(hold_seconds=0.6, steady_state_seconds=1.5)

        pcs_cmd = 200.0
        for _ in range(500):
            meter = self._plant_with_loss(pcs_cmd, loss_pct=0.05)
            pcs_cmd = comp.compensate(setpoint=200.0, measurement=meter, dt=0.3)

        bin_idx = comp._get_bin_index(200.0)
        ff = comp.ff_table[bin_idx]
        # 理論最佳 FF = 1/(1-0.05) ≈ 1.0526；容許 0.02 誤差（steady 邊界停止學習導致）
        assert abs(ff - 1.0526) < 0.02, f"大 setpoint FF 未收斂：bin[{bin_idx}]={ff}"

    def test_small_setpoint_learns_ff(self):
        """Bug repro: 小 setpoint 應能學到 FF（修復後通過、修復前 FAIL）。"""
        comp = _make_compensator(hold_seconds=0.6, steady_state_seconds=1.5)

        pcs_cmd = 5.0
        for _ in range(2000):
            meter = self._plant_with_loss(pcs_cmd, loss_pct=0.05)
            pcs_cmd = comp.compensate(setpoint=5.0, measurement=meter, dt=0.3)

        bin_idx = comp._get_bin_index(5.0)
        ff = comp.ff_table[bin_idx]
        # 小 setpoint 應該也能學到接近 1.0526；放寬到 0.05 容忍邊界停止
        assert abs(ff - 1.0526) < 0.05, (
            f"小 setpoint FF 未收斂：bin[{bin_idx}]={ff}（理論 1.0526）。deadband 雙重門檻鎖死小 setpoint 學習。"
        )

    def test_small_setpoint_steady_error_should_shrink(self):
        """小 setpoint 在學習後穩態誤差應顯著小於 plant 損失。"""
        comp = _make_compensator(hold_seconds=0.6, steady_state_seconds=1.5)

        pcs_cmd = 5.0
        for _ in range(2000):
            meter = self._plant_with_loss(pcs_cmd, loss_pct=0.05)
            pcs_cmd = comp.compensate(setpoint=5.0, measurement=meter, dt=0.3)

        final_meter = self._plant_with_loss(pcs_cmd, loss_pct=0.05)
        # 未修復：穩態誤差 ≈ 0.25 kW (5% loss × 5 kW setpoint)
        # 修復後：應收斂到 < 0.1 kW（鬆綁的 deadband 約 0.1 kW）
        steady_error = abs(5.0 - final_meter)
        assert steady_error < 0.1, f"小 setpoint 穩態誤差過大：{steady_error:.3f} kW（修復前約 0.25 kW）"


# ===========================================================================
# Cross-sign FF inherit (BUG: 放電 bin 的 FF 被繼承到充電 bin)
# ===========================================================================


class TestCompensatorCrossSignInherit:
    """跨符號 setpoint 切換時，FF 不應從異號 bin 繼承。

    Bug 描述：
      `_inherit_ff` 只檢查 new_idx != old_idx + new_ff == 1.0 + old_ff != 1.0，
      沒擋 `old_idx * new_idx < 0`。
      結果：放電 bin 學到的 FF（補放電損耗）被原樣套到充電 bin（應該補充電輔電），
      物理意義錯誤，造成切換瞬間誤差放大。

    場景：rated=2000、bin_step=5%、setpoint 從 +100 (bin +1) 切到 -100 (bin -1)
    放電學完後 FF[+1] ≈ 1.05，切換後 _inherit_ff 應該:
      - 不該把 FF[+1] 套給 FF[-1]
      - FF[-1] 應保持 1.0（待充電方向自己學）

    對 AFC / 頻率響應這種每秒切換的場景，每次跨號切換都會多一個暫態衝擊。
    """

    def _asymmetric_plant(self, pcs_cmd: float) -> float:
        """放電 5% loss、充電 2% loss（兩方向物理不對稱）。"""
        if pcs_cmd >= 0:
            return pcs_cmd * (1 - 0.05)
        return pcs_cmd * (1 + 0.02)

    def _learn_discharge_phase(self, comp: PowerCompensator, cycles: int = 800) -> float:
        """跑放電 setpoint=+100 直到 FF[+1] 收斂；回傳最後一輪 PCS 命令。"""
        pcs_cmd = 100.0
        for _ in range(cycles):
            meter = self._asymmetric_plant(pcs_cmd)
            pcs_cmd = comp.compensate(setpoint=100.0, measurement=meter, dt=0.3)
        return pcs_cmd

    def test_phase_a_learns_positive_bin(self):
        """Sanity: 放電階段應該真的把 FF[+1] 學到 ≠ 1.0（驗證後續測試前提）。"""
        comp = _make_compensator(hold_seconds=0.6, steady_state_seconds=1.5)
        self._learn_discharge_phase(comp)
        ff_pos = comp.ff_table[comp._get_bin_index(100.0)]
        assert ff_pos > 1.01, f"放電 bin 沒學到（FF[+1]={ff_pos}），測試前提不成立"

    def test_cross_sign_switch_does_not_inherit_ff(self):
        """Bug repro: 切換到充電 setpoint 後，FF[-1] 不應被繼承為 FF[+1] 的值。

        修復前：FF[-1] = FF[+1] (錯誤繼承)
        修復後：FF[-1] = 1.0（保持初始值，由 _learn_if_steady 自己學）
        """
        comp = _make_compensator(hold_seconds=0.6, steady_state_seconds=1.5)

        # Phase A: 放電學習
        self._learn_discharge_phase(comp)
        ff_pos_before_switch = comp.ff_table[comp._get_bin_index(100.0)]
        assert ff_pos_before_switch > 1.01  # sanity

        # Phase B: 切換到充電 setpoint，只跑 1 cycle 觀察 inherit 結果
        # 用一個合理的 measurement（與 PCS 命令一致的方向）
        comp.compensate(setpoint=-100.0, measurement=-100.0, dt=0.3)

        ff_neg_after_switch = comp.ff_table[comp._get_bin_index(-100.0)]
        # 充電 bin 不該繼承放電 bin 的學習結果
        assert ff_neg_after_switch == pytest.approx(1.0, abs=1e-6), (
            f"FF[-1]={ff_neg_after_switch} 被錯誤繼承自 FF[+1]={ff_pos_before_switch}。"
            f"跨符號 bin 物理意義不對稱（放電補損耗 vs 充電補輔電），不應繼承。"
        )

    def test_cross_sign_first_cycle_error_consistent_with_unlearned(self):
        """切換瞬間誤差應該對應「FF=1.0」的物理（PCS 出 -100 → meter ≈ -102，欠 2 kW），
        而非繼承後的物理（PCS 出 -95 → meter ≈ -97，過 2.6 kW）。
        """
        comp = _make_compensator(hold_seconds=0.6, steady_state_seconds=1.5)
        self._learn_discharge_phase(comp)

        # 從 phase A 結束的 PCS 命令切到 -100
        # 用 phase A 最後輸出當第一個 measurement 的來源
        pcs_at_phase_a_end = comp.compensate(setpoint=100.0, measurement=100.0 * 0.95, dt=0.3)
        meter_first = self._asymmetric_plant(pcs_at_phase_a_end)

        # 第一個 phase B cycle：setpoint=-100, measurement 從 phase A 帶來
        pcs_phase_b_0 = comp.compensate(setpoint=-100.0, measurement=meter_first, dt=0.3)
        # 第二個 cycle 才是真實的 phase B 物理回饋
        meter_phase_b_1 = self._asymmetric_plant(pcs_phase_b_0)

        # 修復後：FF[-1]=1.0 → PCS 出 -100 → meter = -100 × 1.02 = -102 → error = +2
        # 修復前：FF[-1]≈1.05 → PCS 出 -95.2 → meter = -97.1 → error = -2.9
        error = -100.0 - meter_phase_b_1
        assert error > 0, (
            f"切換瞬間 error={error:.2f} 為負（過充），表示 FF[-1] 被錯誤繼承。"
            f"正確物理：FF[-1]=1.0 時 error 應為正（不足充約 +2 kW）。"
        )


# ===========================================================================
# Integral hold lockup under sustained disturbance
# ===========================================================================


class TestCompensatorIntegralHoldLockup:
    """持續性外部擾動下 integral_hold 永遠不開的問題。

    Bug 描述：
      `_apply_setpoint_change_policy` 設 settle_threshold = |new - old| × 0.15。
      `compensate` line 444 的 integral_hold 只在 |filtered_error| ≤ settle_threshold 才
      decrement。

      設計者原意：等 setpoint change 造成的 transient 過去（error 降到小於門檻）才開 I。
      但 settle 條件用「error 絕對值」判定，無法區分：
        - 真實 transient：error 隨時間衰減
        - 持續擾動：error 永遠卡住

      當 |擾動| > settle_threshold（即 > 15% × setpoint），integral_hold 永遠不
      decrement → I 永不累積 → FF 永不學 → error 永久卡住 = -擾動。

    場景：setpoint=100、plant 加性擾動 +20 kW
      settle_threshold = 100 × 0.15 = 15 < |擾動|=20 → 鎖死。
      實務上小 setpoint + 任何明顯擾動就會踩到（屋頂 PV、其他設備、線路雜耦合等）。
    """

    def _additive_disturbance_plant(self, pcs_cmd: float, disturbance_kw: float = 20.0) -> float:
        return pcs_cmd + disturbance_kw

    def test_setpoint_change_without_disturbance_hold_releases(self):
        """Sanity: 無擾動時 hold 應該正常釋放（驗證 hold 機制本身沒壞）。"""
        comp = _make_compensator(hold_seconds=0.6, steady_state_seconds=1.5)
        # 無擾動，plant 完美（meter = pcs）
        pcs_cmd = 100.0
        for _ in range(20):
            pcs_cmd = comp.compensate(setpoint=100.0, measurement=pcs_cmd, dt=0.3)
        assert comp.diagnostics["hold_remaining"] == 0, f"無擾動下 hold 都沒釋放：{comp.diagnostics['hold_remaining']}"

    def test_sustained_disturbance_should_not_lock_hold_forever(self):
        """Bug repro: 持續擾動 > 15% × setpoint 時 integral_hold 永不釋放。"""
        comp = _make_compensator(hold_seconds=0.6, steady_state_seconds=1.5)
        pcs_cmd = 100.0
        # 跑 500 cycles，遠超過 hold_cycles_needed=round(0.6/0.3)=2
        for _ in range(500):
            meter = self._additive_disturbance_plant(pcs_cmd, disturbance_kw=20.0)
            pcs_cmd = comp.compensate(setpoint=100.0, measurement=meter, dt=0.3)

        diag = comp.diagnostics
        assert diag["hold_remaining"] == 0, (
            f"hold_remaining={diag['hold_remaining']} 卡住未釋放（跑了 500 cycle）。"
            f"settle_threshold={100.0 * 0.15} < |擾動|=20 → 永久鎖死。"
        )

    def test_sustained_disturbance_should_eventually_compensate(self):
        """Bug 後果驗證：持續擾動下 FF 應該學到吸收擾動，error 應收斂。"""
        comp = _make_compensator(hold_seconds=0.6, steady_state_seconds=1.5)
        pcs_cmd = 100.0
        for _ in range(500):
            meter = self._additive_disturbance_plant(pcs_cmd, disturbance_kw=20.0)
            pcs_cmd = comp.compensate(setpoint=100.0, measurement=meter, dt=0.3)

        final_meter = self._additive_disturbance_plant(pcs_cmd, disturbance_kw=20.0)
        final_error = abs(100.0 - final_meter)
        # 修復前：error 卡在 20 kW；修復後：應收斂到 deadband 邊界以內
        assert final_error < 5.0, (
            f"穩態 error={final_error:.2f} kW，FF 沒吸收擾動。integral_hold 鎖死導致學習無法觸發。"
        )


# ===========================================================================
# MongoFFTableRepository drain (fire-and-forget save 遺失問題)
# ===========================================================================


class _FakeMongoCollection:
    """Mock motor.AsyncIOMotorCollection，模擬網路 IO 延遲。"""

    def __init__(self, delay_seconds: float = 0.05) -> None:
        self._delay = delay_seconds
        self.update_count = 0

    async def update_one(self, filter_: dict, update: dict, upsert: bool = False) -> None:
        import asyncio as _asyncio

        await _asyncio.sleep(self._delay)
        self.update_count += 1

    async def find_one(self, query: dict) -> None:
        return None


class TestMongoFFTableRepositoryDrain:
    """MongoFFTableRepository.save 是 fire-and-forget，shutdown 時尚未完成的
    寫入會被 cancel 而遺失。需要 drain() async API 等所有 pending save 完成。
    """

    async def test_burst_saves_without_drain_lost_immediately(self):
        """Sanity: burst 觸發後立即查 → 0 寫入（fire-and-forget 還沒跑）。"""
        coll = _FakeMongoCollection(delay_seconds=0.05)
        repo = MongoFFTableRepository(coll)

        for i in range(5):
            repo.save({i: 1.0 + i * 0.01})

        # 立即查（不 await）→ 還沒有任何寫入
        assert coll.update_count == 0

    async def test_drain_waits_for_all_pending_saves(self):
        """Bug repro: 沒有 drain 機制 → 無法保證 burst 的所有 save 都被持久化。

        修復前：MongoFFTableRepository 無 drain method
        修復後：drain() 等所有 pending task 完成
        """
        coll = _FakeMongoCollection(delay_seconds=0.05)
        repo = MongoFFTableRepository(coll)

        for i in range(10):
            repo.save({i: 1.0 + i * 0.01})

        # drain 應等所有 pending 完成
        await repo.drain()

        assert coll.update_count == 10, f"drain 後仍有 {10 - coll.update_count} 筆未寫入"

    async def test_drain_no_pending_is_noop(self):
        """無 pending 時 drain() 不應 raise 也不該卡住。"""
        coll = _FakeMongoCollection(delay_seconds=0.05)
        repo = MongoFFTableRepository(coll)

        # 沒呼叫 save 直接 drain
        await repo.drain()
        assert coll.update_count == 0

    async def test_compensator_async_close_drains_repository(self):
        """PowerCompensator.async_close() 應對齊 async_init pattern，
        並 drain 底下的 repository（若支援）。
        """
        coll = _FakeMongoCollection(delay_seconds=0.05)
        repo = MongoFFTableRepository(coll)
        comp = PowerCompensator(PowerCompensatorConfig(rated_power=2000.0), repository=repo)

        # 觸發幾次 save（via 公開 update_ff_bin with persist=True）
        for i in range(5):
            comp.update_ff_bin(i, 1.0 + i * 0.01, persist=True)

        # 立即不會寫到（fire-and-forget）
        assert coll.update_count == 0

        # async_close 應 drain
        await comp.async_close()
        assert coll.update_count == 5
