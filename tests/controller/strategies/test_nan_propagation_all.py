"""
NaN / Inf propagation tests for all numeric strategies.

Verifies that each strategy does not silently propagate NaN or Inf into
output Commands.  Where the current implementation DOES propagate bad
values, the test documents that behaviour so a future guard can be added
without breaking the existing assertion.

Strategies covered:
  - PQModeStrategy  (config-driven)
  - QVStrategy      (voltage droop)
  - FPStrategy      (frequency-power curve)
  - IslandModeStrategy (pass-through via last_command)

PVSmoothStrategy is already covered in test_nan_propagation.py.
"""

import math
from typing import Union

import pytest

from csp_lib.controller.core import Command, StrategyContext, SystemBase
from csp_lib.controller.strategies.fp_strategy import FPConfig, FPStrategy
from csp_lib.controller.strategies.island_strategy import IslandModeConfig, IslandModeStrategy
from csp_lib.controller.strategies.pq_strategy import PQModeConfig, PQModeStrategy
from csp_lib.controller.strategies.qv_strategy import QVConfig, QVStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BadFloat = Union[float, float]  # float("nan"), float("inf"), float("-inf")

BAD_FLOATS: list[tuple[str, float]] = [
    ("nan", float("nan")),
    ("inf", float("inf")),
    ("-inf", float("-inf")),
]


def _has_nan(cmd: Command) -> bool:
    """Return True if either target field is NaN."""
    return math.isnan(cmd.p_target) or math.isnan(cmd.q_target)


def _has_inf(cmd: Command) -> bool:
    """Return True if either target field is +/-Inf."""
    return math.isinf(cmd.p_target) or math.isinf(cmd.q_target)


def _has_bad_float(cmd: Command) -> bool:
    """Return True if either target field is NaN or +/-Inf."""
    return _has_nan(cmd) or _has_inf(cmd)


# ---------------------------------------------------------------------------
# Fake relay for IslandModeStrategy
# ---------------------------------------------------------------------------


class FakeRelay:
    """Minimal implementation of RelayProtocol for testing."""

    def __init__(self) -> None:
        self._sync_ok = False
        self._sync_counter = 0

    @property
    def sync_ok(self) -> bool:
        return self._sync_ok

    @property
    def sync_counter(self) -> int:
        return self._sync_counter

    async def set_open(self) -> None:
        pass

    async def set_close(self) -> None:
        pass

    async def set_force_close(self) -> None:
        pass


# ===================================================================
# PQModeStrategy
# ===================================================================


class TestPQModeStrategyNaNInf:
    """PQModeStrategy takes P/Q from config, so bad values come from config fields."""

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_bad_p_in_config(self, label: str, bad_value: float) -> None:
        """When config.p is NaN/Inf the output Command.p_target mirrors it."""
        config = PQModeConfig(p=bad_value, q=50.0)
        strategy = PQModeStrategy(config)
        ctx = StrategyContext(last_command=Command(0.0, 0.0))

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        # PQ passes config value through verbatim -- bad float propagates.
        if math.isnan(bad_value):
            assert math.isnan(result.p_target), "NaN in config.p should propagate to p_target"
        else:
            assert math.isinf(result.p_target), "Inf in config.p should propagate to p_target"
        # q_target should remain clean
        assert result.q_target == 50.0

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_bad_q_in_config(self, label: str, bad_value: float) -> None:
        """When config.q is NaN/Inf the output Command.q_target mirrors it."""
        config = PQModeConfig(p=100.0, q=bad_value)
        strategy = PQModeStrategy(config)
        ctx = StrategyContext(last_command=Command(0.0, 0.0))

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        assert result.p_target == 100.0
        if math.isnan(bad_value):
            assert math.isnan(result.q_target), "NaN in config.q should propagate to q_target"
        else:
            assert math.isinf(result.q_target), "Inf in config.q should propagate to q_target"

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_both_fields_bad(self, label: str, bad_value: float) -> None:
        """Both config fields carry a bad float -> both targets are tainted."""
        config = PQModeConfig(p=bad_value, q=bad_value)
        strategy = PQModeStrategy(config)
        ctx = StrategyContext(last_command=Command(0.0, 0.0))

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        assert _has_bad_float(result), f"Expected bad float in Command for {label}"


