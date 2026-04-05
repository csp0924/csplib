# =============== Modbus Server - Microgrid Simulator ===============
#
# 微電網系統聯動協調器

from __future__ import annotations

import random
from collections import deque

from csp_lib.core import get_logger
from csp_lib.core.errors import ConfigurationError
from csp_lib.equipment.simulation.curve import CurvePoint, CurveRegistry, CurveType

from .behaviors.curve import CurveBehavior
from .config import DeviceLinkConfig, MeterAggregationConfig, MicrogridConfig
from .simulator.base import BaseDeviceSimulator
from .simulator.bms import BMSSimulator
from .simulator.generator import GeneratorSimulator
from .simulator.load import LoadSimulator
from .simulator.pcs import PCSSimulator
from .simulator.power_meter import PowerMeterSimulator
from .simulator.solar import SolarSimulator

logger = get_logger(__name__)


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
    - 設備連結: 可將設備功率導向指定電表（含損耗因子）
    - 電表聚合: 多個子電表功率累加到父電表（拓撲排序）
    """

    def __init__(self, config: MicrogridConfig | None = None) -> None:
        self._config = config or MicrogridConfig()
        self._meters: dict[str, PowerMeterSimulator] = {}
        self._default_meter_id: str | None = None
        self._pcs_list: list[PCSSimulator] = []
        self._solar_list: list[SolarSimulator] = []
        self._load_list: list[LoadSimulator] = []
        self._generator_list: list[GeneratorSimulator] = []
        self._device_links: list[DeviceLinkConfig] = []
        self._meter_aggregations: list[MeterAggregationConfig] = []
        self._aggregation_order: list[MeterAggregationConfig] = []
        self._bms_list: list[BMSSimulator] = []
        self._pcs_bms_links: dict[str, str] = {}
        self._accumulated_energy: float = 0.0
        # V/F override
        self._voltage_override: float | None = None
        self._frequency_override: float | None = None
        # V/F 曲線（使用 CurveBehavior）
        self._voltage_curve: CurveBehavior | None = None
        self._frequency_curve: CurveBehavior | None = None

    @property
    def config(self) -> MicrogridConfig:
        return self._config

    @property
    def meter(self) -> PowerMeterSimulator | None:
        """向後相容：回傳 default 電表。"""
        if self._default_meter_id is None:
            return None
        return self._meters.get(self._default_meter_id)

    @property
    def meters(self) -> dict[str, PowerMeterSimulator]:
        """所有已註冊電表的唯讀副本。"""
        return dict(self._meters)

    @property
    def accumulated_energy(self) -> float:
        """累積電量 (kWh)"""
        return self._accumulated_energy

    # ─── 電網 V/F 控制 ───

    def set_grid_voltage(self, voltage: float | None) -> None:
        """設定電網電壓 override。傳 None 恢復為 config 預設值 + noise。"""
        self._voltage_override = voltage
        if voltage is not None:
            self._voltage_curve = None  # override 優先於曲線

    def set_grid_frequency(self, frequency: float | None) -> None:
        """設定電網頻率 override。傳 None 恢復為 config 預設值 + noise。"""
        self._frequency_override = frequency
        if frequency is not None:
            self._frequency_curve = None

    @staticmethod
    def _parse_curve_points(points: list[tuple[float, ...]], curve_type: CurveType) -> list[CurvePoint]:
        """將 tuple 列表轉換為 CurvePoint 列表。

        支援格式：
        - (value, duration)                → step（固定值）
        - (value, duration, end_value)     → ramp（線性到 end_value）
        - (value, duration, None, rate)    → ramp（按 rate/s 變化）
        """
        result: list[CurvePoint] = []
        for t in points:
            if len(t) == 2:
                result.append(CurvePoint(value=t[0], duration=t[1], curve_type=curve_type))
            elif len(t) == 3:
                result.append(CurvePoint(value=t[0], duration=t[1], curve_type=curve_type, end_value=t[2]))
            elif len(t) == 4:
                if t[2] is not None:
                    raise ConfigurationError(
                        f"4 元素曲線 tuple 第 3 位須為 None: (value, duration, None, rate)，收到: {t}"
                    )
                result.append(CurvePoint(value=t[0], duration=t[1], curve_type=curve_type, rate=t[3]))
            else:
                raise ConfigurationError(f"曲線 tuple 須為 2~4 個元素，收到 {len(t)}: {t}")
        return result

    @staticmethod
    def _make_curve_behavior(
        points: list[tuple[float, ...]], default_value: float, curve_type: CurveType
    ) -> CurveBehavior:
        """從 tuple 列表建立 CurveBehavior。"""
        parsed = MicrogridSimulator._parse_curve_points(points, curve_type)
        registry = CurveRegistry()
        registry.register("_auto", lambda: iter(parsed))
        behavior = CurveBehavior(registry, default_value=default_value)
        behavior.start_curve("_auto")
        return behavior

    def set_voltage_curve(self, points: list[tuple[float, ...]]) -> None:
        """設定電壓曲線（簡便 API）。

        支援三種 tuple 格式：
        - (value, duration)              — step: 固定值持續 N 秒
        - (value, duration, end_value)   — ramp: 線性變化到 end_value
        - (value, duration, None, rate)  — ramp: 按 rate V/s 變化

        Example:
            mg.set_voltage_curve([
                (380, 10),                 # 固定 380V 10 秒
                (380, 60, 350),            # 380V → 350V 線性下降 60 秒
                (350, 10),                 # 固定 350V 10 秒
                (350, 30, None, 1.0),      # 350V 起，每秒 +1V 共 30 秒 → 380V
            ])
        """
        self._voltage_curve = self._make_curve_behavior(points, self._config.grid_voltage, CurveType.VOLTAGE)
        self._voltage_override = None

    def set_frequency_curve(self, points: list[tuple[float, ...]]) -> None:
        """設定頻率曲線（簡便 API）。

        支援三種 tuple 格式：
        - (value, duration)              — step: 固定頻率持續 N 秒
        - (value, duration, end_value)   — ramp: 線性變化到 end_value
        - (value, duration, None, rate)  — ramp: 按 rate Hz/s 變化

        Example:
            mg.set_frequency_curve([
                (60.0, 10),                # 固定 60Hz 10 秒
                (60.0, 100, None, -0.01),  # 60Hz 起，每秒 -0.01Hz 共 100 秒 → 59Hz
                (59.0, 10),                # 固定 59Hz 10 秒
                (59.0, 50, 60.0),          # 59Hz → 60Hz 線性回升 50 秒
            ])
        """
        self._frequency_curve = self._make_curve_behavior(points, self._config.grid_frequency, CurveType.FREQUENCY)
        self._frequency_override = None

    def set_voltage_behavior(self, behavior: CurveBehavior) -> None:
        """設定電壓 CurveBehavior（進階 API）。

        用於自訂 CurveProvider / CurveRegistry 場景。
        需自行呼叫 behavior.start_curve(name) 啟動曲線。

        Example:
            registry = CurveRegistry()
            registry.register("sag", my_voltage_sag_factory)
            behavior = CurveBehavior(registry, default_value=380.0)
            behavior.start_curve("sag")
            mg.set_voltage_behavior(behavior)
        """
        self._voltage_curve = behavior
        self._voltage_override = None

    def set_frequency_behavior(self, behavior: CurveBehavior) -> None:
        """設定頻率 CurveBehavior（進階 API）。"""
        self._frequency_curve = behavior
        self._frequency_override = None

    def _resolve_grid_value(
        self,
        override: float | None,
        curve: CurveBehavior | None,
        config_base: float,
        noise_range: float,
    ) -> float:
        """解析當前 V 或 F 值：override > curve > config+noise"""
        if override is not None:
            return override
        if curve is not None and curve.is_running:
            return curve.update()
        return config_base + random.uniform(-noise_range, noise_range)

    # ─── 設備註冊 ───

    def set_meter(self, meter: PowerMeterSimulator) -> None:
        """向後相容：等同 add_meter(meter, meter.device_id) + 設為 default。"""
        mid = meter.device_id
        self._meters[mid] = meter
        self._default_meter_id = mid

    def add_meter(self, meter: PowerMeterSimulator, meter_id: str | None = None) -> None:
        """
        註冊電表。meter_id 預設使用 meter.device_id。

        Args:
            meter: 電表模擬器實例
            meter_id: 電表識別碼（預設使用 meter.device_id）

        Raises:
            ConfigurationError: 電表 ID 已存在
        """
        mid = meter_id or meter.device_id
        if mid in self._meters:
            raise ConfigurationError(f"電表 '{mid}' 已存在")
        self._meters[mid] = meter
        if self._default_meter_id is None:
            self._default_meter_id = mid

    def get_meter(self, meter_id: str) -> PowerMeterSimulator:
        """
        取得指定 ID 的電表。

        Args:
            meter_id: 電表識別碼

        Returns:
            對應的電表模擬器

        Raises:
            KeyError: 電表不存在
        """
        if meter_id not in self._meters:
            raise KeyError(f"電表 '{meter_id}' 不存在")
        return self._meters[meter_id]

    def add_pcs(self, pcs: PCSSimulator) -> None:
        self._pcs_list.append(pcs)

    def add_solar(self, solar: SolarSimulator) -> None:
        self._solar_list.append(solar)

    def add_load(self, load: LoadSimulator) -> None:
        self._load_list.append(load)

    def add_generator(self, gen: GeneratorSimulator) -> None:
        self._generator_list.append(gen)

    def add_bms(self, bms: BMSSimulator) -> None:
        """註冊 BMS 模擬器。"""
        for existing in self._bms_list:
            if existing.device_id == bms.device_id:
                raise ConfigurationError(f"BMS '{bms.device_id}' 已存在")
        self._bms_list.append(bms)

    def link_pcs_bms(self, pcs_id: str, bms_id: str) -> None:
        """連結 PCS 與 BMS，PCS 的 SOC 將由 BMS 管理。"""
        if not any(p.device_id == pcs_id for p in self._pcs_list):
            raise ConfigurationError(f"PCS '{pcs_id}' 未註冊")
        if not any(b.device_id == bms_id for b in self._bms_list):
            raise ConfigurationError(f"BMS '{bms_id}' 未註冊")
        if pcs_id in self._pcs_bms_links:
            raise ConfigurationError(f"PCS '{pcs_id}' 已有 BMS 連結")
        self._pcs_bms_links[pcs_id] = bms_id

    def _find_bms(self, bms_id: str) -> BMSSimulator | None:
        """在 BMS 列表中查找 bms_id。"""
        for b in self._bms_list:
            if b.device_id == bms_id:
                return b
        return None

    # ─── 設備連結 ───

    def add_device_link(self, link: DeviceLinkConfig) -> None:
        """
        新增設備到電表的連結。

        Args:
            link: 設備連結配置

        Raises:
            ConfigurationError: 設備未註冊、電表未註冊、或設備已有連結
        """
        all_device_ids = {
            d.device_id for d in self._pcs_list + self._solar_list + self._load_list + self._generator_list
        }
        if link.source_device_id not in all_device_ids:
            raise ConfigurationError(f"設備 '{link.source_device_id}' 未註冊")
        if link.target_meter_id not in self._meters:
            raise ConfigurationError(f"電表 '{link.target_meter_id}' 未註冊")
        # 不允許重複來源
        existing_sources = {lnk.source_device_id for lnk in self._device_links}
        if link.source_device_id in existing_sources:
            raise ConfigurationError(f"設備 '{link.source_device_id}' 已有連結")
        self._device_links.append(link)

    # ─── 電表聚合 ───

    def add_meter_aggregation(self, agg: MeterAggregationConfig) -> None:
        """
        新增電表聚合。立即驗證是否存在循環。

        Args:
            agg: 電表聚合配置

        Raises:
            ConfigurationError: 來源/目標電表未註冊、或聚合圖存在循環
        """
        for mid in agg.source_meter_ids:
            if mid not in self._meters:
                raise ConfigurationError(f"來源電表 '{mid}' 未註冊")
        if agg.target_meter_id not in self._meters:
            raise ConfigurationError(f"目標電表 '{agg.target_meter_id}' 未註冊")
        # 同一 target 不可重複設定聚合
        for existing in self._meter_aggregations:
            if existing.target_meter_id == agg.target_meter_id:
                raise ConfigurationError(f"電表 '{agg.target_meter_id}' 已有聚合規則")

        # 暫時新增，驗證後保留或回滾
        self._meter_aggregations.append(agg)
        try:
            self._aggregation_order = self._build_aggregation_order()
        except ConfigurationError:
            self._meter_aggregations.pop()  # 回滾
            raise

    def _build_aggregation_order(self) -> list[MeterAggregationConfig]:
        """
        Kahn 拓撲排序 + cycle detection。

        Returns:
            拓撲排序後的聚合規則列表

        Raises:
            ConfigurationError: 聚合圖存在循環
        """
        if not self._meter_aggregations:
            return []

        agg_by_target: dict[str, MeterAggregationConfig] = {}
        for agg in self._meter_aggregations:
            agg_by_target[agg.target_meter_id] = agg

        # 建構依賴圖：規則 A 依賴規則 B（若 A 的 source 是 B 的 target）
        targets = set(agg_by_target.keys())
        deps: dict[str, set[str]] = {t: set() for t in targets}
        for agg in self._meter_aggregations:
            for src in agg.source_meter_ids:
                if src in targets:
                    deps[agg.target_meter_id].add(src)

        # Kahn's algorithm
        in_degree = {t: len(d) for t, d in deps.items()}
        queue: deque[str] = deque(t for t, d in in_degree.items() if d == 0)
        result: list[MeterAggregationConfig] = []

        while queue:
            t = queue.popleft()
            result.append(agg_by_target[t])
            for other_t, other_deps in deps.items():
                if t in other_deps:
                    in_degree[other_t] -= 1
                    if in_degree[other_t] == 0:
                        queue.append(other_t)

        if len(result) != len(targets):
            raise ConfigurationError("電表聚合圖存在循環")
        return result

    # ─── 屬性 ───

    @property
    def all_simulators(self) -> list[BaseDeviceSimulator]:
        """所有已註冊的模擬器"""
        sims: list[BaseDeviceSimulator] = []
        sims.extend(self._meters.values())
        sims.extend(self._pcs_list)
        sims.extend(self._solar_list)
        sims.extend(self._load_list)
        sims.extend(self._generator_list)
        sims.extend(self._bms_list)
        return sims

    # ─── 內部輔助 ───

    def _find_device(self, device_id: str) -> BaseDeviceSimulator | None:
        """在所有設備列表中查找 device_id。"""
        for d in self._pcs_list + self._solar_list + self._load_list + self._generator_list:
            if d.device_id == device_id:
                return d
        return None

    def _get_device_power(self, device: BaseDeviceSimulator) -> tuple[float, float]:
        """
        取得設備的 (net_p_contribution, net_q_contribution) for meter。

        Sign convention for meter perspective:
        - Load: +P（消耗增加電表讀數）
        - PCS/Solar/Generator: -P（發電減少電表讀數）
        """
        if isinstance(device, LoadSimulator):
            p = float(device.get_value("p_actual") or 0.0)
            q = float(device.get_value("q_actual") or 0.0)
            return (p, q)
        elif isinstance(device, PCSSimulator):
            p = float(device.get_value("p_actual") or 0.0)
            q = float(device.get_value("q_actual") or 0.0)
            return (-p, -q)
        elif isinstance(device, SolarSimulator):
            p = float(device.get_value("ac_power") or 0.0)
            return (-p, 0.0)
        elif isinstance(device, GeneratorSimulator):
            p = float(device.get_value("p_actual") or 0.0)
            q = float(device.get_value("q_actual") or 0.0)
            return (-p, -q)
        return (0.0, 0.0)

    def _compute_unlinked_net_power(self, linked_ids: set[str]) -> tuple[float, float]:
        """計算未連結設備的淨功率（排除已連結的設備）。"""
        total_load_p = sum(
            float(d.get_value("p_actual") or 0.0) for d in self._load_list if d.device_id not in linked_ids
        )
        total_load_q = sum(
            float(d.get_value("q_actual") or 0.0) for d in self._load_list if d.device_id not in linked_ids
        )

        total_solar_p = sum(
            float(d.get_value("ac_power") or 0.0) for d in self._solar_list if d.device_id not in linked_ids
        )
        total_solar_q = 0.0  # 太陽能通常功率因數 ~1

        total_pcs_p = sum(
            float(d.get_value("p_actual") or 0.0) for d in self._pcs_list if d.device_id not in linked_ids
        )
        total_pcs_q = sum(
            float(d.get_value("q_actual") or 0.0) for d in self._pcs_list if d.device_id not in linked_ids
        )

        total_gen_p = sum(
            float(d.get_value("p_actual") or 0.0) for d in self._generator_list if d.device_id not in linked_ids
        )
        total_gen_q = sum(
            float(d.get_value("q_actual") or 0.0) for d in self._generator_list if d.device_id not in linked_ids
        )

        net_p = total_load_p - total_solar_p - total_pcs_p - total_gen_p
        net_q = total_load_q - total_solar_q - total_pcs_q - total_gen_q
        return (net_p, net_q)

    # ─── 主更新邏輯 ───

    async def update(self, tick_interval: float) -> None:
        """
        系統級聯動更新

        Tick 更新順序:
        1. 計算系統電壓/頻率
        2. 更新 Solar — 產出功率
        3. 更新 Generator — 產出功率
        4. 更新 Load — 消耗功率
        5. 更新 PCS — 根據 setpoint ramp + SOC 計算
        6. 重置連結電表累加器
        7. 設備連結 + 全域功率平衡 → 電表
        8. 電表聚合樹（拓撲排序）
        9. 能量累積
        """
        # Step 1: 系統電壓/頻率（override > curve > config+noise）
        cfg = self._config
        system_v = self._resolve_grid_value(
            self._voltage_override, self._voltage_curve, cfg.grid_voltage, cfg.voltage_noise
        )
        system_f = self._resolve_grid_value(
            self._frequency_override, self._frequency_curve, cfg.grid_frequency, cfg.frequency_noise
        )

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

        # Step 5: 更新 PCS + SOC（若有 BMS 連結，由 BMS 管理 SOC）
        for pcs in self._pcs_list:
            pcs.set_value("voltage", system_v)
            pcs.set_value("frequency", system_f)
            await pcs.update()
            if pcs.device_id in self._pcs_bms_links:
                bms_id = self._pcs_bms_links[pcs.device_id]
                bms = self._find_bms(bms_id)
                if bms:
                    p_actual = float(pcs.get_value("p_actual") or 0.0)
                    bms.update_power(p_actual, tick_interval)
                    # 有 BMS 時不更新 PCS 內部 SOC，SOC 應從 BMS 讀取
            else:
                pcs.update_soc(tick_interval)

        # Step 6: 重置連結電表累加器
        for meter in self._meters.values():
            meter.reset_linked_power()

        # Step 7: 設備連結 + 全域功率平衡
        linked_device_ids: set[str] = set()

        # 7a: 處理設備連結
        for link in self._device_links:
            linked_device_ids.add(link.source_device_id)
            device = self._find_device(link.source_device_id)
            if device is None:
                continue
            p, q = self._get_device_power(device)
            effective_p = p * (1 - link.loss_factor)
            effective_q = q * (1 - link.loss_factor)
            self._meters[link.target_meter_id].add_linked_power(effective_p, effective_q)

        # 7b: 未連結設備 → 全域淨功率 → default 電表
        net_p, net_q = self._compute_unlinked_net_power(linked_device_ids)
        if self._default_meter_id and self._default_meter_id in self._meters:
            self._meters[self._default_meter_id].add_linked_power(net_p, net_q)

        # 7c: Finalize 所有電表
        for meter in self._meters.values():
            meter.finalize_linked_reading(system_v, system_f)

        # Step 8: 電表聚合樹（拓撲排序）
        for agg in self._aggregation_order:
            sum_p = sum(self._meters[src]._raw_net_p for src in agg.source_meter_ids)
            sum_q = sum(self._meters[src]._raw_net_q for src in agg.source_meter_ids)
            self._meters[agg.target_meter_id].set_partial_reading(sum_p, sum_q)

        # Step 9: 能量累積
        for meter in self._meters.values():
            p = float(meter.get_value("active_power") or 0.0)
            meter.accumulate_energy(p, tick_interval)

        # Coordinator 層級累積（向後相容）
        if self._default_meter_id and self._default_meter_id in self._meters:
            default_p = float(self._meters[self._default_meter_id].get_value("active_power") or 0.0)
            self._accumulated_energy += default_p * tick_interval / 3600.0
        else:
            self._accumulated_energy += net_p * tick_interval / 3600.0


__all__ = ["MicrogridSimulator"]
