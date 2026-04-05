# =============== Modbus Server Tests - Multi-Meter & Device Link & Aggregation ===============
#
# v0.6.2 MicrogridSimulator 多電表、設備連結、電表聚合測試

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.modbus_server.config import (
    ControllabilityMode,
    DeviceLinkConfig,
    MeterAggregationConfig,
    MicrogridConfig,
)
from csp_lib.modbus_server.microgrid import MicrogridSimulator
from csp_lib.modbus_server.simulator.load import LoadSimulator
from csp_lib.modbus_server.simulator.pcs import PCSSimulator, default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import PowerMeterSimulator, default_meter_config
from csp_lib.modbus_server.simulator.solar import SolarSimulator

# ─── 輔助函式 ───


def _no_noise_mg() -> MicrogridSimulator:
    """建立無擾動 MicrogridSimulator"""
    return MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))


def _no_noise_meter(device_id: str = "meter_1", unit_id: int = 1) -> PowerMeterSimulator:
    """建立無擾動電表"""
    config = default_meter_config(device_id=device_id, unit_id=unit_id)
    return PowerMeterSimulator(config=config, voltage_noise=0.0, frequency_noise=0.0)


# =============================================================================
# C. Multi-meter 測試
# =============================================================================


class TestMultiMeterRegistration:
    """多電表註冊測試"""

    def test_add_meter_and_get(self):
        """add_meter 後可透過 get_meter 取得"""
        mg = _no_noise_mg()
        meter = _no_noise_meter("meter_sub", unit_id=2)
        mg.add_meter(meter, "meter_sub")
        assert mg.get_meter("meter_sub") is meter

    def test_add_meter_first_becomes_default(self):
        """第一個 add_meter 成為 default"""
        mg = _no_noise_mg()
        meter = _no_noise_meter("meter_first", unit_id=2)
        mg.add_meter(meter, "meter_first")
        assert mg.meter is meter

    def test_add_meter_second_not_default(self):
        """第二個 add_meter 不覆蓋 default"""
        mg = _no_noise_mg()
        m1 = _no_noise_meter("m1", unit_id=1)
        m2 = _no_noise_meter("m2", unit_id=2)
        mg.add_meter(m1, "m1")
        mg.add_meter(m2, "m2")
        assert mg.meter is m1

    def test_add_meter_duplicate_raises(self):
        """重複 meter_id 拋 ConfigurationError"""
        mg = _no_noise_mg()
        m1 = _no_noise_meter("m1", unit_id=1)
        m2 = _no_noise_meter("m1_dup", unit_id=2)
        mg.add_meter(m1, "m1")
        with pytest.raises(ConfigurationError, match="m1"):
            mg.add_meter(m2, "m1")

    def test_add_meter_uses_device_id_as_default(self):
        """未指定 meter_id 時使用 device_id"""
        mg = _no_noise_mg()
        meter = _no_noise_meter("auto_id", unit_id=3)
        mg.add_meter(meter)
        assert mg.get_meter("auto_id") is meter

    def test_get_meter_nonexistent_raises(self):
        """不存在的 meter_id 拋 KeyError"""
        mg = _no_noise_mg()
        with pytest.raises(KeyError, match="not_here"):
            mg.get_meter("not_here")

    def test_meters_property_returns_copy(self):
        """meters 屬性回傳 dict 副本"""
        mg = _no_noise_mg()
        meter = _no_noise_meter("m1", unit_id=1)
        mg.add_meter(meter, "m1")
        d = mg.meters
        d["m1"] = None  # type: ignore[assignment]
        # 原始不受影響
        assert mg.get_meter("m1") is meter

    def test_meters_property_contains_all(self):
        """meters 屬性包含所有電表"""
        mg = _no_noise_mg()
        m1 = _no_noise_meter("m1", unit_id=1)
        m2 = _no_noise_meter("m2", unit_id=2)
        mg.add_meter(m1, "m1")
        mg.add_meter(m2, "m2")
        assert set(mg.meters.keys()) == {"m1", "m2"}


