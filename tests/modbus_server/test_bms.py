# =============== Modbus Server Tests - BMS ===============
#
# BMS 模擬器單元測試

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.modbus_server.config import BMSSimConfig, MicrogridConfig
from csp_lib.modbus_server.microgrid import MicrogridSimulator
from csp_lib.modbus_server.simulator.bms import BMSSimulator, default_bms_config
from csp_lib.modbus_server.simulator.pcs import PCSSimulator


class TestBMSSimulatorBasic:
    """BMS 基本操作測試"""

    def test_default_config(self):
        """預設配置：device_id=bms_1, unit_id=20"""
        sim = BMSSimulator()
        assert sim.device_id == "bms_1"
        assert sim.unit_id == 20

    def test_initial_soc(self):
        """初始 SOC 等於 initial_soc 配置值"""
        sim = BMSSimulator(initial_soc=75.0)
        soc = sim.get_value("soc")
        assert abs(soc - 75.0) < 0.01

    def test_initial_voltage(self):
        """初始電壓基於 SOC 線性插值"""
        # SOC=50%, cells=192, min=2.8, max=4.2
        # v_min=192*2.8=537.6, v_max=192*4.2=806.4
        # pack = 537.6 + (806.4 - 537.6) * 50 / 100 = 672.0
        sim = BMSSimulator(initial_soc=50.0)
        voltage = sim.get_value("voltage")
        expected = 192 * 2.8 + (192 * 4.2 - 192 * 2.8) * 50.0 / 100.0
        assert abs(voltage - expected) < 0.1

    def test_initial_temperature(self):
        """初始溫度為 25°C（預設）"""
        sim = BMSSimulator()
        temp = sim.get_value("temperature")
        assert abs(temp - 25.0) < 0.01

    def test_custom_config(self):
        """自訂 BMSSimConfig"""
        cfg = BMSSimConfig(
            capacity_kwh=200.0,
            initial_soc=80.0,
            nominal_voltage=800.0,
            cells_in_series=200,
            min_cell_voltage=3.0,
            max_cell_voltage=4.0,
            charge_efficiency=0.90,
        )
        dev_cfg = default_bms_config(device_id="bms_custom", unit_id=21)
        sim = BMSSimulator(config=dev_cfg, sim_config=cfg)
        assert sim.device_id == "bms_custom"
        assert sim.unit_id == 21
        assert sim.capacity_kwh == 200.0
        assert abs(sim.get_value("soc") - 80.0) < 0.01


