# =============== Equipment Simulation Tests ===============
#
# simulation 模組單元測試

from dataclasses import FrozenInstanceError
from typing import Iterator

import pytest

from csp_lib.equipment.simulation import (
    DEFAULT_REGISTRY,
    CurvePoint,
    CurveProvider,
    CurveRegistry,
    CurveType,
    MeterMode,
    MeterReading,
    VirtualMeter,
    curve_fp_step,
    curve_qv_step,
)

# ================ CurvePoint Tests ================


class TestCurvePoint:
    """CurvePoint 測試"""

    def test_creation(self):
        point = CurvePoint(value=60.0, duration=3.0, curve_type=CurveType.FREQUENCY)
        assert point.value == 60.0
        assert point.duration == 3.0
        assert point.curve_type == CurveType.FREQUENCY

    def test_immutable(self):
        point = CurvePoint(value=60.0, duration=3.0, curve_type=CurveType.FREQUENCY)
        with pytest.raises(FrozenInstanceError):
            point.value = 59.0

    def test_voltage_type(self):
        point = CurvePoint(value=380.0, duration=5.0, curve_type=CurveType.VOLTAGE)
        assert point.curve_type == CurveType.VOLTAGE


# ================ CurveRegistry Tests ================


class TestCurveRegistry:
    """CurveRegistry 測試"""

    def test_register_and_get(self):
        registry = CurveRegistry()

        def my_curve() -> Iterator[CurvePoint]:
            yield CurvePoint(value=60.0, duration=1.0, curve_type=CurveType.FREQUENCY)

        registry.register("test", my_curve)
        curve = registry.get_curve("test")
        assert curve is not None
        point = next(curve)
        assert point.value == 60.0

    def test_get_nonexistent(self):
        registry = CurveRegistry()
        assert registry.get_curve("nonexistent") is None

    def test_list_curves(self):
        registry = CurveRegistry()

        def curve1() -> Iterator[CurvePoint]:
            yield CurvePoint(value=60.0, duration=1.0, curve_type=CurveType.FREQUENCY)

        def curve2() -> Iterator[CurvePoint]:
            yield CurvePoint(value=380.0, duration=1.0, curve_type=CurveType.VOLTAGE)

        registry.register("curve1", curve1)
        registry.register("curve2", curve2)

        curves = registry.list_curves()
        assert "curve1" in curves
        assert "curve2" in curves
        assert len(curves) == 2

    def test_unregister(self):
        registry = CurveRegistry()

        def my_curve() -> Iterator[CurvePoint]:
            yield CurvePoint(value=60.0, duration=1.0, curve_type=CurveType.FREQUENCY)

        registry.register("test", my_curve)
        assert "test" in registry

        result = registry.unregister("test")
        assert result is True
        assert "test" not in registry

    def test_unregister_nonexistent(self):
        registry = CurveRegistry()
        result = registry.unregister("nonexistent")
        assert result is False

    def test_contains(self):
        registry = CurveRegistry()

        def my_curve() -> Iterator[CurvePoint]:
            yield CurvePoint(value=60.0, duration=1.0, curve_type=CurveType.FREQUENCY)

        registry.register("test", my_curve)
        assert "test" in registry
        assert "other" not in registry

    def test_len(self):
        registry = CurveRegistry()
        assert len(registry) == 0

        def my_curve() -> Iterator[CurvePoint]:
            yield CurvePoint(value=60.0, duration=1.0, curve_type=CurveType.FREQUENCY)

        registry.register("test", my_curve)
        assert len(registry) == 1

    def test_satisfies_protocol(self):
        """CurveRegistry 滿足 CurveProvider Protocol"""
        registry = CurveRegistry()
        assert isinstance(registry, CurveProvider)


# ================ Built-in Curves Tests ================


class TestBuiltinCurves:
    """內建曲線測試"""

    def test_fp_step_curve(self):
        points = list(curve_fp_step())
        assert len(points) == 18
        assert all(p.curve_type == CurveType.FREQUENCY for p in points)
        assert all(p.duration == 3.0 for p in points)

    def test_qv_step_curve(self):
        points = list(curve_qv_step())
        assert len(points) == 9
        assert all(p.curve_type == CurveType.VOLTAGE for p in points)
        assert all(p.duration == 3.0 for p in points)

    def test_default_registry_contains_builtin(self):
        assert "fp_step" in DEFAULT_REGISTRY
        assert "qv_step" in DEFAULT_REGISTRY