class TestSetMeterBackwardCompat:
    """set_meter 向後相容測試"""

    def test_set_meter_accessible_via_meter_property(self):
        """set_meter 後可透過 .meter 取得"""
        mg = _no_noise_mg()
        meter = _no_noise_meter()
        mg.set_meter(meter)
        assert mg.meter is meter

    def test_set_meter_identity(self):
        """.meter 回傳相同物件（identity check）"""
        mg = _no_noise_mg()
        meter = _no_noise_meter()
        mg.set_meter(meter)
        assert mg.meter is meter

    def test_meter_none_initially(self):
        """初始 .meter 為 None"""
        mg = _no_noise_mg()
        assert mg.meter is None

    def test_all_simulators_includes_all_meters(self):
        """all_simulators 包含所有電表"""
        mg = _no_noise_mg()
        m1 = _no_noise_meter("m1", unit_id=1)
        m2 = _no_noise_meter("m2", unit_id=2)
        pcs = PCSSimulator()
        mg.add_meter(m1, "m1")
        mg.add_meter(m2, "m2")
        mg.add_pcs(pcs)
        sims = mg.all_simulators
        assert m1 in sims
        assert m2 in sims
        assert pcs in sims
        assert len(sims) == 3


# =============================================================================
# D. Device Link 測試
# =============================================================================


class TestAddDeviceLink:
    """add_device_link 驗證測試"""

    def test_valid_link(self):
        """有效連結不拋錯"""
        mg = _no_noise_mg()
        meter = _no_noise_meter("meter_sub", unit_id=2)
        pcs = PCSSimulator()
        mg.add_meter(meter, "meter_sub")
        mg.add_pcs(pcs)
        link = DeviceLinkConfig(source_device_id=pcs.device_id, target_meter_id="meter_sub")
        mg.add_device_link(link)  # 不應拋錯

    def test_source_not_registered_raises(self):
        """未註冊設備拋 ConfigurationError"""
        mg = _no_noise_mg()
        meter = _no_noise_meter("meter_sub", unit_id=2)
        mg.add_meter(meter, "meter_sub")
        link = DeviceLinkConfig(source_device_id="nonexistent", target_meter_id="meter_sub")
        with pytest.raises(ConfigurationError, match="nonexistent"):
            mg.add_device_link(link)

    def test_target_meter_not_registered_raises(self):
        """未註冊電表拋 ConfigurationError"""
        mg = _no_noise_mg()
        pcs = PCSSimulator()
        mg.add_pcs(pcs)
        link = DeviceLinkConfig(source_device_id=pcs.device_id, target_meter_id="nonexistent")
        with pytest.raises(ConfigurationError, match="nonexistent"):
            mg.add_device_link(link)

    def test_duplicate_source_raises(self):
        """重複來源拋 ConfigurationError"""
        mg = _no_noise_mg()
        meter = _no_noise_meter("meter_sub", unit_id=2)
        pcs = PCSSimulator()
        mg.add_meter(meter, "meter_sub")
        mg.add_pcs(pcs)
        link1 = DeviceLinkConfig(source_device_id=pcs.device_id, target_meter_id="meter_sub")
        link2 = DeviceLinkConfig(source_device_id=pcs.device_id, target_meter_id="meter_sub")
        mg.add_device_link(link1)
        with pytest.raises(ConfigurationError, match=pcs.device_id):
            mg.add_device_link(link2)