class TestBMSConfigValidation:
    """BMSSimConfig 驗證測試"""

    def test_capacity_zero_raises(self):
        """capacity_kwh <= 0 拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="capacity_kwh"):
            BMSSimConfig(capacity_kwh=0.0)

    def test_soc_above_100_raises(self):
        """initial_soc > 100 拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="initial_soc"):
            BMSSimConfig(initial_soc=101.0)

    def test_soc_below_zero_raises(self):
        """initial_soc < 0 拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="initial_soc"):
            BMSSimConfig(initial_soc=-1.0)

    def test_min_cell_ge_max_raises(self):
        """min_cell_voltage >= max_cell_voltage 拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="min_cell_voltage"):
            BMSSimConfig(min_cell_voltage=4.2, max_cell_voltage=4.2)

    def test_efficiency_zero_raises(self):
        """charge_efficiency <= 0 拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="charge_efficiency"):
            BMSSimConfig(charge_efficiency=0.0)

    def test_efficiency_above_one_raises(self):
        """charge_efficiency > 1 拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="charge_efficiency"):
            BMSSimConfig(charge_efficiency=1.1)

    def test_cells_zero_raises(self):
        """cells_in_series <= 0 拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="cells_in_series"):
            BMSSimConfig(cells_in_series=0)


class TestBMSUpdatePower:
    """BMS update_power 物理模擬測試"""

    def test_discharge_reduces_soc(self):
        """放電(+power) 降低 SOC"""
        sim = BMSSimulator(capacity_kwh=100.0, initial_soc=50.0)
        sim.update_power(power_kw=50.0, dt=1.0)
        soc = sim.get_value("soc")
        assert soc < 50.0

    def test_charge_increases_soc(self):
        """充電(-power) 增加 SOC"""
        sim = BMSSimulator(capacity_kwh=100.0, initial_soc=50.0)
        sim.update_power(power_kw=-50.0, dt=1.0)
        soc = sim.get_value("soc")
        assert soc > 50.0

    def test_charge_efficiency_applied(self):
        """充電 SOC 增加受效率折減"""
        # 放電 delta_soc = -P * dt / (C * 3600) * 100 = -(-50) * 1 / (100*3600) * 100 = 0.01389%
        # 充電效率 0.95 → delta_soc *= 0.95 = 0.01319%
        sim_efficient = BMSSimulator(capacity_kwh=100.0, initial_soc=50.0, charge_efficiency=0.95)
        sim_perfect = BMSSimulator(capacity_kwh=100.0, initial_soc=50.0, charge_efficiency=1.0)

        sim_efficient.update_power(power_kw=-50.0, dt=1.0)
        sim_perfect.update_power(power_kw=-50.0, dt=1.0)

        soc_efficient = sim_efficient.get_value("soc")
        soc_perfect = sim_perfect.get_value("soc")
        # 充電效率低 → SOC 增加量較少
        assert soc_efficient < soc_perfect

    def test_soc_clamp_at_zero(self):
        """放電超過容量 → SOC 鉗位在 0"""
        sim = BMSSimulator(capacity_kwh=100.0, initial_soc=1.0)
        sim.update_power(power_kw=1000.0, dt=3600.0)
        assert sim.get_value("soc") == 0.0

    def test_soc_clamp_at_100(self):
        """充電超過容量 → SOC 鉗位在 100"""
        sim = BMSSimulator(capacity_kwh=100.0, initial_soc=99.0)
        sim.update_power(power_kw=-1000.0, dt=3600.0)
        assert sim.get_value("soc") == 100.0

    def test_voltage_tracks_soc(self):
        """SOC 越高電壓越高"""
        sim_low = BMSSimulator(initial_soc=20.0)
        sim_high = BMSSimulator(initial_soc=80.0)
        assert sim_high.get_value("voltage") > sim_low.get_value("voltage")

    def test_current_positive_discharge(self):
        """放電時電流為正"""
        sim = BMSSimulator(initial_soc=50.0)
        sim.update_power(power_kw=50.0, dt=1.0)
        current = sim.get_value("current")
        assert current > 0

    def test_current_negative_charge(self):
        """充電時電流為負"""
        sim = BMSSimulator(initial_soc=50.0)
        sim.update_power(power_kw=-50.0, dt=1.0)
        current = sim.get_value("current")
        assert current < 0

    def test_temperature_writable_for_debug(self):
        """溫度可透過 on_write 設定（debug 用途，測試 alarm）"""
        sim = BMSSimulator(ambient_temperature=25.0)
        sim.on_write("temperature", 25.0, 60.0)
        assert sim.get_value("temperature") == 60.0
        assert sim._temperature == 60.0

    def test_temperature_stays_when_set(self):
        """溫度設定後不會自動變化（無溫升/散熱模型）"""
        sim = BMSSimulator(ambient_temperature=25.0)
        sim.on_write("temperature", 25.0, 60.0)
        sim.update_power(power_kw=50.0, dt=10.0)
        temp = sim.get_value("temperature")
        assert temp == 60.0

    def test_status_standby(self):
        """|power| < 0.1 → status = 0 (standby)"""
        sim = BMSSimulator()
        sim.update_power(power_kw=0.0, dt=1.0)
        assert sim.get_value("status") == 0

    def test_status_charging(self):
        """power < 0 → status = 1 (charging)"""
        sim = BMSSimulator()
        sim.update_power(power_kw=-50.0, dt=1.0)
        assert sim.get_value("status") == 1

    def test_status_discharging(self):
        """power > 0 → status = 2 (discharging)"""
        sim = BMSSimulator()
        sim.update_power(power_kw=50.0, dt=1.0)
        assert sim.get_value("status") == 2


class TestBMSAlarms:
    """BMS 告警測試"""

    def test_over_temp_alarm(self):
        """溫度 > 55 → bit 0"""
        sim = BMSSimulator(ambient_temperature=25.0, cooling_rate=0.0, thermal_coefficient=1.0)
        # 直接設定高溫再 update_power 觸發告警檢查
        sim._temperature = 60.0
        sim.set_value("temperature", 60.0)
        sim.update_power(power_kw=0.0, dt=0.0)
        alarm = sim.get_value("alarm_register")
        assert alarm & (1 << 0) != 0

    def test_soc_low_alarm(self):
        """SOC < 5 → bit 3"""
        sim = BMSSimulator(initial_soc=3.0)
        sim.update_power(power_kw=0.0, dt=0.0)
        alarm = sim.get_value("alarm_register")
        assert alarm & (1 << 3) != 0

    def test_soc_high_alarm(self):
        """SOC > 95 → bit 4"""
        sim = BMSSimulator(initial_soc=98.0)
        sim.update_power(power_kw=0.0, dt=0.0)
        alarm = sim.get_value("alarm_register")
        assert alarm & (1 << 4) != 0

    def test_no_alarm_normal(self):
        """正常狀態 → alarm_register = 0"""
        sim = BMSSimulator(initial_soc=50.0, ambient_temperature=25.0)
        sim.update_power(power_kw=0.0, dt=0.0)
        assert sim.get_value("alarm_register") == 0


class TestPCSBMSIntegration:
    """PCS-BMS 連結整合測試"""

    def _make_mg(self) -> MicrogridSimulator:
        return MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

    def test_link_pcs_bms_in_microgrid(self):
        """add_bms + link_pcs_bms 不拋錯"""
        mg = self._make_mg()
        pcs = PCSSimulator()
        bms = BMSSimulator()
        mg.add_pcs(pcs)
        mg.add_bms(bms)
        mg.link_pcs_bms(pcs.device_id, bms.device_id)  # 不應拋錯

    async def test_bms_soc_updated_by_pcs_power(self):
        """PCS-BMS 連結後，BMS SOC 由 PCS 功率驅動"""
        mg = self._make_mg()
        pcs = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0)
        pcs.on_write("start_cmd", 0, 1)
        pcs.on_write("p_setpoint", 0.0, 50.0)

        bms = BMSSimulator(capacity_kwh=100.0, initial_soc=80.0)
        mg.add_pcs(pcs)
        mg.add_bms(bms)
        mg.link_pcs_bms(pcs.device_id, bms.device_id)

        await mg.update(tick_interval=1.0)

        # BMS SOC 應減少（PCS 放電 → BMS SOC 下降）
        bms_soc = bms.get_value("soc")
        assert bms_soc < 80.0

    async def test_unlinked_pcs_uses_internal_soc(self):
        """未連結 BMS 的 PCS 使用內部 SOC 追蹤"""
        mg = self._make_mg()
        pcs = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0, capacity_kwh=100.0)
        pcs.on_write("start_cmd", 0, 1)
        pcs.on_write("p_setpoint", 0.0, 50.0)

        mg.add_pcs(pcs)
        # 不連結 BMS

        initial_soc = pcs.get_value("soc")
        await mg.update(tick_interval=1.0)
        after_soc = pcs.get_value("soc")

        # 放電應降低 SOC（PCS 內部追蹤）
        assert after_soc < initial_soc

    def test_invalid_pcs_link_raises(self):
        """連結不存在的 PCS 拋 ConfigurationError"""
        mg = self._make_mg()
        bms = BMSSimulator()
        mg.add_bms(bms)
        with pytest.raises(ConfigurationError, match="PCS"):
            mg.link_pcs_bms("nonexistent_pcs", bms.device_id)

    def test_invalid_bms_link_raises(self):
        """連結不存在的 BMS 拋 ConfigurationError"""
        mg = self._make_mg()
        pcs = PCSSimulator()
        mg.add_pcs(pcs)
        with pytest.raises(ConfigurationError, match="BMS"):
            mg.link_pcs_bms(pcs.device_id, "nonexistent_bms")

    def test_duplicate_pcs_link_raises(self):
        """重複連結同一 PCS 拋 ConfigurationError"""
        mg = self._make_mg()
        pcs = PCSSimulator()
        bms1 = BMSSimulator()
        bms2_cfg = default_bms_config(device_id="bms_2", unit_id=21)
        bms2 = BMSSimulator(config=bms2_cfg)

        mg.add_pcs(pcs)
        mg.add_bms(bms1)
        mg.add_bms(bms2)
        mg.link_pcs_bms(pcs.device_id, bms1.device_id)
        with pytest.raises(ConfigurationError, match=pcs.device_id):
            mg.link_pcs_bms(pcs.device_id, bms2.device_id)
