# =============== Modbus Server Tests - Behaviors ===============
#
# 行為模組單元測試

import pytest

from csp_lib.modbus_server.behaviors.alarm import AlarmBehavior
from csp_lib.modbus_server.behaviors.noise import NoiseBehavior, NoiseType
from csp_lib.modbus_server.behaviors.ramp import RampBehavior
from csp_lib.modbus_server.config import AlarmResetMode


class TestAlarmBehaviorAutoReset:
    """AUTO reset 告警測試"""

    def setup_method(self):
        self.alarm = AlarmBehavior("OVER_TEMP", bit_position=0, reset_mode=AlarmResetMode.AUTO)

    def test_initial_state(self):
        assert not self.alarm.is_active

    def test_trigger(self):
        self.alarm.update(trigger_condition=True)
        assert self.alarm.is_active

    def test_auto_clear(self):
        """條件消失自動清除"""
        self.alarm.update(trigger_condition=True)
        assert self.alarm.is_active

        self.alarm.update(trigger_condition=False)
        assert not self.alarm.is_active

    def test_manual_reset_ignored(self):
        """AUTO 模式下 manual_reset 無效"""
        self.alarm.update(trigger_condition=True)
        assert not self.alarm.manual_reset()
        assert self.alarm.is_active


class TestAlarmBehaviorManualReset:
    """MANUAL reset 告警測試"""

    def setup_method(self):
        self.alarm = AlarmBehavior("DC_OV", bit_position=1, reset_mode=AlarmResetMode.MANUAL)

    def test_stays_active_after_condition_clears(self):
        """條件消失後仍保持 active"""
        self.alarm.update(trigger_condition=True)
        self.alarm.update(trigger_condition=False)
        assert self.alarm.is_active

    def test_manual_reset_clears(self):
        """手動 reset 清除"""
        self.alarm.update(trigger_condition=True)
        assert self.alarm.manual_reset()
        assert not self.alarm.is_active

    def test_force_reset_ignored(self):
        """MANUAL 模式下 force_reset 無效"""
        self.alarm.update(trigger_condition=True)
        assert not self.alarm.force_reset()


class TestAlarmBehaviorLatchedReset:
    """LATCHED reset 告警測試"""

    def setup_method(self):
        self.alarm = AlarmBehavior("CRITICAL", bit_position=2, reset_mode=AlarmResetMode.LATCHED)

    def test_stays_active(self):
        """條件消失後仍保持 active"""
        self.alarm.update(trigger_condition=True)
        self.alarm.update(trigger_condition=False)
        assert self.alarm.is_active

    def test_manual_reset_ineffective(self):
        """manual_reset 對 LATCHED 無效"""
        self.alarm.update(trigger_condition=True)
        assert not self.alarm.manual_reset()

    def test_force_reset_clears(self):
        """force_reset 清除"""
        self.alarm.update(trigger_condition=True)
        assert self.alarm.force_reset()
        assert not self.alarm.is_active

    def test_reset_method(self):
        """reset() 完全重置"""
        self.alarm.update(trigger_condition=True)
        self.alarm.reset()
        assert not self.alarm.is_active


class TestNoiseBehavior:
    """NoiseBehavior 測試"""

    def test_uniform_noise_range(self):
        noise = NoiseBehavior(base_value=100.0, amplitude=5.0, noise_type=NoiseType.UNIFORM)
        values = [noise.update() for _ in range(100)]
        assert all(95.0 <= v <= 105.0 for v in values)

    def test_zero_amplitude(self):
        noise = NoiseBehavior(base_value=42.0, amplitude=0.0)
        assert noise.update() == 42.0

    def test_gaussian_noise(self):
        noise = NoiseBehavior(base_value=100.0, amplitude=1.0, noise_type=NoiseType.GAUSSIAN)
        values = [noise.update() for _ in range(1000)]
        mean = sum(values) / len(values)
        # Gaussian: mean 應該接近 base_value
        assert abs(mean - 100.0) < 1.0

    def test_base_value_setter(self):
        noise = NoiseBehavior(base_value=0.0, amplitude=0.0)
        noise.base_value = 50.0
        assert noise.base_value == 50.0
        assert noise.update() == 50.0

    def test_reset(self):
        noise = NoiseBehavior(base_value=100.0, amplitude=10.0)
        noise.update()
        noise.reset()
        assert noise.current_value == 100.0


class TestRampBehavior:
    """RampBehavior 測試"""

    def test_ramp_up(self):
        ramp = RampBehavior(ramp_rate=10.0, initial_value=0.0)
        ramp.target = 50.0

        # dt=1s, rate=10/s → 每步 +10
        v = ramp.update(dt=1.0)
        assert abs(v - 10.0) < 0.01

    def test_ramp_down(self):
        ramp = RampBehavior(ramp_rate=10.0, initial_value=100.0)
        ramp.target = 50.0

        v = ramp.update(dt=1.0)
        assert abs(v - 90.0) < 0.01

    def test_reaches_target_exactly(self):
        """到達目標值時停在目標"""
        ramp = RampBehavior(ramp_rate=100.0, initial_value=0.0)
        ramp.target = 5.0

        v = ramp.update(dt=1.0)
        assert abs(v - 5.0) < 0.01
        assert ramp.at_target

    def test_stays_at_target(self):
        """已在目標值不再變化"""
        ramp = RampBehavior(ramp_rate=10.0, initial_value=50.0)
        ramp.target = 50.0

        v = ramp.update(dt=1.0)
        assert abs(v - 50.0) < 0.01

    def test_fractional_dt(self):
        """小時間步長"""
        ramp = RampBehavior(ramp_rate=100.0, initial_value=0.0)
        ramp.target = 100.0

        v = ramp.update(dt=0.1)
        assert abs(v - 10.0) < 0.01

    def test_reset(self):
        ramp = RampBehavior(ramp_rate=10.0, initial_value=50.0)
        ramp.target = 100.0
        ramp.update(dt=1.0)

        ramp.reset(0.0)
        assert ramp.current_value == 0.0
        assert ramp.target == 0.0