class TestDeviceLinkUpdate:
    """update() 時設備連結行為測試"""

    async def test_pcs_power_routes_to_linked_meter(self):
        """PCS 功率路由到連結的電表"""
        mg = _no_noise_mg()
        meter_main = _no_noise_meter("meter_main", unit_id=1)
        meter_sub = _no_noise_meter("meter_sub", unit_id=2)
        mg.add_meter(meter_main, "meter_main")
        mg.add_meter(meter_sub, "meter_sub")

        pcs = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0)
        pcs.on_write("start_cmd", 0, 1)
        pcs.on_write("p_setpoint", 0.0, 100.0)
        mg.add_pcs(pcs)

        # 連結 PCS → meter_sub
        link = DeviceLinkConfig(source_device_id=pcs.device_id, target_meter_id="meter_sub")
        mg.add_device_link(link)

        await mg.update(tick_interval=1.0)

        # meter_sub 應該有 PCS 放電功率（負值，因為發電減少電表讀數）
        sub_p = meter_sub.get_value("active_power")
        assert sub_p < 0  # PCS 放電 → 電表功率為負

        # meter_main（default）不應有 PCS 功率，只有 unlinked 設備的功率
        main_p = meter_main.get_value("active_power")
        assert abs(main_p) < 1.0  # 無其他設備，淨功率接近 0

    async def test_loss_factor_applied(self):
        """loss_factor 正確套用"""
        mg = _no_noise_mg()
        meter_sub = _no_noise_meter("meter_sub", unit_id=2)
        mg.add_meter(meter_sub, "meter_sub")

        pcs = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0)
        pcs.on_write("start_cmd", 0, 1)
        pcs.on_write("p_setpoint", 0.0, 100.0)
        mg.add_pcs(pcs)

        # 10% 損耗
        link = DeviceLinkConfig(source_device_id=pcs.device_id, target_meter_id="meter_sub", loss_factor=0.1)
        mg.add_device_link(link)

        await mg.update(tick_interval=1.0)

        # PCS 100 kW 放電 → 電表觀點 -100 * (1-0.1) = -90
        sub_p = meter_sub.get_value("active_power")
        assert abs(sub_p - (-90.0)) < 1.0

    async def test_two_pcs_linked_to_same_meter(self):
        """兩個 PCS 連結到同一電表，功率聚合"""
        mg = _no_noise_mg()
        meter_sub = _no_noise_meter("meter_sub", unit_id=2)
        mg.add_meter(meter_sub, "meter_sub")

        # PCS 1: 放電 60 kW
        pcs1 = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0)
        pcs1.on_write("start_cmd", 0, 1)
        pcs1.on_write("p_setpoint", 0.0, 60.0)

        # PCS 2: 放電 40 kW

        pcs2_cfg = default_pcs_config(device_id="pcs_2", unit_id=11)
        pcs2 = PCSSimulator(config=pcs2_cfg, p_ramp_rate=10000.0, tick_interval=1.0)
        pcs2.on_write("start_cmd", 0, 1)
        pcs2.on_write("p_setpoint", 0.0, 40.0)

        mg.add_pcs(pcs1)
        mg.add_pcs(pcs2)

        link1 = DeviceLinkConfig(source_device_id=pcs1.device_id, target_meter_id="meter_sub")
        link2 = DeviceLinkConfig(source_device_id=pcs2.device_id, target_meter_id="meter_sub")
        mg.add_device_link(link1)
        mg.add_device_link(link2)

        await mg.update(tick_interval=1.0)

        # 兩個 PCS 放電合計 -100 kW
        sub_p = meter_sub.get_value("active_power")
        assert abs(sub_p - (-100.0)) < 1.0

    async def test_linked_and_unlinked_coexist(self):
        """有連結與無連結設備共存"""
        mg = _no_noise_mg()
        meter_main = _no_noise_meter("meter_main", unit_id=1)
        meter_sub = _no_noise_meter("meter_sub", unit_id=2)
        mg.add_meter(meter_main, "meter_main")
        mg.add_meter(meter_sub, "meter_sub")

        # PCS（連結到 meter_sub）
        pcs = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0)
        pcs.on_write("start_cmd", 0, 1)
        pcs.on_write("p_setpoint", 0.0, 50.0)
        mg.add_pcs(pcs)

        # Load（未連結 → 進 default meter_main）
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=100.0,
            load_noise=0.0,
        )
        mg.add_load(load)

        link = DeviceLinkConfig(source_device_id=pcs.device_id, target_meter_id="meter_sub")
        mg.add_device_link(link)

        await mg.update(tick_interval=1.0)

        # meter_main 只有 load 的功率 (+100 kW)
        main_p = meter_main.get_value("active_power")
        assert abs(main_p - 100.0) < 1.0

        # meter_sub 只有 PCS 放電功率 (-50 kW)
        sub_p = meter_sub.get_value("active_power")
        assert abs(sub_p - (-50.0)) < 1.0


