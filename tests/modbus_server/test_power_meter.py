# =============== Modbus Server Tests - Power Meter ===============
#
# 電表模擬器單元測試

import pytest

from csp_lib.modbus_server.simulator.power_meter import PowerMeterSimulator, default_meter_config


class TestPowerMeterSimulator:
    """PowerMeterSimulator 測試"""

    def test_default_config(self):
        """預設配置正確"""
        sim = PowerMeterSimulator()
        assert sim.device_id == "meter_1"
        assert sim.unit_id == 1
        assert sim.power_sign == 1.0

    def test_initial_values(self):
        """初始值正確"""
        sim = PowerMeterSimulator()
        assert abs(sim.get_value("voltage_a") - 380.0) < 0.01
        assert abs(sim.get_value("frequency") - 60.0) < 0.01
        assert sim.get_value("status") == 1

    def test_set_system_reading(self):
        """MicrogridSimulator 聯動設定"""
        sim = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        sim.set_system_reading(v=380.0, f=60.0, p=100.0, q=50.0)

        assert abs(sim.get_value("active_power") - 100.0) < 0.01
        assert abs(sim.get_value("reactive_power") - 50.0) < 0.01
        # 視在功率 S = sqrt(P² + Q²)
        s = (100.0**2 + 50.0**2) ** 0.5
        assert abs(sim.get_value("apparent_power") - s) < 0.1

    def test_power_sign_negative(self):
        """負功率符號"""
        sim = PowerMeterSimulator(power_sign=-1.0, voltage_noise=0.0, frequency_noise=0.0)
        sim.set_system_reading(v=380.0, f=60.0, p=100.0, q=50.0)

        assert abs(sim.get_value("active_power") - (-100.0)) < 0.01
        assert abs(sim.get_value("reactive_power") - (-50.0)) < 0.01

    def test_accumulate_energy(self):
        """累積電量"""
        sim = PowerMeterSimulator()
        # 100 kW * 3600 seconds = 100 kWh
        sim.accumulate_energy(100.0, 3600.0)
        assert abs(sim.get_value("energy_total") - 100.0) < 0.01

    @pytest.mark.asyncio
    async def test_update_standalone(self):
        """獨立更新（無 MicrogridSimulator）"""
        sim = PowerMeterSimulator()
        await sim.update()
        # 電壓和頻率應該有擾動（不等於精確初始值）
        # 只要不拋錯就好
        assert sim.get_value("voltage_a") is not None
        assert sim.get_value("frequency") is not None

    def test_custom_config(self):
        """自訂配置"""
        config = default_meter_config(
            device_id="custom_meter",
            unit_id=5,
            power_sign=-1.0,
        )
        sim = PowerMeterSimulator(config=config, power_sign=-1.0)
        assert sim.device_id == "custom_meter"
        assert sim.unit_id == 5
