"""Tests for FFCalibrationStrategy."""

from __future__ import annotations

import pytest

from csp_lib.controller.calibration import FFCalibrationConfig, FFCalibrationStrategy
from csp_lib.controller.core import Command, StrategyContext, SystemBase


def _make_context(measurement: float | None = None, last_p: float = 0.0) -> StrategyContext:
    """Helper to create a StrategyContext with measurement in extra."""
    extra: dict = {}
    if measurement is not None:
        extra["meter_power"] = measurement
    return StrategyContext(
        last_command=Command(p_target=last_p),
        soc=50.0,
        system_base=SystemBase(p_base=2000.0),
        extra=extra,
    )


class TestFFCalibrationConfig:
    def test_default_config(self):
        cfg = FFCalibrationConfig()
        assert cfg.step_pct == 5
        assert cfg.min_pct == -100
        assert cfg.max_pct == 100
        assert cfg.skip_zero is True
        assert cfg.steady_cycles == 10

    def test_validate_invalid_step(self):
        cfg = FFCalibrationConfig(step_pct=0)
        with pytest.raises(ValueError, match="step_pct"):
            cfg.validate()

    def test_validate_invalid_range(self):
        cfg = FFCalibrationConfig(min_pct=50, max_pct=10)
        with pytest.raises(ValueError, match="min_pct"):
            cfg.validate()