# ===================================================================
# QVStrategy
# ===================================================================


class TestQVStrategyNaNInf:
    """QVStrategy reads context.extra['voltage'] and does droop arithmetic."""

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_bad_voltage_no_system_base(self, label: str, bad_value: float) -> None:
        """Bad voltage without system_base -> q_target comes from ratio calc directly.

        NaN: v_pu = NaN/380 = NaN.  Both ``<=`` and ``>=`` comparisons with NaN
        return False, so _calculate_q_ratio falls through to the deadband
        ``return 0.0``.  The NaN is silently swallowed -- no error, but the
        result is *wrong* (indistinguishable from a genuine deadband zero).

        +/-Inf: v_pu = Inf/380 = Inf.  ``Inf >= v_set_pu + deadband`` is True
        so the high-voltage branch fires and the ratio calculation produces
        -Inf, which is then clamped by ``max(..., -q_max_ratio)``.
        """
        config = QVConfig(nominal_voltage=380.0, v_set=100.0, droop=5.0)
        strategy = QVStrategy(config)
        ctx = StrategyContext(
            last_command=Command(10.0, 0.0),
            extra={"voltage": bad_value},
        )

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        # QV 只管 Q，P 固定為 0
        assert result.p_target == 0.0
        if math.isnan(bad_value):
            # NaN falls through all if-branches into deadband -> 0.0
            assert result.q_target == 0.0, (
                "NaN voltage silently falls into deadband (q=0); "
                "this is silent data corruption -- no NaN propagation, but wrong result"
            )
        elif bad_value == float("inf"):
            # +Inf enters high-voltage branch, ratio = -Inf, clamped to -q_max_ratio
            assert result.q_target == -config.q_max_ratio
        else:
            # -Inf enters low-voltage branch, ratio = +Inf, clamped to +q_max_ratio
            assert result.q_target == config.q_max_ratio

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_bad_voltage_with_system_base(self, label: str, bad_value: float) -> None:
        """Bad voltage with system_base -> percent_to_kvar amplifies the result.

        NaN case: same deadband fall-through as no-system-base variant,
        so q_ratio=0 -> kvar=0.  Inf case: clamped ratio * q_base.
        """
        config = QVConfig(nominal_voltage=380.0, v_set=100.0, droop=5.0)
        strategy = QVStrategy(config)
        q_base = 500.0
        ctx = StrategyContext(
            last_command=Command(10.0, 0.0),
            system_base=SystemBase(p_base=500.0, q_base=q_base),
            extra={"voltage": bad_value},
        )

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        # QV 只管 Q，P 固定為 0
        assert result.p_target == 0.0
        if math.isnan(bad_value):
            # NaN -> deadband 0.0 ratio -> percent_to_kvar(0) = 0
            assert result.q_target == 0.0, "NaN voltage silently produces q=0 via deadband"
        elif bad_value == float("inf"):
            # +Inf -> clamped to -q_max_ratio -> kvar
            expected = (-config.q_max_ratio * 100) * q_base / 100
            assert result.q_target == expected
        else:
            # -Inf -> clamped to +q_max_ratio -> kvar
            expected = (config.q_max_ratio * 100) * q_base / 100
            assert result.q_target == expected

    def test_missing_voltage_returns_last_command(self) -> None:
        """No voltage in context -> returns last_command unchanged (no NaN injection)."""
        strategy = QVStrategy(QVConfig())
        last = Command(42.0, 7.0)
        ctx = StrategyContext(last_command=last)

        result = strategy.execute(ctx)

        assert result is last
        assert not _has_bad_float(result)

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_bad_last_command_p_not_preserved(self, label: str, bad_value: float) -> None:
        """QV 只管 Q，P 固定為 0，不再傳播 last_command 的 bad p_target。"""
        config = QVConfig(nominal_voltage=380.0, v_set=100.0, droop=5.0)
        strategy = QVStrategy(config)
        ctx = StrategyContext(
            last_command=Command(p_target=bad_value, q_target=0.0),
            extra={"voltage": 380.0},  # normal voltage
        )

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        assert result.p_target == 0.0, "QV should output p_target=0, not propagate last_command"

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_bad_nominal_voltage_in_config(self, label: str, bad_value: float) -> None:
        """Bad nominal_voltage in config causes division by bad float in _calculate_q_ratio."""
        # Note: NaN nominal_voltage would fail validation, but config.validate() is optional.
        config = QVConfig(nominal_voltage=bad_value, v_set=100.0, droop=5.0)
        strategy = QVStrategy(config)
        ctx = StrategyContext(
            last_command=Command(0.0, 0.0),
            extra={"voltage": 380.0},
        )

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        # v_pu = 380 / NaN = NaN, or 380 / inf = 0.0
        # For NaN: all comparisons fail -> falls through to return 0.0 (deadband)
        # For Inf: v_pu = 0.0 -> low voltage path -> ratio calc
        # For -Inf: v_pu = 380 / -inf = -0.0 -> low voltage path
        assert isinstance(result.q_target, float)  # Should be a float, may or may not be bad


