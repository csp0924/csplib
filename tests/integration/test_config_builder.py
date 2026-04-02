"""Tests for SystemControllerConfigBuilder — fluent API and build behavior."""

from unittest.mock import MagicMock

import pytest

from csp_lib.controller.core import CommandProcessor
from csp_lib.controller.system import ProtectionRule
from csp_lib.integration.schema import HeartbeatMode
from csp_lib.integration.system_controller import SystemControllerConfig, SystemControllerConfigBuilder


class TestBuilderFluentChain:
    """Builder methods should return self, enabling method chaining."""

    def test_all_methods_return_builder(self):
        builder = SystemControllerConfig.builder()
        # Each call should return the same builder instance
        result = builder.system_base(p_base=2000)
        assert result is builder

        result = builder.map_context(point_name="soc", target="soc", device_id="BMS1")
        assert result is builder

        result = builder.map_command(field="p_target", point_name="set_p", device_id="PCS1")
        assert result is builder

        mock_rule = MagicMock(spec=ProtectionRule)
        result = builder.protect(mock_rule)
        assert result is builder

        result = builder.auto_stop(enabled=True)
        assert result is builder

        mock_proc = MagicMock(spec=CommandProcessor)
        result = builder.processor(mock_proc)
        assert result is builder

        result = builder.params(MagicMock())
        assert result is builder

        result = builder.heartbeat(interval=2.0)
        assert result is builder

        result = builder.alarm_mode_per_device()
        assert result is builder

        result = builder.cascading(capacity_kva=500.0)
        assert result is builder

    def test_full_chain_produces_config(self):
        """A realistic fluent chain should build successfully."""
        config = (
            SystemControllerConfig.builder()
            .system_base(p_base=2000, q_base=100)
            .map_context(point_name="soc", target="soc", device_id="BMS1")
            .map_context(point_name="freq", target="extra.frequency", trait="meter")
            .map_command(field="p_target", point_name="set_p", device_id="PCS1")
            .auto_stop(enabled=True, alarm_key="system_alarm")
            .build()
        )
        assert isinstance(config, SystemControllerConfig)
        assert config.system_base is not None
        assert config.system_base.p_base == 2000
        assert len(config.context_mappings) == 2
        assert len(config.command_mappings) == 1


class TestBuilderMutualExclusion:
    """Context/Command mappings require exactly one of device_id or trait."""

    def test_map_context_both_device_and_trait_raises(self):
        """Providing both device_id and trait should raise ValueError."""
        builder = SystemControllerConfig.builder()
        with pytest.raises(ValueError, match="Cannot set both"):
            builder.map_context(point_name="soc", target="soc", device_id="BMS1", trait="bms")

    def test_map_context_neither_device_nor_trait_raises(self):
        """Providing neither device_id nor trait should raise ValueError."""
        builder = SystemControllerConfig.builder()
        with pytest.raises(ValueError, match="Must set either"):
            builder.map_context(point_name="soc", target="soc")

    def test_map_command_both_device_and_trait_raises(self):
        builder = SystemControllerConfig.builder()
        with pytest.raises(ValueError, match="Cannot set both"):
            builder.map_command(field="p_target", point_name="set_p", device_id="PCS1", trait="pcs")

    def test_map_command_neither_device_nor_trait_raises(self):
        builder = SystemControllerConfig.builder()
        with pytest.raises(ValueError, match="Must set either"):
            builder.map_command(field="p_target", point_name="set_p")


class TestBuilderMissingFields:
    """Build with no mappings should still succeed — all fields have defaults."""

    def test_empty_builder_produces_valid_config(self):
        """Builder with no configuration still produces a valid config with defaults."""
        config = SystemControllerConfig.builder().build()
        assert isinstance(config, SystemControllerConfig)
        assert config.context_mappings == []
        assert config.command_mappings == []
        assert config.system_base is None
        assert config.auto_stop_on_alarm is True
        assert config.alarm_mode == "system_wide"
        assert config.pv_max_history == 300

    def test_builder_preserves_protection_rules(self):
        """Protection rules added via .protect() should appear in built config."""
        rule1 = MagicMock(spec=ProtectionRule)
        rule2 = MagicMock(spec=ProtectionRule)
        config = SystemControllerConfig.builder().protect(rule1).protect(rule2).build()
        assert len(config.protection_rules) == 2
        assert config.protection_rules[0] is rule1
        assert config.protection_rules[1] is rule2


class TestBuilderCompleteBuild:
    """Full configuration build with multiple features."""

    def test_complete_build_with_all_options(self):
        mock_proc = MagicMock(spec=CommandProcessor)
        mock_rule = MagicMock(spec=ProtectionRule)
        mock_params = MagicMock()

        config = (
            SystemControllerConfig.builder()
            .system_base(p_base=3000, q_base=500)
            .map_context(point_name="soc", target="soc", device_id="BMS1")
            .map_command(field="p_target", point_name="set_p", trait="pcs")
            .protect(mock_rule)
            .auto_stop(enabled=False, alarm_key="custom_alarm")
            .processor(mock_proc)
            .params(mock_params)
            .heartbeat(interval=2.0, use_capability=True, mode=HeartbeatMode.INCREMENT)
            .alarm_mode_per_device()
            .cascading(capacity_kva=750.0)
            .build()
        )

        # System base
        assert config.system_base is not None
        assert config.system_base.p_base == 3000
        assert config.system_base.q_base == 500

        # Mappings
        assert len(config.context_mappings) == 1
        assert config.context_mappings[0].context_field == "soc"
        assert len(config.command_mappings) == 1
        assert config.command_mappings[0].command_field == "p_target"

        # Protection & auto-stop
        assert len(config.protection_rules) == 1
        assert config.auto_stop_on_alarm is False
        assert config.system_alarm_key == "custom_alarm"

        # Processor & params
        assert len(config.post_protection_processors) == 1
        assert config.post_protection_processors[0] is mock_proc
        assert config.runtime_params is mock_params

        # Heartbeat
        assert config.heartbeat_interval == 2.0
        assert config.use_heartbeat_capability is True
        assert config.heartbeat_capability_mode == HeartbeatMode.INCREMENT

        # Alarm mode & cascading
        assert config.alarm_mode == "per_device"
        assert config.capacity_kva == 750.0

    def test_builder_classmethod_returns_builder(self):
        """SystemControllerConfig.builder() should return a new builder."""
        builder = SystemControllerConfig.builder()
        assert isinstance(builder, SystemControllerConfigBuilder)

    def test_multiple_builds_are_independent(self):
        """Building twice from the same builder should produce equal but separate configs."""
        builder = (
            SystemControllerConfig.builder()
            .system_base(p_base=1000)
            .map_context(point_name="soc", target="soc", device_id="BMS1")
        )
        config1 = builder.build()
        config2 = builder.build()
        assert config1 is not config2
        assert config1.system_base.p_base == config2.system_base.p_base
        assert len(config1.context_mappings) == len(config2.context_mappings)