# =============================================================================
# E. Meter Aggregation 測試
# =============================================================================


class TestAddMeterAggregation:
    """add_meter_aggregation 驗證測試"""

    def test_valid_aggregation(self):
        """有效聚合不拋錯"""
        mg = _no_noise_mg()
        m1 = _no_noise_meter("m1", unit_id=1)
        m2 = _no_noise_meter("m2", unit_id=2)
        m_agg = _no_noise_meter("m_agg", unit_id=3)
        mg.add_meter(m1, "m1")
        mg.add_meter(m2, "m2")
        mg.add_meter(m_agg, "m_agg")

        agg = MeterAggregationConfig(source_meter_ids=("m1", "m2"), target_meter_id="m_agg")
        mg.add_meter_aggregation(agg)  # 不應拋錯

    def test_source_not_registered_raises(self):
        """來源電表未註冊拋 ConfigurationError"""
        mg = _no_noise_mg()
        m_agg = _no_noise_meter("m_agg", unit_id=3)
        mg.add_meter(m_agg, "m_agg")

        agg = MeterAggregationConfig(source_meter_ids=("nonexistent",), target_meter_id="m_agg")
        with pytest.raises(ConfigurationError, match="nonexistent"):
            mg.add_meter_aggregation(agg)

    def test_target_not_registered_raises(self):
        """目標電表未註冊拋 ConfigurationError"""
        mg = _no_noise_mg()
        m1 = _no_noise_meter("m1", unit_id=1)
        mg.add_meter(m1, "m1")

        agg = MeterAggregationConfig(source_meter_ids=("m1",), target_meter_id="nonexistent")
        with pytest.raises(ConfigurationError, match="nonexistent"):
            mg.add_meter_aggregation(agg)

    def test_cycle_two_nodes_raises(self):
        """A→B→A 循環拋 ConfigurationError"""
        mg = _no_noise_mg()
        ma = _no_noise_meter("A", unit_id=1)
        mb = _no_noise_meter("B", unit_id=2)
        mg.add_meter(ma, "A")
        mg.add_meter(mb, "B")

        # A → B
        agg1 = MeterAggregationConfig(source_meter_ids=("A",), target_meter_id="B")
        mg.add_meter_aggregation(agg1)

        # B → A 形成循環
        agg2 = MeterAggregationConfig(source_meter_ids=("B",), target_meter_id="A")
        with pytest.raises(ConfigurationError, match="循環"):
            mg.add_meter_aggregation(agg2)

    def test_cycle_three_nodes_raises(self):
        """A→B→C→A 三節點循環拋 ConfigurationError"""
        mg = _no_noise_mg()
        for name, uid in [("A", 1), ("B", 2), ("C", 3)]:
            mg.add_meter(_no_noise_meter(name, unit_id=uid), name)

        mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("A",), target_meter_id="B"))
        mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("B",), target_meter_id="C"))

        # C → A 形成循環
        with pytest.raises(ConfigurationError, match="循環"):
            mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("C",), target_meter_id="A"))

    def test_rollback_on_cycle_detection(self):
        """循環檢測失敗後不保留無效聚合"""
        mg = _no_noise_mg()
        for name, uid in [("A", 1), ("B", 2)]:
            mg.add_meter(_no_noise_meter(name, unit_id=uid), name)

        mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("A",), target_meter_id="B"))

        with pytest.raises(ConfigurationError):
            mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("B",), target_meter_id="A"))

        # 內部 _meter_aggregations 只有 1 條（回滾成功）
        assert len(mg._meter_aggregations) == 1


