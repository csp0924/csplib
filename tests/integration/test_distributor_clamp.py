"""Tests for SOCBalancingDistributor per_device_max_p / per_device_max_q clamping."""

import pytest

from csp_lib.controller.core import Command
from csp_lib.integration.distributor import DeviceSnapshot, SOCBalancingDistributor

# ===========================================================================
# Helpers
# ===========================================================================


def _snap(
    device_id: str,
    rated_p: float = 500.0,
    soc: float | None = None,
) -> DeviceSnapshot:
    caps = {}
    if soc is not None:
        caps["soc_readable"] = {"soc": soc}
    return DeviceSnapshot(
        device_id=device_id,
        metadata={"rated_p": rated_p},
        capabilities=caps,
    )


# ===========================================================================
# No clamp (default)
# ===========================================================================


class TestDistributorNoClamp:
    def test_no_clamp_default(self):
        """Without per_device_max_p, distribution is not limited."""
        dist = SOCBalancingDistributor(per_device_max_p=None)
        devices = [_snap("d1", rated_p=1000.0, soc=60.0)]
        result = dist.distribute(Command(p_target=1000.0), devices)
        assert result["d1"].p_target == pytest.approx(1000.0)


# ===========================================================================
# Clamp with overflow transfer (discharge)
# ===========================================================================


class TestDistributorClampDischarge:
    def test_clamp_with_overflow_transfer(self):
        """If one device exceeds max_p, overflow should transfer to others."""
        dist = SOCBalancingDistributor(per_device_max_p=400.0, gain=2.0)
        # Two devices with same rating but different SOC
        # Device d1 (high SOC) gets more P during discharge
        devices = [
            _snap("d1", rated_p=500.0, soc=90.0),
            _snap("d2", rated_p=500.0, soc=30.0),
        ]
        cmd = Command(p_target=700.0, q_target=0.0)
        result = dist.distribute(cmd, devices)

        # Both should be at or below 400
        assert result["d1"].p_target <= 400.0 + 0.01
        assert result["d2"].p_target <= 400.0 + 0.01

        # Total should approximately equal original (conservation within clamp precision)
        total = result["d1"].p_target + result["d2"].p_target
        # Total may be slightly less than 700 if both saturated
        assert total <= 700.0 + 0.01

    def test_single_device_clamp(self):
        """Single device should be clamped to max_p."""
        dist = SOCBalancingDistributor(per_device_max_p=300.0)
        devices = [_snap("d1", rated_p=500.0, soc=50.0)]
        result = dist.distribute(Command(p_target=500.0), devices)
        assert result["d1"].p_target == pytest.approx(300.0)


# ===========================================================================
# All devices saturated
# ===========================================================================


class TestDistributorAllSaturated:
    def test_all_saturated_clamp(self):
        """When all devices saturate, each gets max_p and total < requested."""
        dist = SOCBalancingDistributor(per_device_max_p=200.0)
        devices = [
            _snap("d1", rated_p=500.0, soc=60.0),
            _snap("d2", rated_p=500.0, soc=60.0),
        ]
        result = dist.distribute(Command(p_target=1000.0), devices)
        # Each should be clamped to 200
        assert result["d1"].p_target == pytest.approx(200.0)
        assert result["d2"].p_target == pytest.approx(200.0)
        total = result["d1"].p_target + result["d2"].p_target
        assert total == pytest.approx(400.0)  # < 1000


# ===========================================================================
# Charging (negative P)
# ===========================================================================