# ===================================================================
# FPStrategy
# ===================================================================


class TestFPStrategyNaNInf:
    """FPStrategy reads context.extra['frequency'] and does piecewise interpolation."""

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_bad_frequency_no_system_base(self, label: str, bad_value: float) -> None:
        """Bad frequency without system_base -> p_target from _calculate_power directly."""
        config = FPConfig(f_base=60.0)
        strategy = FPStrategy(config)
        ctx = StrategyContext(
            last_command=Command(0.0, 0.0),
            extra={"frequency": bad_value},
        )

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        assert result.q_target == 0.0, "FP always sets q_target=0"
        if math.isnan(bad_value):
            # NaN: all comparisons (< f1, <= f2 ...) return False -> falls through to p6
            assert isinstance(result.p_target, float)
        elif math.isinf(bad_value) and bad_value > 0:
            # +Inf: frequency >= f6 is True -> returns p6 (max charge, -100)
            assert result.p_target == config.p6
        else:
            # -Inf: frequency < f1 is True -> returns p1 (max discharge, 100)
            assert result.p_target == config.p1

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_bad_frequency_with_system_base(self, label: str, bad_value: float) -> None:
        """Bad frequency with system_base -> percent_to_kw amplifies the result."""
        config = FPConfig(f_base=60.0)
        strategy = FPStrategy(config)
        ctx = StrategyContext(
            last_command=Command(0.0, 0.0),
            system_base=SystemBase(p_base=1000.0, q_base=500.0),
            extra={"frequency": bad_value},
        )

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        assert result.q_target == 0.0
        if math.isnan(bad_value):
            # NaN falls through all comparisons -> returns p6 -> percent_to_kw(p6)
            # p6 = -100, so p_kw = -100 * 1000 / 100 = -1000
            assert isinstance(result.p_target, float)
        elif math.isinf(bad_value) and bad_value > 0:
            # +Inf -> p6 = -100 -> p_kw = -1000
            expected = config.p6 * 1000.0 / 100.0
            assert result.p_target == expected
        else:
            # -Inf -> p1 = 100 -> p_kw = 1000
            expected = config.p1 * 1000.0 / 100.0
            assert result.p_target == expected

    def test_missing_frequency_returns_last_command(self) -> None:
        """No frequency in context -> returns last_command unchanged."""
        strategy = FPStrategy(FPConfig())
        last = Command(42.0, 7.0)
        ctx = StrategyContext(last_command=last)

        result = strategy.execute(ctx)

        assert result is last
        assert not _has_bad_float(result)

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_bad_f_base_in_config(self, label: str, bad_value: float) -> None:
        """Bad f_base in config poisons the absolute frequency calculation."""
        config = FPConfig(f_base=bad_value)
        strategy = FPStrategy(config)
        ctx = StrategyContext(
            last_command=Command(0.0, 0.0),
            extra={"frequency": 60.0},
        )

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        # f_base + offset = NaN/Inf + offset -- comparison results vary
        assert isinstance(result.p_target, float)

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_nan_frequency_falls_through_to_p6(self, label: str, bad_value: float) -> None:
        """
        Detailed check: NaN frequency causes all if-comparisons to be False,
        so _calculate_power falls through every branch and returns cfg.p6.

        For Inf: +Inf >= f6 -> True -> p6;  -Inf < f1 -> True -> p1.
        """
        config = FPConfig(f_base=60.0)
        strategy = FPStrategy(config)

        power = strategy._calculate_power(bad_value)

        if math.isnan(bad_value):
            # All comparisons with NaN are False -> falls through to the final return cfg.p6
            assert power == config.p6, "NaN should fall through all branches to p6"
        elif bad_value == float("inf"):
            assert power == config.p6, "+Inf >= f6 should return p6"
        else:
            assert power == config.p1, "-Inf < f1 should return p1"