class TestMeterAggregationUpdate:
    """update() 時電表聚合行為測試"""

    async def test_target_gets_sum_of_sources(self):
        """目標電表取得來源電表功率總和"""
        mg = _no_noise_mg()
        m1 = _no_noise_meter("m1", unit_id=1)
        m2 = _no_noise_meter("m2", unit_id=2)
        m_agg = _no_noise_meter("m_agg", unit_id=3)
        mg.add_meter(m1, "m1")
        mg.add_meter(m2, "m2")
        mg.add_meter(m_agg, "m_agg")

        # 設備連結：不同 PCS → 不同子電表

        pcs1 = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0)
        pcs1.on_write("start_cmd", 0, 1)
        pcs1.on_write("p_setpoint", 0.0, 60.0)

        pcs2_cfg = default_pcs_config(device_id="pcs_2", unit_id=11)
        pcs2 = PCSSimulator(config=pcs2_cfg, p_ramp_rate=10000.0, tick_interval=1.0)
        pcs2.on_write("start_cmd", 0, 1)
        pcs2.on_write("p_setpoint", 0.0, 40.0)

        mg.add_pcs(pcs1)
        mg.add_pcs(pcs2)

        mg.add_device_link(DeviceLinkConfig(source_device_id=pcs1.device_id, target_meter_id="m1"))
        mg.add_device_link(DeviceLinkConfig(source_device_id=pcs2.device_id, target_meter_id="m2"))

        # 聚合：m1 + m2 → m_agg
        mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("m1", "m2"), target_meter_id="m_agg"))

        await mg.update(tick_interval=1.0)

        # m1 = -60, m2 = -40 → m_agg = -100
        m1_p = m1.get_value("active_power")
        m2_p = m2.get_value("active_power")
        agg_p = m_agg.get_value("active_power")

        assert abs(m1_p - (-60.0)) < 1.0
        assert abs(m2_p - (-40.0)) < 1.0
        assert abs(agg_p - (m1_p + m2_p)) < 1.0

    async def test_two_level_aggregation_tree(self):
        """兩層聚合樹：葉先算，再算父"""
        mg = _no_noise_mg()
        # 葉電表
        leaf1 = _no_noise_meter("leaf1", unit_id=1)
        leaf2 = _no_noise_meter("leaf2", unit_id=2)
        # 中間電表
        mid = _no_noise_meter("mid", unit_id=3)
        # 根電表
        root = _no_noise_meter("root", unit_id=4)

        for m, mid_str in [(leaf1, "leaf1"), (leaf2, "leaf2"), (mid, "mid"), (root, "root")]:
            mg.add_meter(m, mid_str)

        # PCS1 → leaf1 (30 kW)
        pcs1 = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0)
        pcs1.on_write("start_cmd", 0, 1)
        pcs1.on_write("p_setpoint", 0.0, 30.0)

        # PCS2 → leaf2 (20 kW)
        pcs2_cfg = default_pcs_config(device_id="pcs_2", unit_id=11)
        pcs2 = PCSSimulator(config=pcs2_cfg, p_ramp_rate=10000.0, tick_interval=1.0)
        pcs2.on_write("start_cmd", 0, 1)
        pcs2.on_write("p_setpoint", 0.0, 20.0)

        mg.add_pcs(pcs1)
        mg.add_pcs(pcs2)

        mg.add_device_link(DeviceLinkConfig(source_device_id=pcs1.device_id, target_meter_id="leaf1"))
        mg.add_device_link(DeviceLinkConfig(source_device_id=pcs2.device_id, target_meter_id="leaf2"))

        # 聚合樹: leaf1 + leaf2 → mid, mid → root（只有 mid 一個 source）
        mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("leaf1", "leaf2"), target_meter_id="mid"))
        mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("mid",), target_meter_id="root"))

        await mg.update(tick_interval=1.0)

        leaf1_p = leaf1.get_value("active_power")
        leaf2_p = leaf2.get_value("active_power")
        mid_p = mid.get_value("active_power")
        root_p = root.get_value("active_power")

        # leaf1 = -30, leaf2 = -20
        assert abs(leaf1_p - (-30.0)) < 1.0
        assert abs(leaf2_p - (-20.0)) < 1.0
        # mid = leaf1 + leaf2 = -50
        assert abs(mid_p - (leaf1_p + leaf2_p)) < 1.0
        # root = mid = -50（因為 mid 是唯一 source）
        assert abs(root_p - mid_p) < 1.0


