import math

import pytest

from csp_lib.equipment.core.pipeline import ProcessingPipeline
from csp_lib.equipment.core.transform import (
    BitExtractTransform,
    ClampTransform,
    InverseTransform,
    PowerFactorTransform,
    RoundTransform,
    ScaleTransform,
)


class TestScaleEdgeCases:
    def test_nan_input(self):
        t = ScaleTransform(magnitude=2.0, offset=10.0)
        result = t.apply(float("nan"))
        assert math.isnan(result)

    def test_inf_times_zero_magnitude(self):
        t = ScaleTransform(magnitude=0.0, offset=5.0)
        result = t.apply(float("inf"))
        # inf * 0 = nan
        assert math.isnan(result)

    def test_non_numeric_raises(self):
        t = ScaleTransform()
        with pytest.raises(TypeError):
            t.apply("not_a_number")


class TestClampEdgeCases:
    def test_min_greater_than_max(self):
        """Contradictory clamp: min > max"""
        t = ClampTransform(min_value=100, max_value=0)
        # max(result, 100) then min(result, 0) -> always 0
        result = t.apply(50)
        assert result == 0  # min(max(50, 100), 0) = min(100, 0) = 0

    def test_nan_comparison(self):
        """NaN vs min/max: max(NaN, 0) behaviour is platform-dependent"""
        t = ClampTransform(min_value=0, max_value=100)
        result = t.apply(float("nan"))
        # In CPython, max(nan, 0) returns 0, min(0, 100) returns 0
        # OR max(nan, 0) could return nan depending on argument order
        # We just verify it does not raise
        assert isinstance(result, float)

    def test_none_raises(self):
        t = ClampTransform(min_value=0, max_value=100)
        with pytest.raises(TypeError):
            t.apply(None)


class TestRoundEdgeCases:
    def test_nan(self):
        t = RoundTransform(decimals=2)
        result = t.apply(float("nan"))
        assert math.isnan(result)

    def test_inf(self):
        t = RoundTransform(decimals=2)
        result = t.apply(float("inf"))
        assert math.isinf(result)


class TestInverseEdgeCases:
    def test_nan_input(self):
        t = InverseTransform(magnitude=2.0, offset=10.0)
        result = t.apply(float("nan"))
        assert math.isnan(result)

    def test_magnitude_zero_raises(self):
        t = InverseTransform(magnitude=0.0)
        with pytest.raises(ValueError):
            t.apply(10.0)


class TestBitExtractEdgeCases:
    def test_large_offset_returns_zero(self):
        """Shifting past all bits should return 0"""
        t = BitExtractTransform(bit_offset=64, bit_length=1)
        # For a 16-bit value, shifting by 64 gives 0
        result = t.apply(0xFFFF)
        assert result is False  # bit_length=1 -> bool(0) = False

    def test_negative_offset_raises(self):
        with pytest.raises(ValueError):
            BitExtractTransform(bit_offset=-1)

    def test_zero_bit_length_raises(self):
        with pytest.raises(ValueError):
            BitExtractTransform(bit_offset=0, bit_length=0)


class TestPowerFactorEdgeCases:
    def test_near_unity_positive(self):
        t = PowerFactorTransform()
        result = t.apply(1.0)
        assert result == 1.0

    def test_near_unity_negative(self):
        t = PowerFactorTransform()
        result = t.apply(-1.0)
        assert result == -1.0

    def test_non_numeric_raises(self):
        t = PowerFactorTransform()
        with pytest.raises(TypeError):
            t.apply("not_a_number")


class TestPipelineEdgeCases:
    def test_none_value_raises_typeerror(self):
        pipe = ProcessingPipeline(steps=(ScaleTransform(magnitude=2.0),))
        with pytest.raises(TypeError):
            pipe.process(None)

    def test_exception_in_middle_step(self):
        """Exception in middle step - no partial result"""
        pipe = ProcessingPipeline(
            steps=(
                ScaleTransform(magnitude=1.0),
                InverseTransform(magnitude=0.0),  # will raise ValueError
                RoundTransform(decimals=2),
            )
        )
        with pytest.raises(ValueError):
            pipe.process(10.0)

    def test_empty_pipeline(self):
        pipe = ProcessingPipeline(steps=())
        assert pipe.process(42) == 42
        assert not pipe  # __bool__ returns False for empty