# ================ MeterReading Tests ================


class TestMeterReading:
    """MeterReading 測試"""

    def test_default_values(self):
        reading = MeterReading()
        assert reading.v == 380.0
        assert reading.f == 60.0
        assert reading.p == 0.0
        assert reading.q == 0.0
        assert reading.s == 0.0
        assert reading.pf == 1.0

    def test_custom_values(self):
        reading = MeterReading(v=400.0, f=59.5, p=100.0, q=50.0, s=111.8, pf=0.89)
        assert reading.v == 400.0
        assert reading.f == 59.5
        assert reading.p == 100.0

    def test_immutable(self):
        reading = MeterReading()
        with pytest.raises(FrozenInstanceError):
            reading.v = 400.0

    def test_with_power_factory(self):
        reading = MeterReading.with_power(v=380.0, f=60.0, p=100.0, q=50.0)
        assert reading.v == 380.0
        assert reading.f == 60.0
        assert reading.p == 100.0
        assert reading.q == 50.0
        assert reading.s == pytest.approx(111.803, rel=0.01)
        assert reading.pf == pytest.approx(0.894, rel=0.01)

    def test_with_power_zero(self):
        reading = MeterReading.with_power(v=380.0, f=60.0, p=0.0, q=0.0)
        assert reading.s == 0.0
        assert reading.pf == 1.0


# ================ VirtualMeter Tests ================


class TestVirtualMeter:
    """VirtualMeter 測試"""

    def test_default_init(self):
        meter = VirtualMeter()
        assert meter.mode == MeterMode.RANDOM
        assert meter.get_voltage() == 380.0
        assert meter.get_frequency() == 60.0

    def test_custom_base_values(self):
        meter = VirtualMeter(base_voltage=400.0, base_frequency=50.0)
        assert meter.get_voltage() == 400.0
        assert meter.get_frequency() == 50.0

    def test_reading_property(self):
        meter = VirtualMeter()
        reading = meter.reading
        assert isinstance(reading, MeterReading)

    def test_list_available_curves(self):
        meter = VirtualMeter()
        curves = meter.list_available_curves()
        assert "fp_step" in curves
        assert "qv_step" in curves

    def test_start_test_curve_success(self):
        meter = VirtualMeter()
        result = meter.start_test_curve("fp_step")
        assert result is True
        assert meter.mode == MeterMode.TEST_CURVE

    def test_start_test_curve_unknown(self):
        meter = VirtualMeter()
        result = meter.start_test_curve("nonexistent")
        assert result is False
        assert meter.mode == MeterMode.RANDOM

    def test_stop_test_curve(self):
        meter = VirtualMeter()
        meter.start_test_curve("fp_step")
        meter.stop_test_curve()
        assert meter.mode == MeterMode.RANDOM

    def test_custom_curve_provider(self):
        registry = CurveRegistry()

        def custom_curve() -> Iterator[CurvePoint]:
            yield CurvePoint(value=99.9, duration=1.0, curve_type=CurveType.FREQUENCY)

        registry.register("custom", custom_curve)

        meter = VirtualMeter(curve_provider=registry)
        curves = meter.list_available_curves()
        assert "custom" in curves
        assert "fp_step" not in curves  # 只有自定義曲線

    def test_str_repr(self):
        meter = VirtualMeter()
        text = str(meter)
        assert "VirtualMeter" in text
        assert "random" in text


class TestVirtualMeterAsync:
    """VirtualMeter 非同步測試"""

    @pytest.mark.asyncio
    async def test_update_random_mode(self):
        meter = VirtualMeter(voltage_noise=1.0, frequency_noise=0.01)

        await meter.update()

        # 更新後值應該有變化（可能相同，但通常會不同）
        assert meter.mode == MeterMode.RANDOM

    @pytest.mark.asyncio
    async def test_update_test_curve_mode(self):
        meter = VirtualMeter()
        meter.start_test_curve("fp_step")

        await meter.update()

        assert meter.mode == MeterMode.TEST_CURVE
        # 頻率應該是曲線的第一個點 (60.01)
        assert meter.get_frequency() == pytest.approx(60.01, rel=0.001)