# =============================================================================
# F. 向後相容 & 迴歸測試
# =============================================================================


class TestLegacyRegression:
    """確保 v0.6.2 不破壞既有行為"""

    async def test_legacy_set_meter_update_works(self):
        """舊式 set_meter + update 行為不變"""
        mg = _no_noise_mg()
        meter = _no_noise_meter()
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=100.0,
            load_noise=0.0,
        )
        mg.set_meter(meter)
        mg.add_load(load)

        await mg.update(tick_interval=1.0)

        meter_p = meter.get_value("active_power")
        assert abs(meter_p - 100.0) < 1.0

    async def test_no_links_no_aggregation_default_meter_gets_all(self):
        """無連結無聚合時，default 電表取得全部淨功率"""
        mg = _no_noise_mg()
        meter = _no_noise_meter()
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

        # 100 - 60 = 40
        meter_p = meter.get_value("active_power")
        assert abs(meter_p - 40.0) < 1.0

    async def test_energy_accumulation_per_meter(self):
        """每個電表都有獨立的能量累積"""
        mg = _no_noise_mg()
        m1 = _no_noise_meter("m1", unit_id=1)
        m2 = _no_noise_meter("m2", unit_id=2)
        mg.add_meter(m1, "m1")
        mg.add_meter(m2, "m2")

        # Load → default (m1)
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=100.0,
            load_noise=0.0,
        )
        mg.add_load(load)

        # 100 kW * 3600s = 100 kWh（for m1）
        await mg.update(tick_interval=3600.0)

        m1_energy = m1.get_value("energy_total")
        m2_energy = m2.get_value("energy_total")
        assert abs(m1_energy - 100.0) < 1.0
        # m2 沒有功率，能量接近 0
        assert abs(m2_energy) < 1.0

    async def test_accumulated_energy_property_backward_compat(self):
        """mg.accumulated_energy 使用 default 電表"""
        mg = _no_noise_mg()
        meter = _no_noise_meter()
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=36.0,
            load_noise=0.0,
        )
        mg.set_meter(meter)
        mg.add_load(load)

        # 36 kW * 100s / 3600 = 1 kWh
        await mg.update(tick_interval=100.0)
        assert abs(mg.accumulated_energy - 1.0) < 0.1

    async def test_empty_microgrid_update_no_crash(self):
        """空 microgrid update 不當機"""
        mg = _no_noise_mg()
        await mg.update(tick_interval=1.0)  # 不拋錯


# =============================================================================
# G. Sign Convention 混合測試
# =============================================================================


def _signed_meter(device_id: str, unit_id: int, power_sign: float) -> PowerMeterSimulator:
    """建立指定 power_sign 的無擾動電表"""
    config = default_meter_config(device_id=device_id, unit_id=unit_id)
    return PowerMeterSimulator(config=config, power_sign=power_sign, voltage_noise=0.0, frequency_noise=0.0)


