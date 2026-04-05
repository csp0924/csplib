# =============== Modbus Server Tests - PowerMeter Linked Power ===============
#
# v0.6.2 新增的 linked power 方法測試

import math

from csp_lib.modbus_server.simulator.power_meter import PowerMeterSimulator


class TestResetLinkedPower:
    """reset_linked_power() 測試"""

    def test_zeroes_accumulators(self):
        """重置後累加器歸零"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        sim.add_linked_power(100.0, 50.0)
        sim.reset_linked_power()
        # finalize 後 P/Q 應為 0
        sim.finalize_linked_reading(380.0, 60.0)
        assert abs(sim.get_value("active_power")) < 0.01
        assert abs(sim.get_value("reactive_power")) < 0.01

    def test_reset_idempotent(self):
        """連續重置不影響結果"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        sim.reset_linked_power()
        sim.reset_linked_power()
        sim.finalize_linked_reading(380.0, 60.0)
        assert abs(sim.get_value("active_power")) < 0.01


class TestAddLinkedPower:
    """add_linked_power() 測試"""

    def test_single_add(self):
        """單次累加"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        sim.reset_linked_power()
        sim.add_linked_power(100.0, 50.0)
        sim.finalize_linked_reading(380.0, 60.0)
        assert abs(sim.get_value("active_power") - 100.0) < 0.01
        assert abs(sim.get_value("reactive_power") - 50.0) < 0.01

    def test_multiple_adds_accumulate(self):
        """多次累加正確加總"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        sim.reset_linked_power()
        sim.add_linked_power(100.0, 30.0)
        sim.add_linked_power(50.0, 20.0)
        sim.add_linked_power(-30.0, -10.0)
        sim.finalize_linked_reading(380.0, 60.0)
        # 100+50-30 = 120, 30+20-10 = 40
        assert abs(sim.get_value("active_power") - 120.0) < 0.01
        assert abs(sim.get_value("reactive_power") - 40.0) < 0.01

    def test_negative_power(self):
        """負功率正確累加"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        sim.reset_linked_power()
        sim.add_linked_power(-200.0, -100.0)
        sim.finalize_linked_reading(380.0, 60.0)
        assert abs(sim.get_value("active_power") - (-200.0)) < 0.01
        assert abs(sim.get_value("reactive_power") - (-100.0)) < 0.01


class TestFinalizeLinkedReading:
    """finalize_linked_reading() 測試"""

    def test_calls_set_system_reading(self):
        """finalize 後電壓/頻率/功率皆正確"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        sim.reset_linked_power()
        sim.add_linked_power(100.0, 50.0)
        sim.finalize_linked_reading(400.0, 59.5)

        assert abs(sim.get_value("active_power") - 100.0) < 0.01
        assert abs(sim.get_value("reactive_power") - 50.0) < 0.01
        # 電壓應為 400.0（無 noise）
        assert abs(sim.get_value("voltage_a") - 400.0) < 0.01
        # 頻率應為 59.5（無 noise）
        assert abs(sim.get_value("frequency") - 59.5) < 0.01

    def test_apparent_power_calculated(self):
        """finalize 後正確計算視在功率"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        sim.reset_linked_power()
        sim.add_linked_power(300.0, 400.0)
        sim.finalize_linked_reading(380.0, 60.0)

        expected_s = math.sqrt(300.0**2 + 400.0**2)  # 500.0
        assert abs(sim.get_value("apparent_power") - expected_s) < 0.1


class TestSetPartialReading:
    """set_partial_reading() 測試"""

    def test_updates_pq_without_changing_vf(self):
        """更新 P/Q 但不改變 V/F"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        # 先設定 V/F
        sim.set_system_reading(v=380.0, f=60.0, p=0.0, q=0.0)

        # 透過 partial 只更新 P/Q
        sim.set_partial_reading(200.0, 100.0)

        assert abs(sim.get_value("active_power") - 200.0) < 0.01
        assert abs(sim.get_value("reactive_power") - 100.0) < 0.01
        # V/F 保持不變
        assert abs(sim.get_value("voltage_a") - 380.0) < 0.01
        assert abs(sim.get_value("frequency") - 60.0) < 0.01

    def test_calculates_apparent_power(self):
        """正確計算視在功率"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        sim.set_system_reading(v=380.0, f=60.0, p=0.0, q=0.0)
        sim.set_partial_reading(300.0, 400.0)

        expected_s = math.sqrt(300.0**2 + 400.0**2)  # 500.0
        assert abs(sim.get_value("apparent_power") - expected_s) < 0.1

    def test_calculates_power_factor(self):
        """正確計算功率因數"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        sim.set_system_reading(v=380.0, f=60.0, p=0.0, q=0.0)
        sim.set_partial_reading(300.0, 400.0)

        expected_s = math.sqrt(300.0**2 + 400.0**2)  # 500
        expected_pf = 300.0 / expected_s  # 0.6
        assert abs(sim.get_value("power_factor") - expected_pf) < 0.01

    def test_zero_power_pf_is_one(self):
        """零功率時功率因數為 1.0"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        sim.set_system_reading(v=380.0, f=60.0, p=0.0, q=0.0)
        sim.set_partial_reading(0.0, 0.0)
        assert abs(sim.get_value("power_factor") - 1.0) < 0.01

    def test_with_power_sign_negative(self):
        """負功率符號正確套用"""
        sim = PowerMeterSimulator(power_sign=-1.0, voltage_noise=0.0, frequency_noise=0.0)
        sim.set_system_reading(v=380.0, f=60.0, p=0.0, q=0.0)
        sim.set_partial_reading(100.0, 50.0)

        assert abs(sim.get_value("active_power") - (-100.0)) < 0.01
        assert abs(sim.get_value("reactive_power") - (-50.0)) < 0.01
