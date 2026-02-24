# =============== Modbus Server - Microgrid Simulator ===============
#
# 微電網系統聯動協調器

from __future__ import annotations

import random

from csp_lib.core import get_logger

from .config import MicrogridConfig
from .simulator.base import BaseDeviceSimulator
from .simulator.generator import GeneratorSimulator
from .simulator.load import LoadSimulator
from .simulator.pcs import PCSSimulator
from .simulator.power_meter import PowerMeterSimulator
from .simulator.solar import SolarSimulator

logger = get_logger("csp_lib.modbus_server.microgrid")


class MicrogridSimulator:
    """
    微電網系統聯動協調器

    管理所有設備模擬器之間的物理關係：
    - 功率平衡: P_grid = P_load - P_solar - P_pcs - P_generator
      (正值=從電網取電，負值=輸出到電網)
    - Sign convention:
      - PCS: +discharge / -charge
      - Solar/Generator: 值恆正（發電量）
      - Load: 值恆正（用電量）
      - Meter: 正負號由 power_sign 配置決定
    - SOC 追蹤: PCS 的 SOC 根據 p_actual 與容量動態更新
    - 電壓/頻率: 所有設備共用系統電壓/頻率（加個別擾動）
    - 累積電量: 電表 energy_total 根據功率積分
    """

    def __init__(self, config: MicrogridConfig | None = None) -> None:
        self._config = config or MicrogridConfig()
        self._meter: PowerMeterSimulator | None = None
        self._pcs_list: list[PCSSimulator] = []
        self._solar_list: list[SolarSimulator] = []
        self._load_list: list[LoadSimulator] = []
        self._generator_list: list[GeneratorSimulator] = []
        self._accumulated_energy: float = 0.0

    @property
    def config(self) -> MicrogridConfig:
        return self._config

    @property
    def meter(self) -> PowerMeterSimulator | None:
        return self._meter

    @property
    def accumulated_energy(self) -> float:
        """累積電量 (kWh)"""
        return self._accumulated_energy

    # 設備註冊
    def set_meter(self, meter: PowerMeterSimulator) -> None:
        self._meter = meter

    def add_pcs(self, pcs: PCSSimulator) -> None:
        self._pcs_list.append(pcs)

    def add_solar(self, solar: SolarSimulator) -> None:
        self._solar_list.append(solar)

    def add_load(self, load: LoadSimulator) -> None:
        self._load_list.append(load)

    def add_generator(self, gen: GeneratorSimulator) -> None:
        self._generator_list.append(gen)

    @property
    def all_simulators(self) -> list[BaseDeviceSimulator]:
        """所有已註冊的模擬器"""
        sims: list[BaseDeviceSimulator] = []
        if self._meter:
            sims.append(self._meter)
        sims.extend(self._pcs_list)
        sims.extend(self._solar_list)
        sims.extend(self._load_list)
        sims.extend(self._generator_list)
        return sims

    async def update(self, tick_interval: float) -> None:
        """
        系統級聯動更新

        Tick 更新順序:
        1. 計算系統電壓/頻率
        2. 更新 Solar — 產出功率
        3. 更新 Generator — 產出功率
        4. 更新 Load — 消耗功率
        5. 更新 PCS — 根據 setpoint ramp + SOC 計算
        6. 聯動更新 Meter — 淨功率流
        7. 更新能量累積
        """
        # Step 1: 系統電壓/頻率
        cfg = self._config
        system_v = cfg.grid_voltage + random.uniform(-cfg.voltage_noise, cfg.voltage_noise)
        system_f = cfg.grid_frequency + random.uniform(-cfg.frequency_noise, cfg.frequency_noise)

        # Step 2: 更新 Solar
        for solar in self._solar_list:
            solar.set_value("ac_voltage", system_v)
            solar.set_value("frequency", system_f)
            await solar.update()

        # Step 3: 更新 Generator
        for gen in self._generator_list:
            await gen.update()

        # Step 4: 更新 Load
        for load in self._load_list:
            load.set_value("voltage", system_v)
            load.set_value("frequency", system_f)
            await load.update()

        # Step 5: 更新 PCS + SOC
        for pcs in self._pcs_list:
            pcs.set_value("voltage", system_v)
            pcs.set_value("frequency", system_f)
            await pcs.update()
            pcs.update_soc(tick_interval)

        # Step 6: 功率平衡 → 電表
        total_load_p = sum(float(load.get_value("p_actual") or 0.0) for load in self._load_list)
        total_load_q = sum(float(load.get_value("q_actual") or 0.0) for load in self._load_list)

        total_solar_p = sum(float(solar.get_value("ac_power") or 0.0) for solar in self._solar_list)
        total_solar_q = 0.0  # 太陽能通常功率因數 ~1

        total_pcs_p = sum(float(pcs.get_value("p_actual") or 0.0) for pcs in self._pcs_list)
        total_pcs_q = sum(float(pcs.get_value("q_actual") or 0.0) for pcs in self._pcs_list)

        total_gen_p = sum(float(gen.get_value("p_actual") or 0.0) for gen in self._generator_list)
        total_gen_q = sum(float(gen.get_value("q_actual") or 0.0) for gen in self._generator_list)

        # 淨功率 = 負載 - 太陽能 - PCS - 發電機 (正值=從電網取電)
        net_p = total_load_p - total_solar_p - total_pcs_p - total_gen_p
        net_q = total_load_q - total_solar_q - total_pcs_q - total_gen_q

        if self._meter:
            self._meter.set_system_reading(v=system_v, f=system_f, p=net_p, q=net_q)

        # Step 7: 累積電量 (kWh)
        self._accumulated_energy += net_p * tick_interval / 3600.0

        if self._meter:
            self._meter.accumulate_energy(net_p, tick_interval)


__all__ = ["MicrogridSimulator"]
