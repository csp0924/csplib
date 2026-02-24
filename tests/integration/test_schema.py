"""Tests for integration schema dataclasses."""

import pytest

from csp_lib.integration.schema import (
    AggregateFunc,
    CommandMapping,
    ContextMapping,
    DataFeedMapping,
)


class TestContextMapping:
    def test_device_id_mode(self):
        m = ContextMapping(point_name="soc", context_field="soc", device_id="dev1")
        assert m.device_id == "dev1"
        assert m.trait is None

    def test_trait_mode(self):
        m = ContextMapping(point_name="soc", context_field="soc", trait="bms")
        assert m.trait == "bms"
        assert m.device_id is None

    def test_both_raises(self):
        with pytest.raises(ValueError, match="Cannot set both"):
            ContextMapping(point_name="soc", context_field="soc", device_id="d1", trait="t1")

    def test_neither_raises(self):
        with pytest.raises(ValueError, match="Must set either"):
            ContextMapping(point_name="soc", context_field="soc")

    def test_frozen(self):
        m = ContextMapping(point_name="soc", context_field="soc", device_id="d1")
        with pytest.raises(AttributeError):
            m.point_name = "other"  # type: ignore[misc]

    def test_defaults(self):
        m = ContextMapping(point_name="soc", context_field="soc", device_id="d1")
        assert m.aggregate == AggregateFunc.AVERAGE
        assert m.custom_aggregate is None
        assert m.default is None
        assert m.transform is None

    def test_custom_aggregate(self):
        fn = lambda vs: sum(vs) / len(vs)  # noqa: E731
        m = ContextMapping(point_name="soc", context_field="soc", trait="bms", custom_aggregate=fn)
        assert m.custom_aggregate is fn

    def test_transform(self):
        fn = lambda v: v * 100  # noqa: E731
        m = ContextMapping(point_name="soc", context_field="soc", device_id="d1", transform=fn)
        assert m.transform is fn


class TestCommandMapping:
    def test_device_id_mode(self):
        m = CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")
        assert m.device_id == "pcs1"

    def test_trait_mode(self):
        m = CommandMapping(command_field="p_target", point_name="p_set", trait="pcs")
        assert m.trait == "pcs"

    def test_both_raises(self):
        with pytest.raises(ValueError, match="Cannot set both"):
            CommandMapping(command_field="p_target", point_name="p_set", device_id="d1", trait="t1")

    def test_neither_raises(self):
        with pytest.raises(ValueError, match="Must set either"):
            CommandMapping(command_field="p_target", point_name="p_set")

    def test_frozen(self):
        m = CommandMapping(command_field="p_target", point_name="p_set", device_id="d1")
        with pytest.raises(AttributeError):
            m.command_field = "other"  # type: ignore[misc]


class TestDataFeedMapping:
    def test_device_id_mode(self):
        m = DataFeedMapping(point_name="pv_power", device_id="meter1")
        assert m.device_id == "meter1"

    def test_trait_mode(self):
        m = DataFeedMapping(point_name="pv_power", trait="meter")
        assert m.trait == "meter"

    def test_both_raises(self):
        with pytest.raises(ValueError, match="Cannot set both"):
            DataFeedMapping(point_name="pv_power", device_id="d1", trait="t1")

    def test_neither_raises(self):
        with pytest.raises(ValueError, match="Must set either"):
            DataFeedMapping(point_name="pv_power")

    def test_frozen(self):
        m = DataFeedMapping(point_name="pv_power", device_id="d1")
        with pytest.raises(AttributeError):
            m.point_name = "other"  # type: ignore[misc]


class TestAggregateFunc:
    def test_values(self):
        assert AggregateFunc.AVERAGE.value == "average"
        assert AggregateFunc.SUM.value == "sum"
        assert AggregateFunc.MIN.value == "min"
        assert AggregateFunc.MAX.value == "max"
        assert AggregateFunc.FIRST.value == "first"

    def test_member_count(self):
        assert len(AggregateFunc) == 5