# ===================================================================
# IslandModeStrategy
# ===================================================================


class TestIslandModeStrategyNaNInf:
    """
    IslandModeStrategy.execute() returns context.last_command verbatim.
    Bad floats in last_command pass through unchanged.
    """

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_bad_p_in_last_command(self, label: str, bad_value: float) -> None:
        """Bad p_target in last_command is returned as-is."""
        relay = FakeRelay()
        strategy = IslandModeStrategy(relay, config=IslandModeConfig())
        ctx = StrategyContext(last_command=Command(p_target=bad_value, q_target=0.0))

        result = strategy.execute(ctx)

        assert result is ctx.last_command, "IslandMode should return last_command object"
        if math.isnan(bad_value):
            assert math.isnan(result.p_target)
        else:
            assert math.isinf(result.p_target)

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_bad_q_in_last_command(self, label: str, bad_value: float) -> None:
        """Bad q_target in last_command is returned as-is."""
        relay = FakeRelay()
        strategy = IslandModeStrategy(relay, config=IslandModeConfig())
        ctx = StrategyContext(last_command=Command(p_target=0.0, q_target=bad_value))

        result = strategy.execute(ctx)

        assert result is ctx.last_command
        if math.isnan(bad_value):
            assert math.isnan(result.q_target)
        else:
            assert math.isinf(result.q_target)

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_both_targets_bad(self, label: str, bad_value: float) -> None:
        """Both targets bad -> both propagate through."""
        relay = FakeRelay()
        strategy = IslandModeStrategy(relay, config=IslandModeConfig())
        ctx = StrategyContext(last_command=Command(p_target=bad_value, q_target=bad_value))

        result = strategy.execute(ctx)

        assert _has_bad_float(result), f"Expected bad float in result for {label}"


# ===================================================================
# Cross-strategy: NaN in SystemBase
# ===================================================================


class TestSystemBaseNaNInf:
    """
    SystemBase is used by QV and FP to convert percent -> kW/kVar.
    Bad floats in SystemBase.p_base or q_base corrupt the conversion.
    """

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_qv_bad_q_base(self, label: str, bad_value: float) -> None:
        """QV with bad q_base in SystemBase -> q_target is tainted."""
        config = QVConfig(nominal_voltage=380.0, v_set=100.0, droop=5.0)
        strategy = QVStrategy(config)
        ctx = StrategyContext(
            last_command=Command(10.0, 0.0),
            system_base=SystemBase(p_base=500.0, q_base=bad_value),
            extra={"voltage": 370.0},  # below nominal -> positive Q ratio
        )

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        # q_target = q_ratio * 100 * bad_value / 100 = q_ratio * bad_value
        if math.isnan(bad_value):
            assert math.isnan(result.q_target), "NaN q_base should produce NaN q_target"
        else:
            assert math.isinf(result.q_target), "Inf q_base should produce Inf q_target"

    @pytest.mark.parametrize("label,bad_value", BAD_FLOATS, ids=[t[0] for t in BAD_FLOATS])
    def test_fp_bad_p_base(self, label: str, bad_value: float) -> None:
        """FP with bad p_base in SystemBase -> p_target is tainted."""
        config = FPConfig(f_base=60.0)
        strategy = FPStrategy(config)
        ctx = StrategyContext(
            last_command=Command(0.0, 0.0),
            system_base=SystemBase(p_base=bad_value, q_base=500.0),
            extra={"frequency": 59.5},  # below f1 -> p1 = 100%
        )

        result = strategy.execute(ctx)

        assert isinstance(result, Command)
        # p_kw = 100 * bad_value / 100 = bad_value
        if math.isnan(bad_value):
            assert math.isnan(result.p_target), "NaN p_base should produce NaN p_target"
        else:
            assert math.isinf(result.p_target), "Inf p_base should produce Inf p_target"