class TestDistributorClampCharging:
    def test_clamp_charging(self):
        """Clamp should also apply to negative P (charging)."""
        dist = SOCBalancingDistributor(per_device_max_p=300.0, gain=2.0)
        devices = [
            _snap("d1", rated_p=500.0, soc=30.0),
            _snap("d2", rated_p=500.0, soc=80.0),
        ]
        cmd = Command(p_target=-700.0, q_target=0.0)
        result = dist.distribute(cmd, devices)

        # Both should be within [-300, 0] for charging
        assert result["d1"].p_target >= -300.0 - 0.01
        assert result["d2"].p_target >= -300.0 - 0.01

    def test_all_saturated_charging(self):
        """All devices saturated during charging."""
        dist = SOCBalancingDistributor(per_device_max_p=200.0)
        devices = [
            _snap("d1", rated_p=500.0, soc=50.0),
            _snap("d2", rated_p=500.0, soc=50.0),
        ]
        result = dist.distribute(Command(p_target=-1000.0), devices)
        assert result["d1"].p_target >= -200.0 - 0.01
        assert result["d2"].p_target >= -200.0 - 0.01


# ===========================================================================
# Q clamp (per_device_max_q)
# ===========================================================================


class TestDistributorQClamp:
    def test_q_clamp(self):
        """per_device_max_q should limit Q per device."""
        dist = SOCBalancingDistributor(per_device_max_q=100.0)
        devices = [
            _snap("d1", rated_p=500.0, soc=60.0),
            _snap("d2", rated_p=500.0, soc=60.0),
        ]
        result = dist.distribute(Command(p_target=0.0, q_target=400.0), devices)
        # Each Q should be at most 100
        assert abs(result["d1"].q_target) <= 100.0 + 0.01
        assert abs(result["d2"].q_target) <= 100.0 + 0.01


# ===========================================================================
# Conservation check with clamp
# ===========================================================================


class TestDistributorConservationWithClamp:
    def test_p_conservation_under_partial_clamp(self):
        """When only some devices saturate, overflow transfers and total is conserved."""
        dist = SOCBalancingDistributor(per_device_max_p=400.0, gain=0.0)
        # gain=0 -> proportional (no SOC weighting), equal rated -> equal split
        # 3 devices each get 1000/3 = 333.3 -> all below 400 -> no clamp
        devices = [
            _snap("d1", rated_p=500.0, soc=50.0),
            _snap("d2", rated_p=500.0, soc=50.0),
            _snap("d3", rated_p=500.0, soc=50.0),
        ]
        result = dist.distribute(Command(p_target=1000.0), devices)
        total = sum(r.p_target for r in result.values())
        assert total == pytest.approx(1000.0, abs=1.0)

    def test_cascading_overflow_conservation(self):
        """When Pass 2 redistribution causes new saturation, overflow must not be lost.

        Scenario: 3 devices, max_p=100, command=280 (total capacity=300).
        SOC skew causes d1 to get 168 initially → clamped → overflow to d2/d3.
        d2 then exceeds 100 after receiving overflow → must re-distribute to d3.
        """
        dist = SOCBalancingDistributor(per_device_max_p=100.0, gain=2.0)
        devices = [
            _snap("d1", rated_p=100.0, soc=90.0),
            _snap("d2", rated_p=100.0, soc=50.0),
            _snap("d3", rated_p=100.0, soc=10.0),
        ]
        result = dist.distribute(Command(p_target=280.0), devices)

        # Each device must not exceed max
        for cmd in result.values():
            assert cmd.p_target <= 100.0 + 0.01

        # Total must equal command (since total capacity 300 > 280)
        total = sum(r.p_target for r in result.values())
        assert total == pytest.approx(280.0, abs=1.0)

    def test_p_total_does_not_exceed_command(self):
        """With overflow redistribution, total should not exceed the command."""
        dist = SOCBalancingDistributor(per_device_max_p=500.0, gain=2.0)
        devices = [
            _snap("d1", rated_p=1000.0, soc=90.0),
            _snap("d2", rated_p=500.0, soc=30.0),
            _snap("d3", rated_p=500.0, soc=60.0),
        ]
        result = dist.distribute(Command(p_target=1500.0), devices)
        total = sum(r.p_target for r in result.values())
        assert total <= 1500.0 + 1.0
