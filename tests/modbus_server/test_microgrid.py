# =============== Modbus Server Tests - Microgrid ===============
#
# MicrogridSimulator 聯動測試

import pytest

from csp_lib.modbus_server.config import ControllabilityMode, MicrogridConfig
from csp_lib.modbus_server.microgrid import MicrogridSimulator
from csp_lib.modbus_server.simulator.generator import GeneratorSimulator
from csp_lib.modbus_server.simulator.load import LoadSimulator
from csp_lib.modbus_server.simulator.pcs import PCSSimulator
from csp_lib.modbus_server.simulator.power_meter import PowerMeterSimulator
from csp_lib.modbus_server.simulator.solar import SolarSimulator


class TestMicrogridSetup:
    """MicrogridSimulator 設置測試"""

    def test_empty_microgrid(self):
        mg = MicrogridSimulator()
        assert mg.meter is None
        assert mg.all_simulators == []

    def test_register_devices(self):
        mg = MicrogridSimulator()
        meter = PowerMeterSimulator()
        pcs = PCSSimulator()
        solar = SolarSimulator()
        load = LoadSimulator()
        gen = GeneratorSimulator()

        mg.set_meter(meter)
        mg.add_pcs(pcs)
        mg.add_solar(solar)
        mg.add_load(load)
        mg.add_generator(gen)

        assert mg.meter is meter
        assert len(mg.all_simulators) == 5


class TestMicrogridPowerBalance:
    """功率平衡測試"""

    @pytest.mark.asyncio
    async def test_load_only(self):
        """只有負載 → 電表顯示正功率（從電網取電）"""
        mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

        meter = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=100.0,
            load_noise=0.0,
        )

        mg.set_meter(meter)
        mg.add_load(load)

        await mg.update(tick_interval=1.0)

        # 負載 100 kW，無發電 → 電表 = +100 kW
        meter_p = meter.get_value("active_power")
        assert abs(meter_p - 100.0) < 1.0

    @pytest.mark.asyncio
    async def test_solar_offsets_load(self):
        """太陽能抵消部分負載"""
        mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

        meter = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=100.0,
            load_noise=0.0,
        )
        solar = SolarSimulator(power_noise=0.0, efficiency=1.0)
        solar.set_target_power(60.0)

        mg.set_meter(meter)
        mg.add_load(load)
        mg.add_solar(solar)

        await mg.update(tick_interval=1.0)

        # 負載 100 - 太陽能 60 = 電網 40 kW
        meter_p = meter.get_value("active_power")
        assert abs(meter_p - 40.0) < 1.0

    @pytest.mark.asyncio
    async def test_pcs_discharge_offsets_load(self):
        """PCS 放電抵消負載"""
        mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

        meter = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=100.0,
            load_noise=0.0,
        )
        pcs = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0)
        pcs.on_write("start_cmd", 0, 1)
        pcs.on_write("p_setpoint", 0.0, 40.0)

        mg.set_meter(meter)
        mg.add_load(load)
        mg.add_pcs(pcs)

        await mg.update(tick_interval=1.0)

        # 負載 100 - PCS 40 = 電網 60 kW
        meter_p = meter.get_value("active_power")
        assert abs(meter_p - 60.0) < 1.0

    @pytest.mark.asyncio
    async def test_excess_solar_exports(self):
        """太陽能超過負載 → 電表顯示負功率（輸出到電網）"""
        mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

        meter = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=50.0,
            load_noise=0.0,
        )
        solar = SolarSimulator(power_noise=0.0, efficiency=1.0)
        solar.set_target_power(100.0)

        mg.set_meter(meter)
        mg.add_load(load)
        mg.add_solar(solar)

        await mg.update(tick_interval=1.0)

        # 負載 50 - 太陽能 100 = 電網 -50 kW
        meter_p = meter.get_value("active_power")
        assert meter_p < 0
        assert abs(meter_p - (-50.0)) < 1.0


class TestMicrogridSOCTracking:
    """SOC 追蹤測試"""

    @pytest.mark.asyncio
    async def test_pcs_soc_updated(self):
        """MicrogridSimulator 更新 PCS SOC"""
        mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

        pcs = PCSSimulator(capacity_kwh=100.0, p_ramp_rate=10000.0, tick_interval=1.0)
        pcs.on_write("start_cmd", 0, 1)
        pcs.on_write("p_setpoint", 0.0, 100.0)  # 100 kW discharge

        mg.add_pcs(pcs)

        initial_soc = pcs.get_value("soc")
        await mg.update(tick_interval=1.0)
        new_soc = pcs.get_value("soc")

        # 放電 → SOC 應該減少
        assert new_soc < initial_soc


class TestMicrogridEnergyAccumulation:
    """能量累積測試"""

    @pytest.mark.asyncio
    async def test_energy_accumulates(self):
        """電表能量累積"""
        mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

        meter = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=100.0,
            load_noise=0.0,
        )

        mg.set_meter(meter)
        mg.add_load(load)

        # 100 kW * 3600s = 100 kWh
        await mg.update(tick_interval=3600.0)
        energy = meter.get_value("energy_total")
        assert abs(energy - 100.0) < 1.0

    @pytest.mark.asyncio
    async def test_accumulated_energy_property(self):
        """MicrogridSimulator 累積電量屬性"""
        mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=36.0,
            load_noise=0.0,
        )
        mg.add_load(load)

        # 36 kW * 100s / 3600 = 1 kWh
        await mg.update(tick_interval=100.0)
        assert abs(mg.accumulated_energy - 1.0) < 0.1


class TestMicrogridVoltageFrequency:
    """電壓/頻率聯動測試"""

    @pytest.mark.asyncio
    async def test_system_vf_propagated(self):
        """系統 V/F 傳播到各設備"""
        mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

        load = LoadSimulator(load_noise=0.0)
        pcs = PCSSimulator()

        mg.add_load(load)
        mg.add_pcs(pcs)

        await mg.update(tick_interval=1.0)

        # 無擾動時應該等於標稱值
        assert abs(load.get_value("voltage") - 380.0) < 0.01
        assert abs(pcs.get_value("voltage") - 380.0) < 0.01