class TestFFCalibrationStrategy:
    def test_initial_state_is_idle(self):
        cal = FFCalibrationStrategy()
        assert cal.state == "idle"

    @pytest.mark.asyncio
    async def test_activate_transitions_to_stepping(self):
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(step_pct=10, min_pct=10, max_pct=20),
            rated_power=1000.0,
        )
        await cal.on_activate()
        assert cal.state == "stepping"
        assert cal.progress["total_bins"] > 0

    @pytest.mark.asyncio
    async def test_idle_returns_last_command(self):
        cal = FFCalibrationStrategy(rated_power=1000.0)
        ctx = _make_context(measurement=100.0, last_p=500.0)
        cmd = cal.execute(ctx)
        assert cmd.p_target == 500.0  # IDLE → returns last_command

    @pytest.mark.asyncio
    async def test_stepping_outputs_bin_power(self):
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(step_pct=10, min_pct=10, max_pct=10, steady_cycles=3, settle_wait_cycles=0),
            rated_power=1000.0,
        )
        await cal.on_activate()
        ctx = _make_context(measurement=100.0)
        cmd = cal.execute(ctx)
        # bin=1, step=10% → setpoint = 1000 * 1 * 10 / 100 = 100kW
        assert cmd.p_target == 100.0

    @pytest.mark.asyncio
    async def test_steady_state_records_ff(self):
        """When measurement matches setpoint for N cycles, FF is recorded."""
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(
                step_pct=50, min_pct=50, max_pct=50,
                steady_cycles=3, settle_wait_cycles=0, steady_threshold=0.05,
            ),
            rated_power=1000.0,
        )
        await cal.on_activate()

        # bin=1, step=50% → setpoint=500kW, measurement=480kW (within 5%)
        ctx = _make_context(measurement=480.0)
        for _ in range(3):
            cal.execute(ctx)

        # After 3 steady cycles → FF recorded, moves to negative bins
        assert len(cal.results) == 1
        assert 1 in cal.results
        # ff = 500 / 480 ≈ 1.0417
        assert abs(cal.results[1] - 500.0 / 480.0) < 0.01

    @pytest.mark.asyncio
    async def test_full_calibration_completes(self):
        """Single positive + single negative bin → DONE."""
        completed = []

        async def on_done(results):
            completed.append(results)

        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(
                step_pct=100, min_pct=-100, max_pct=100,
                steady_cycles=2, settle_wait_cycles=0, steady_threshold=0.05,
            ),
            compensator=None,
            rated_power=1000.0,
            on_complete=on_done,
        )
        await cal.on_activate()

        # bin=1 (100%): setpoint=1000, measurement=980 (2% error, within 5%)
        ctx_pos = _make_context(measurement=980.0)
        cal.execute(ctx_pos)
        cal.execute(ctx_pos)  # 2 steady cycles → record, move to bin=-1

        # bin=-1 (-100%): setpoint=-1000, measurement=-980 (2% error)
        ctx_neg = _make_context(measurement=-980.0)
        for _ in range(cal._config.settle_wait_cycles):
            cal.execute(ctx_neg)  # settle wait
        cal.execute(ctx_neg)
        cal.execute(ctx_neg)  # 2 steady cycles → record, DONE

        assert cal.state == "done"
        assert len(cal.results) == 2
        assert 1 in cal.results
        assert -1 in cal.results

    @pytest.mark.asyncio
    async def test_done_returns_zero(self):
        """After DONE, execute returns P=0."""
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(
                step_pct=100, min_pct=100, max_pct=100,
                steady_cycles=1, settle_wait_cycles=0,
            ),
            rated_power=1000.0,
        )
        await cal.on_activate()

        ctx = _make_context(measurement=1000.0)
        cal.execute(ctx)  # 1 cycle → DONE

        cmd = cal.execute(ctx)
        assert cmd.p_target == 0.0
        assert cal.state == "done"

    @pytest.mark.asyncio
    async def test_deactivate_during_stepping_does_not_write_ff(self):
        """Interrupting calibration should NOT update compensator."""

        class FakeCompensator:
            def __init__(self):
                self._ff_table = {1: 1.0}
                self.saved = False

            def _save_ff_table(self):
                self.saved = True

        comp = FakeCompensator()
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(step_pct=100, min_pct=100, max_pct=100, steady_cycles=100),
            compensator=comp,
            rated_power=1000.0,
        )
        await cal.on_activate()
        assert cal.state == "stepping"

        # Interrupt before completion
        await cal.on_deactivate()
        assert cal.state == "idle"
        assert comp._ff_table[1] == 1.0  # unchanged
        assert not comp.saved

    @pytest.mark.asyncio
    async def test_compensator_ff_table_updated_on_completion(self):
        """Completed calibration writes FF table to compensator."""

        class FakeCompensator:
            def __init__(self):
                self._ff_table = {1: 1.0}
                self.saved = False

            def _save_ff_table(self):
                self.saved = True

        comp = FakeCompensator()
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(
                step_pct=100, min_pct=100, max_pct=100,
                steady_cycles=1, settle_wait_cycles=0,
            ),
            compensator=comp,
            rated_power=1000.0,
        )
        await cal.on_activate()

        ctx = _make_context(measurement=990.0)
        cal.execute(ctx)  # 1 cycle → DONE

        assert comp._ff_table[1] != 1.0  # updated
        assert comp.saved

    @pytest.mark.asyncio
    async def test_settle_wait_skips_cycles(self):
        """After switching bins, settle_wait_cycles are skipped."""
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(
                step_pct=100, min_pct=100, max_pct=100,
                steady_cycles=1, settle_wait_cycles=3,
            ),
            rated_power=1000.0,
        )
        await cal.on_activate()

        ctx = _make_context(measurement=1000.0)
        # First 3 cycles: settle wait (initial settle)
        for _ in range(3):
            cal.execute(ctx)
            assert cal.state == "stepping"

        # 4th cycle: actual steady state check
        cal.execute(ctx)
        assert cal.state == "done"

    def test_progress_property(self):
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(step_pct=10, min_pct=10, max_pct=20),
            rated_power=1000.0,
        )
        prog = cal.progress
        assert prog["state"] == "idle"
        assert prog["total_bins"] == 0
        assert prog["completed_bins"] == 0

    @pytest.mark.asyncio
    async def test_no_measurement_continues(self):
        """If no measurement available, still outputs setpoint."""
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(step_pct=10, min_pct=10, max_pct=10),
            rated_power=1000.0,
        )
        await cal.on_activate()

        ctx = _make_context(measurement=None)
        cmd = cal.execute(ctx)
        assert cmd.p_target == 100.0  # Still outputs setpoint

    def test_str_repr(self):
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(step_pct=5, min_pct=-50, max_pct=50),
        )
        s = str(cal)
        assert "FFCalibrationStrategy" in s
        assert "5%" in s
        assert "idle" in s

    @pytest.mark.asyncio
    async def test_skip_zero_excludes_zero_bin(self):
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(step_pct=50, min_pct=-50, max_pct=50, skip_zero=True),
            rated_power=1000.0,
        )
        await cal.on_activate()
        # With skip_zero=True, bin 0 should not be in sequence
        assert 0 not in cal._bin_sequence

    @pytest.mark.asyncio
    async def test_include_zero_when_not_skipped(self):
        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(step_pct=50, min_pct=0, max_pct=50, skip_zero=False),
            rated_power=1000.0,
        )
        await cal.on_activate()
        assert 0 in cal._bin_sequence
