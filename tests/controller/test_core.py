# =============== Core Module Tests ===============
#
# 測試 Command, SystemBase, StrategyContext, ExecutionConfig

import dataclasses

import pytest

from csp_lib.controller.core import (
    Command,
    ConfigMixin,
    ExecutionConfig,
    ExecutionMode,
    StrategyContext,
    SystemBase,
)

# =============== Command Tests ===============


class TestCommand:
    """Command 不可變物件測試"""

    def test_default_values(self):
        """預設值應為 (0.0, 0.0)"""
        cmd = Command()
        assert cmd.p_target == 0.0
        assert cmd.q_target == 0.0

    def test_create_with_values(self):
        """可建立帶有指定值的 Command"""
        cmd = Command(p_target=100.0, q_target=50.0)
        assert cmd.p_target == 100.0
        assert cmd.q_target == 50.0

    def test_frozen_immutable(self):
        """Command 應為不可變 (frozen)"""
        cmd = Command(p_target=100.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            cmd.p_target = 200.0

    def test_with_p_creates_new_instance(self):
        """with_p 應建立新實例，不修改原物件"""
        original = Command(p_target=100.0, q_target=50.0)
        new_cmd = original.with_p(200.0)

        assert new_cmd.p_target == 200.0
        assert new_cmd.q_target == 50.0
        assert original.p_target == 100.0  # 原物件不變

    def test_with_q_creates_new_instance(self):
        """with_q 應建立新實例，不修改原物件"""
        original = Command(p_target=100.0, q_target=50.0)
        new_cmd = original.with_q(75.0)

        assert new_cmd.p_target == 100.0
        assert new_cmd.q_target == 75.0
        assert original.q_target == 50.0  # 原物件不變

    def test_str_representation(self):
        """__str__ 應產生易讀格式"""
        cmd = Command(p_target=123.456, q_target=78.9)
        assert "123.5" in str(cmd)
        assert "78.9" in str(cmd)
        assert "kW" in str(cmd)
        assert "kVar" in str(cmd)


# =============== SystemBase Tests ===============


class TestSystemBase:
    """SystemBase 系統基準值測試"""

    def test_default_values(self):
        """預設值應為 (0.0, 0.0)"""
        base = SystemBase()
        assert base.p_base == 0.0
        assert base.q_base == 0.0

    def test_frozen_immutable(self):
        """SystemBase 應為不可變"""
        base = SystemBase(p_base=1000.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            base.p_base = 2000.0


# =============== ConfigMixin Tests ===============


@dataclasses.dataclass
class SampleConfig(ConfigMixin):
    """測試用 Config"""

    ramp_rate: float = 10.0
    max_power: float = 100.0


class TestConfigMixin:
    """ConfigMixin.from_dict 測試"""

    def test_from_dict_basic(self):
        """基本字典轉換"""
        config = SampleConfig.from_dict({"ramp_rate": 20.0, "max_power": 200.0})
        assert config.ramp_rate == 20.0
        assert config.max_power == 200.0

    def test_from_dict_ignores_extra_keys(self):
        """應忽略不存在的 key"""
        config = SampleConfig.from_dict({"ramp_rate": 15.0, "unknown_key": "ignored"})
        assert config.ramp_rate == 15.0
        assert config.max_power == 100.0  # 使用預設值

    def test_from_dict_camel_to_snake(self):
        """支援 camelCase 轉 snake_case"""
        config = SampleConfig.from_dict({"rampRate": 25.0, "maxPower": 300.0})
        assert config.ramp_rate == 25.0
        assert config.max_power == 300.0

    def test_to_dict(self):
        """to_dict 應輸出完整字典"""
        config = SampleConfig(ramp_rate=30.0, max_power=400.0)
        result = config.to_dict()
        assert result == {"ramp_rate": 30.0, "max_power": 400.0}


# =============== StrategyContext Tests ===============


class TestStrategyContext:
    """StrategyContext 策略上下文測試"""

    def test_default_values(self):
        """預設值測試"""
        ctx = StrategyContext()
        assert ctx.last_command == Command()
        assert ctx.soc is None
        assert ctx.system_base is None
        assert ctx.current_time is None
        assert ctx.extra == {}

    def test_percent_to_kw_with_system_base(self):
        """percent_to_kw 應正確轉換"""
        ctx = StrategyContext(system_base=SystemBase(p_base=1000.0, q_base=500.0))
        assert ctx.percent_to_kw(10.0) == 100.0  # 10% of 1000
        assert ctx.percent_to_kw(50.0) == 500.0

    def test_percent_to_kvar_with_system_base(self):
        """percent_to_kvar 應正確轉換"""
        ctx = StrategyContext(system_base=SystemBase(p_base=1000.0, q_base=500.0))
        assert ctx.percent_to_kvar(20.0) == 100.0  # 20% of 500

    def test_percent_to_kw_without_system_base_raises(self):
        """未設定 system_base 時應拋出 ValueError"""
        ctx = StrategyContext()
        with pytest.raises(ValueError, match="system_base is not set"):
            ctx.percent_to_kw(10.0)

    def test_percent_to_kvar_without_system_base_raises(self):
        """未設定 system_base 時應拋出 ValueError"""
        ctx = StrategyContext()
        with pytest.raises(ValueError, match="system_base is not set"):
            ctx.percent_to_kvar(10.0)

    def test_dataclasses_replace(self):
        """應支援 dataclasses.replace()"""
        original = StrategyContext(soc=50.0)
        new_ctx = dataclasses.replace(original, soc=80.0)

        assert new_ctx.soc == 80.0
        assert original.soc == 50.0  # 原物件不變


# =============== ExecutionConfig Tests ===============


class TestExecutionConfig:
    """ExecutionConfig 執行配置測試"""

    def test_default_interval(self):
        """預設 interval 應為 1"""
        config = ExecutionConfig(mode=ExecutionMode.PERIODIC)
        assert config.interval_seconds == 1

    def test_frozen_immutable(self):
        """ExecutionConfig 應為不可變"""
        config = ExecutionConfig(mode=ExecutionMode.PERIODIC)
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.interval_seconds = 10

    def test_periodic_requires_positive_interval(self):
        """PERIODIC 模式需要正數 interval"""
        with pytest.raises(ValueError, match="must be positive"):
            ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=0)

    def test_hybrid_requires_positive_interval(self):
        """HYBRID 模式需要正數 interval"""
        with pytest.raises(ValueError, match="must be positive"):
            ExecutionConfig(mode=ExecutionMode.HYBRID, interval_seconds=-1)

    def test_triggered_allows_any_interval(self):
        """TRIGGERED 模式可接受任意 interval (因為不使用)"""
        config = ExecutionConfig(mode=ExecutionMode.TRIGGERED, interval_seconds=0)
        assert config.interval_seconds == 0