class TestSignConventionMixed:
    """不同 power_sign 電表的聚合正確性測試

    修復前: 聚合使用 active_power（含 sign）→ 混合 sign 時結果錯誤
    修復後: 聚合使用 _raw_net_p（原始物理值）→ 正確
    """

    async def test_mixed_sign_aggregation(self):
        """Meter_PCS(sign=-1) + Meter_Load(sign=+1) → Meter_Total(sign=-1) 聚合正確

        PCS 放電 50kW: raw = -50, active_power = -50 * (-1) = +50（表前視角）
        Load 30kW: raw = +30, active_power = +30 * (+1) = +30（表後視角）
        聚合 raw = -50 + 30 = -20
        Meter_Total active_power = -20 * (-1) = +20（表前視角：淨出力 20kW）
        """
        mg = _no_noise_mg()

        # 表前電表（sign=-1）：PCS 放電
        meter_pcs = _signed_meter("meter_pcs", unit_id=1, power_sign=-1.0)
        # 表後電表（sign=+1）：Load
        meter_load = _signed_meter("meter_load", unit_id=2, power_sign=1.0)
        # 聚合電表（sign=-1）
        meter_total = _signed_meter("meter_total", unit_id=3, power_sign=-1.0)

        mg.add_meter(meter_pcs, "meter_pcs")
        mg.add_meter(meter_load, "meter_load")
        mg.add_meter(meter_total, "meter_total")

        # PCS 放電 50kW
        pcs = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0)
        pcs.on_write("start_cmd", 0, 1)
        pcs.on_write("p_setpoint", 0.0, 50.0)
        mg.add_pcs(pcs)

        # Load 30kW
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=30.0,
            load_noise=0.0,
        )
        mg.add_load(load)

        # PCS → meter_pcs, Load → meter_load
        mg.add_device_link(DeviceLinkConfig(source_device_id=pcs.device_id, target_meter_id="meter_pcs"))
        mg.add_device_link(DeviceLinkConfig(source_device_id=load.device_id, target_meter_id="meter_load"))

        # 聚合：meter_pcs + meter_load → meter_total
        mg.add_meter_aggregation(
            MeterAggregationConfig(source_meter_ids=("meter_pcs", "meter_load"), target_meter_id="meter_total")
        )

        await mg.update(tick_interval=1.0)

        # 驗證 raw 值
        assert abs(meter_pcs._raw_net_p - (-50.0)) < 1.0
        assert abs(meter_load._raw_net_p - 30.0) < 1.0

        # 聚合 raw = -50 + 30 = -20
        assert abs(meter_total._raw_net_p - (-20.0)) < 1.0

        # 聚合電表 active_power = raw * sign = -20 * (-1) = +20
        total_ap = meter_total.get_value("active_power")
        assert abs(total_ap - 20.0) < 1.0

    async def test_same_sign_aggregation(self):
        """所有電表 sign=-1 → 聚合仍正確"""
        mg = _no_noise_mg()

        m1 = _signed_meter("m1", unit_id=1, power_sign=-1.0)
        m2 = _signed_meter("m2", unit_id=2, power_sign=-1.0)
        m_agg = _signed_meter("m_agg", unit_id=3, power_sign=-1.0)

        mg.add_meter(m1, "m1")
        mg.add_meter(m2, "m2")
        mg.add_meter(m_agg, "m_agg")

        pcs1 = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0)
        pcs1.on_write("start_cmd", 0, 1)
        pcs1.on_write("p_setpoint", 0.0, 60.0)

        pcs2_cfg = default_pcs_config(device_id="pcs_2", unit_id=11)
        pcs2 = PCSSimulator(config=pcs2_cfg, p_ramp_rate=10000.0, tick_interval=1.0)
        pcs2.on_write("start_cmd", 0, 1)
        pcs2.on_write("p_setpoint", 0.0, 40.0)

        mg.add_pcs(pcs1)
        mg.add_pcs(pcs2)

        mg.add_device_link(DeviceLinkConfig(source_device_id=pcs1.device_id, target_meter_id="m1"))
        mg.add_device_link(DeviceLinkConfig(source_device_id=pcs2.device_id, target_meter_id="m2"))

        mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("m1", "m2"), target_meter_id="m_agg"))

        await mg.update(tick_interval=1.0)

        # raw: m1=-60, m2=-40, m_agg=-100
        assert abs(m_agg._raw_net_p - (-100.0)) < 1.0
        # active_power = -100 * (-1) = +100
        agg_ap = m_agg.get_value("active_power")
        assert abs(agg_ap - 100.0) < 1.0

    async def test_two_level_aggregation_mixed(self):
        """leaf(sign=-1) → mid(sign=+1) → root(sign=-1) 多層混合 sign 聚合

        確認每層聚合都使用 _raw_net_p，不受中間層 sign 影響。
        """
        mg = _no_noise_mg()

        leaf = _signed_meter("leaf", unit_id=1, power_sign=-1.0)
        mid = _signed_meter("mid", unit_id=2, power_sign=1.0)
        root = _signed_meter("root", unit_id=3, power_sign=-1.0)

        mg.add_meter(leaf, "leaf")
        mg.add_meter(mid, "mid")
        mg.add_meter(root, "root")

        # PCS 放電 80kW → leaf
        pcs = PCSSimulator(p_ramp_rate=10000.0, tick_interval=1.0)
        pcs.on_write("start_cmd", 0, 1)
        pcs.on_write("p_setpoint", 0.0, 80.0)
        mg.add_pcs(pcs)
        mg.add_device_link(DeviceLinkConfig(source_device_id=pcs.device_id, target_meter_id="leaf"))

        # leaf → mid → root
        mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("leaf",), target_meter_id="mid"))
        mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("mid",), target_meter_id="root"))

        await mg.update(tick_interval=1.0)

        # leaf raw = -80
        assert abs(leaf._raw_net_p - (-80.0)) < 1.0
        # mid raw = sum(leaf._raw_net_p) = -80（mid sign 不影響 raw 傳播）
        assert abs(mid._raw_net_p - (-80.0)) < 1.0
        # root raw = sum(mid._raw_net_p) = -80
        assert abs(root._raw_net_p - (-80.0)) < 1.0

        # 各電表 active_power 各自乘 sign
        assert abs(leaf.get_value("active_power") - 80.0) < 1.0  # -80 * -1 = 80
        assert abs(mid.get_value("active_power") - (-80.0)) < 1.0  # -80 * +1 = -80
        assert abs(root.get_value("active_power") - 80.0) < 1.0  # -80 * -1 = 80

    async def test_aggregation_raw_values_propagate(self):
        """驗證聚合後 _raw_net_p 正確設定在目標電表上"""
        mg = _no_noise_mg()

        m1 = _no_noise_meter("m1", unit_id=1)
        m2 = _no_noise_meter("m2", unit_id=2)
        m_agg = _no_noise_meter("m_agg", unit_id=3)

        mg.add_meter(m1, "m1")
        mg.add_meter(m2, "m2")
        mg.add_meter(m_agg, "m_agg")

        # Load 100kW → m1, Solar 60kW → m2
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=100.0,
            load_noise=0.0,
        )
        solar = SolarSimulator(power_noise=0.0, efficiency=1.0)
        solar.set_target_power(60.0)

        mg.add_load(load)
        mg.add_solar(solar)

        mg.add_device_link(DeviceLinkConfig(source_device_id=load.device_id, target_meter_id="m1"))
        mg.add_device_link(DeviceLinkConfig(source_device_id=solar.device_id, target_meter_id="m2"))

        mg.add_meter_aggregation(MeterAggregationConfig(source_meter_ids=("m1", "m2"), target_meter_id="m_agg"))

        await mg.update(tick_interval=1.0)

        # m1 raw = +100（load 消耗）, m2 raw = -60（solar 發電）
        assert abs(m1._raw_net_p - 100.0) < 1.0
        assert abs(m2._raw_net_p - (-60.0)) < 1.0

        # m_agg raw = 100 + (-60) = 40
        assert abs(m_agg._raw_net_p - 40.0) < 1.0
        # m_agg active_power = 40 * sign(+1) = 40
        assert abs(m_agg.get_value("active_power") - 40.0) < 1.0
