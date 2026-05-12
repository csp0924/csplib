# =============== Power Compensator ===============
#
# 前饋 + 積分閉環功率補償器
#
# 控制方程式：command = ff(power_bin) × setpoint + Ki × ∫error·dt
#
# 職責：
#   - 前饋補償：按功率區間查表，補償 PCS 非線性與輔電損耗
#   - 積分修正：短期殘差修正，含 anti-windup / deadband / clamp
#   - 穩態學習：I 項貢獻吸收進 FF 表，長期自適應
#   - 暫態閘門：setpoint 變更後等 PCS 到位才啟動 I
#   - FF 表持久化：JSON 檔案存/讀
#
# 實作 CommandProcessor Protocol，可作為 post_protection_processor 使用。
#
# Usage::
#
#     compensator = PowerCompensator(PowerCompensatorConfig(
#         rated_power=2000.0,
#         measurement_key="meter_power",
#     ))
#
#     config = SystemControllerConfig(
#         post_protection_processors=[compensator],
#     )

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from csp_lib.controller.core import Command, StrategyContext, is_no_change
from csp_lib.core import get_logger
from csp_lib.core._numeric import clamp, is_non_finite_float

logger = get_logger(__name__)

# 3σ 涵蓋約 99.7% 的高斯 noise；用於從 measurement_noise_kw 推算 effective deadband
_NOISE_SIGMA_MULTIPLIER = 3.0


def _cycles_from_seconds(seconds: float, dt: float, *, floor: int) -> int:
    """把「秒」表達的時間預算換成 runtime cycles。

    ``dt <= 0`` 時退回 ``floor``（避免除零，並讓 hold_seconds=0 在 dt=0 時得到 0）。
    """
    if dt <= 0:
        return floor
    return max(floor, round(seconds / dt))


# =============== FF Table Repository ===============


@runtime_checkable
class FFTableRepository(Protocol):
    """
    FF Table 持久化介面

    實作此 Protocol 即可支援任意後端（JSON、MongoDB、Redis 等）。
    PowerCompensator 透過此介面存取 FF Table。
    """

    def save(self, table: dict[int, float]) -> None:
        """儲存 FF Table"""
        ...

    def load(self) -> dict[int, float] | None:
        """載入 FF Table，不存在時回傳 None"""
        ...


class JsonFFTableRepository:
    """
    JSON 檔案持久化（預設實作）

    支援不同 step 的 FF Table 自動遷移（線性插值）。

    Args:
        path: JSON 檔案路徑
        power_bin_step_pct: 當前 FF Table 的 step 百分比（用於遷移偵測）
    """

    def __init__(self, path: str, power_bin_step_pct: int = 5) -> None:
        self._path = path
        self._step_pct = power_bin_step_pct

    def save(self, table: dict[int, float]) -> None:
        try:
            data = {str(k): v for k, v in table.items()}
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            logger.opt(exception=True).warning("JsonFFTableRepository: failed to save")

    def load(self) -> dict[int, float] | None:
        if not Path(self._path).exists():
            return None
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            if not data:
                return None
            return {int(k): float(v) for k, v in data.items()}
        except Exception:
            logger.opt(exception=True).warning("JsonFFTableRepository: failed to load")
            return None


class MongoFFTableRepository:
    """
    MongoDB 持久化

    將 FF Table 存為單一 document，格式::

        {
            "_id": <document_id>,
            "table": {"0": 1.0, "5": 1.02, "-5": 0.98, ...},
            "updated_at": <datetime>
        }

    Args:
        collection: motor AsyncIOMotorCollection 實例
        document_id: document 的 _id（預設 "ff_table"）
    """

    def __init__(self, collection: Any, document_id: str = "ff_table") -> None:
        self._collection = collection
        self._doc_id = document_id

    def save(self, table: dict[int, float]) -> None:
        """同步包裝 — 在 asyncio event loop 中排程 async save"""

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_save(table))
        except RuntimeError:
            logger.warning("MongoFFTableRepository: no running event loop, skip save")

    def load(self) -> dict[int, float] | None:
        """同步包裝 — 用於 PowerCompensator.__init__，無法 await"""
        # MongoDB load 需要 async，init 時無法 await
        # 由 async_load() 在 start 階段呼叫
        logger.debug("MongoFFTableRepository: sync load not available, use async_load()")
        return None

    async def _async_save(self, table: dict[int, float]) -> None:
        from datetime import datetime, timezone

        try:
            data = {str(k): v for k, v in table.items()}
            await self._collection.update_one(
                {"_id": self._doc_id},
                {"$set": {"table": data, "updated_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
            logger.debug(f"MongoFFTableRepository: saved {len(table)} bins")
        except Exception:
            logger.opt(exception=True).warning("MongoFFTableRepository: failed to save")

    async def async_load(self) -> dict[int, float] | None:
        """
        Async 載入 FF Table

        在 PowerCompensator 啟動後呼叫::

            repo = MongoFFTableRepository(collection)
            table = await repo.async_load()
            if table:
                compensator.load_ff_table(table)
        """
        try:
            doc = await self._collection.find_one({"_id": self._doc_id})
            if doc and "table" in doc:
                return {int(k): float(v) for k, v in doc["table"].items()}
            return None
        except Exception:
            logger.opt(exception=True).warning("MongoFFTableRepository: failed to load")
            return None


@dataclass(frozen=True, slots=True)
class PowerCompensatorConfig:
    """
    功率補償器配置

    v0.8 起所有時間相關參數改用「秒」表達，與 dt 解耦；deadband 改用 ratio
    自動跟著 rated_power scale。詳見 v0.8 BREAKING 段落。

    Attributes:
        rated_power: 系統額定功率 (kW)
        output_min: 輸出下限 (kW)
        output_max: 輸出上限 (kW)
        integral_time_seconds: I 項時間常數 (秒)。物理意義：誤差持續為 rated_power
            (100% 額定) 時，I 在這段時間內打滿 ``integral_max_ratio × rated``。
            ``None`` 或 ``<= 0`` = 停用 I 項（負值同樣 silently 視為停用）。
            等效 Ki = integral_max_ratio / integral_time_seconds。
        integral_max_ratio: I 項最大貢獻 = ratio × rated_power
        deadband_ratio: 死區佔 rated 的比例（預設 0.00025 = 0.025%）。誤差低於
            ``deadband_ratio × rated_power`` 不累積 I。
        deadband_setpoint_ratio: 死區佔 |setpoint| 的比例（預設 0.02 = 2%）。
            小 setpoint 時用此值取代固定 deadband，避免「setpoint × plant_loss < 固定
            deadband」造成積分閘門 + 學習閘門雙重鎖死、FF 永遠卡在 1.0。
            實際 deadband = ``max(noise_floor, min(deadband_ratio × rated, |setpoint| × ratio))``。
            ``0`` 或負值 = 停用相對縮放（純走 absolute deadband，等同 v0.8.0 行為）。
        measurement_noise_kw: （選用）量測 noise 標準差估計 (kW)。若提供，實際
            死區 = ``max(deadband_ratio × rated, 3σ)``；不提供或非正值則純用 ratio。
        power_bin_step_pct: FF 表功率區間寬度 (% of rated)
        steady_state_threshold: 穩態門檻 |error/setpoint| (相對)；內部會強制以
            effective deadband 作為下限，避免誤差小於 deadband 反而被認為穩態。
        steady_state_seconds: 連續穩態時間 (秒)，達標後觸發 FF 學習。runtime
            cycles = ``max(1, round(steady_state_seconds / dt))``。
        settle_ratio: 暫態閘門比例，setpoint 變更後 |error| > 變化量 × settle_ratio 時不倒數
        hold_seconds: setpoint 變更後暫停積分的時間 (秒)；runtime cycles = round(hold_seconds / dt)。
        setpoint_change_threshold_ratio: setpoint 變動「視為改變」的相對閾值（佔 rated）。
            預設 0.00005 = 0.005%（對 rated=2000kW 為 0.1kW，對應舊 v0.7 hardcoded 行為）。
            上游若有 round-off / float drift 時調大此值可避免每 cycle 誤觸發 reset。
        ff_min: FF 補償係數下限
        ff_max: FF 補償係數上限
        error_ema_alpha: 誤差 EMA 濾波係數 (0=停用)
        rate_limit: 輸出變化率限制 (kW/s)。``None`` = 不限（假設上游已 ramp）。
            注意：rate_limit 只約束 compensate() 輸出，FF 自我修正造成的輸出跳變
            （`_learn_from_saturation` 每次最多動 FF saturation_learn_max_step）
            乘以 setpoint 仍會穿透；若需嚴格 ramp 限制，請在此層或上層明確設值。
        measurement_key: context.extra 中量測值的 key
        persist_path: FF 表持久化路徑 (空=不持久化)
        saturation_learn_min_cycles: 連續飽和 N 個週期後才觸發飽和學習
            （避免單次瞬態飽和即更新 FF）
        saturation_learn_alpha: 飽和學習的 EMA 平滑係數 (0~1)，
            1.0 = 完全採用物理推算值，0.0 = 完全保留舊值
        saturation_learn_max_step: 單次飽和學習的 FF 最大變動量
            （限制單步衝擊，預設 0.03 對應約 1.5 秒收斂）
    """

    rated_power: float = 2000.0
    output_min: float = -2000.0
    output_max: float = 2000.0
    # 預設 ≈ 0.167s，對應舊 v0.7 ki=0.3 的行為（integral_max_ratio / 0.3）。
    # 改大會讓 I 響應變慢、改小會變快；單位是「對 100% rated error 時 I 打滿 max 的時間」。
    integral_time_seconds: float | None = 0.05 / 0.3
    integral_max_ratio: float = 0.05
    # 預設 0.00025 對應舊 deadband=0.5 kW @ rated=2000 kW 的行為；
    # 量測 noise 估計值較大時請用 measurement_noise_kw（取 max(ratio×rated, 3σ)）。
    deadband_ratio: float = 0.5 / 2000.0
    # 預設 0.02 = 2% — 小 setpoint 時用此值縮小 deadband 允許學習；
    # 0 = 停用（純 absolute deadband，回到 v0.8.0 行為）。
    deadband_setpoint_ratio: float = 0.02
    measurement_noise_kw: float | None = None
    power_bin_step_pct: int = 5
    steady_state_threshold: float = 0.02
    # 預設 1.5s = 5 cycles × 0.3s dt（舊 v0.7 行為）
    steady_state_seconds: float = 1.5
    settle_ratio: float = 0.15
    # 預設 0.6s = 2 cycles × 0.3s dt（舊 v0.7 行為）
    hold_seconds: float = 0.6
    # setpoint 變動視為「不變」的相對閾值 (佔 rated 的比例)；
    # 0.00005 = 0.005% 對應舊 v0.7 hardcoded 的 0.1 kW @ rated=2000 kW。
    setpoint_change_threshold_ratio: float = 0.1 / 2000.0
    ff_min: float = 0.8
    ff_max: float = 1.5
    error_ema_alpha: float = 0.0
    rate_limit: float | None = None
    measurement_key: str = "meter_power"
    persist_path: str = ""
    saturation_learn_min_cycles: int = 2
    saturation_learn_alpha: float = 0.5
    saturation_learn_max_step: float = 0.03


class PowerCompensator:
    """
    前饋 + 積分閉環功率補償器

    實作 CommandProcessor Protocol，可在 SystemControllerConfig 的
    post_protection_processors 中使用。

    command = ff(power_bin) × setpoint + Ki × ∫error·dt

    正功率（放電）：ff_output = ff × setpoint
    負功率（充電）：ff_output = setpoint / ff（補償輔電使電網讀數更負的效果）

    Usage::

        compensator = PowerCompensator(PowerCompensatorConfig(
            rated_power=2000.0,
            measurement_key="meter_power",
        ))

        # 作為 CommandProcessor
        config = SystemControllerConfig(
            post_protection_processors=[compensator],
        )

        # 或手動呼叫
        compensated_cmd = await compensator.process(command, context)
    """

    def __init__(
        self,
        config: PowerCompensatorConfig | None = None,
        repository: FFTableRepository | None = None,
    ) -> None:
        self._config = config or PowerCompensatorConfig()
        self._enabled = True

        # 預先計算 effective values（不依賴 dt 的部分；其餘在 compensate() 內按 dt 換算）
        self._effective_ki = self._compute_effective_ki()
        self._effective_deadband_kw = self._compute_effective_deadband()

        # Repository：優先使用注入的，否則從 config.persist_path 建立 JSON repo
        if repository is not None:
            self._repository: FFTableRepository | None = repository
        elif self._config.persist_path:
            self._repository = JsonFFTableRepository(self._config.persist_path, self._config.power_bin_step_pct)
        else:
            self._repository = None

        # FF 補償表：bin_index → ff_factor (初始 1.0)
        self._ff_table: dict[int, float] = self._build_initial_ff_table()
        self._load_ff_table()

        # 積分與濾波狀態
        self._integral: float = 0.0
        self._filtered_error: float = 0.0

        # 追蹤狀態
        self._last_setpoint: float = 0.0
        self._last_output: float = 0.0
        self._steady_count: int = 0
        self._integral_hold: int = 0
        self._settle_threshold: float = 0.0
        # 飽和脫離週期計數（v0.7.2 BUG-012）— 累積連續飽和週期，達到 min_cycles 後啟動飽和學習
        self._saturation_escape_count: int = 0

    # ─────────────────────── CommandProcessor Protocol ───────────────────────

    async def process(self, command: Command, context: StrategyContext) -> Command:
        """
        CommandProcessor.process() 實作

        從 context.extra 讀取量測值，計算補償後的功率指令。
        若補償器停用或無量測值，直接回傳原始 command。

        SEC-013a L4 防禦：measurement 為非有限值（NaN/Inf）時整體 bypass —
        不更新 _integral / _last_output / _filtered_error / FF table，
        避免 NaN 污染狀態後永久黏住。

        ``command.p_target`` 為 NO_CHANGE sentinel 時整體 bypass 補償邏輯並原封回傳，
        避免把 sentinel 餵進 FF 表或積分器。
        """
        if not self._enabled:
            return command

        # NO_CHANGE：策略不變更 P 軸，補償器亦不介入
        if is_no_change(command.p_target):
            return command

        # TypeGuard 收斂後 p_target 為 float
        p_setpoint: float = command.p_target
        measurement_key = self._config.measurement_key
        measurement = context.extra.get(measurement_key)
        if measurement is None:
            return command

        # SEC-013a L4：非有限 measurement 整體 bypass（比 EMA update 更前置）
        if is_non_finite_float(measurement):
            logger.debug(
                f"PowerCompensator: non-finite measurement {measurement!r}, bypass compensate to avoid state poisoning"
            )
            return command

        # 計算 dt（從 context.extra 取得，或預設 0.3s）
        dt = float(context.extra.get("dt", 0.3))

        compensated_p = self.compensate(
            setpoint=p_setpoint,
            measurement=float(measurement),
            dt=dt,
        )
        return command.with_p(compensated_p)

    # ─────────────────────── 核心演算法 ───────────────────────

    def compensate(self, setpoint: float, measurement: float, dt: float) -> float:
        """
        計算補償後的 PCS 功率指令

        Args:
            setpoint: 目標功率 (kW)，保護鏈輸出
            measurement: 電網端實際功率 (kW)
            dt: 距上次呼叫的時間間隔 (秒)

        Returns:
            補償後的 PCS 功率指令 (kW)
        """
        cfg = self._config

        # 零目標 → 直接輸出 0，重置積分
        if abs(setpoint) < 1e-6:
            self._integral = 0.0
            self._last_setpoint = 0.0
            self._last_output = 0.0
            self._steady_count = 0
            return 0.0

        # Per-call effective values（依 dt 換算 + per-setpoint 縮放）
        deadband_kw = self._effective_deadband_for_setpoint(setpoint)
        hold_cycles_needed = _cycles_from_seconds(cfg.hold_seconds, dt, floor=0)
        steady_cycles_needed = _cycles_from_seconds(cfg.steady_state_seconds, dt, floor=1)

        # 1. Setpoint 變動策略
        self._apply_setpoint_change_policy(setpoint, hold_cycles_needed)
        self._last_setpoint = setpoint

        # 2. 計算誤差
        error = setpoint - measurement

        # 3. 誤差濾波
        if cfg.error_ema_alpha > 0:
            self._filtered_error = cfg.error_ema_alpha * error + (1.0 - cfg.error_ema_alpha) * self._filtered_error
            filtered_error = self._filtered_error
        else:
            filtered_error = error

        # 4. 前饋查表（line interpolation across nearest bins，避免邊界 chatter）
        ff = self._get_ff(setpoint)
        if setpoint >= 0:
            ff_output = ff * setpoint
        else:
            ff_output = setpoint / ff if abs(ff) > 1e-6 else setpoint

        # 5. 飽和檢測（分方向，供 asymmetric anti-windup 使用）
        sat_high = ff_output >= cfg.output_max
        sat_low = ff_output <= cfg.output_min
        saturated = sat_high or sat_low

        # Asymmetric anti-windup（v0.7.2 BUG-012）：
        # - 飽和在上限 + error 為負（量測 > 目標）→ 朝脫離方向，允許累積負 integral 拉回
        # - 飽和在下限 + error 為正（量測 < 目標）→ 朝脫離方向，允許累積正 integral 拉回
        # - 非飽和 + 誤差超出死區 → 正常積分累積
        # - 飽和同向（誤差與飽和一致）→ 凍結積分以避免 windup
        can_integrate_high = sat_high and filtered_error < -deadband_kw
        can_integrate_low = sat_low and filtered_error > deadband_kw
        can_integrate_free = (not saturated) and abs(filtered_error) >= deadband_kw

        # 6. 積分更新
        if self._integral_hold > 0:
            if abs(filtered_error) <= self._settle_threshold:
                self._integral_hold -= 1
        elif can_integrate_high or can_integrate_low or can_integrate_free:
            self._integral += filtered_error * dt
            self._clamp_integral()

        # 7. 計算輸出
        output = ff_output + self._effective_ki * self._integral

        # 8. 輸出限幅
        output = clamp(output, cfg.output_min, cfg.output_max)

        # 9. 變化率限制（None = 不限，假設上游已 ramp）
        if cfg.rate_limit is not None and cfg.rate_limit > 0:
            max_delta = cfg.rate_limit * dt
            delta = output - self._last_output
            if abs(delta) > max_delta:
                output = self._last_output + math.copysign(max_delta, delta)

        # 10. 學習分支（飽和學習 與 穩態學習 互斥）
        if saturated:
            # 飽和（任一方向）→ 累積 escape 計數，達標後物理推算學習
            # 註：不論同向或異向飽和都學 FF — 同向飽和代表 PCS 已 clamp 仍不足，正是 FF 學歪的信號
            # 方向性保護仍由上面的 asymmetric anti-windup 確保（integral 不 windup）
            self._saturation_escape_count += 1
            if self._integral_hold == 0 and abs(setpoint) >= deadband_kw:
                self._learn_from_saturation(setpoint, measurement, sat_high, output)
            self._steady_count = 0
        else:
            # 非飽和 → 重置 escape 計數，走穩態學習
            self._saturation_escape_count = 0
            self._learn_if_steady(setpoint, filtered_error, deadband_kw, steady_cycles_needed)

        self._last_output = output
        return output

    # ─────────────────────── 公開介面 ───────────────────────

    def reset(self) -> None:
        """重置積分與追蹤狀態（保留 FF 補償表）"""
        self._integral = 0.0
        self._filtered_error = 0.0
        self._last_setpoint = 0.0
        self._last_output = 0.0
        self._steady_count = 0
        self._integral_hold = 0
        self._saturation_escape_count = 0

    def reset_ff_table(self) -> None:
        """重置 FF 補償表為全 1.0 並清除持久化"""
        self._ff_table = self._build_initial_ff_table()
        # 清除持久化
        if self._config.persist_path:
            try:
                Path(self._config.persist_path).unlink(missing_ok=True)
            except OSError:
                pass
        logger.info("FF table reset to defaults")

    def load_ff_table(self, table: dict[int, float]) -> None:
        """
        直接載入 FF Table（供外部校準使用）

        Args:
            table: {bin_index: ff_factor} 映射
        """
        loaded = 0
        for idx, ff in table.items():
            if idx in self._ff_table:
                self._ff_table[idx] = ff
                loaded += 1
        logger.info(f"FF table loaded externally ({loaded} bins)")

    def update_ff_bin(
        self,
        bin_idx: int,
        ff_ratio: float,
        *,
        persist: bool = False,
    ) -> None:
        """更新單一 FF bin 補償係數（公開 API，取代直接存取 ``_ff_table``）。

        超出 ``[ff_min, ff_max]`` 時會 clamp 後寫入並記錄 warning，與
        ``_learn_if_steady`` / ``_learn_from_saturation`` 的行為一致。

        Args:
            bin_idx: FF 表 bin 索引，必須存在於當前 FF 表（依 ``power_bin_step_pct`` 產生）。
            ff_ratio: 前饋補償係數，必須為有限且非負的浮點數。
            persist: 為 True 時在更新後立即持久化（委派 :meth:`persist_ff_table`）。

        Raises:
            TypeError: ``bin_idx`` 非 ``int``。
            ValueError: ``bin_idx`` 不在 FF 表、``ff_ratio`` 非有限值或為負值。

        Note:
            非 thread-safe — 呼叫端需自行保證序列化。
        """
        # bool 是 int 的子類，需顯式排除避免誤判
        if not isinstance(bin_idx, int) or isinstance(bin_idx, bool):
            raise TypeError(f"bin_idx 必須為 int，收到: {type(bin_idx).__name__}")

        if bin_idx not in self._ff_table:
            valid_min = min(self._ff_table)
            valid_max = max(self._ff_table)
            raise ValueError(f"bin_idx={bin_idx} 不在 FF 表中，有效範圍 [{valid_min}, {valid_max}]")

        if is_non_finite_float(ff_ratio):
            raise ValueError(f"ff_ratio 必須為有限浮點數，收到: {ff_ratio!r}")

        ff_ratio_f = float(ff_ratio)
        if ff_ratio_f < 0:
            raise ValueError(f"ff_ratio 必須 >= 0，收到: {ff_ratio_f}")

        cfg = self._config
        clamped = clamp(ff_ratio_f, cfg.ff_min, cfg.ff_max)
        if abs(clamped - ff_ratio_f) > 1e-9:
            logger.warning(
                f"update_ff_bin: bin[{bin_idx}] ff_ratio={ff_ratio_f:.4f} "
                f"超出 [{cfg.ff_min}, {cfg.ff_max}]，clamp 為 {clamped:.4f}"
            )

        self._ff_table[bin_idx] = clamped

        if persist:
            self.persist_ff_table()

    def persist_ff_table(self) -> None:
        """持久化當前 FF 表。

        若未配置 repository（None）則為 no-op，不拋例外。
        ``repository.save()`` 例外會被 log-swallow，呼叫端可安全呼叫。
        """
        self._save_ff_table()

    async def async_init(self) -> None:
        """
        Async 初始化 — 從 async repository（如 MongoDB）載入 FF Table

        JSON repository 在 __init__ 中同步載入，不需要呼叫此方法。
        MongoDB repository 必須在 event loop 啟動後呼叫此方法。

        SystemController._on_start() 會自動呼叫所有 CommandProcessor 的 async_init()。

        Usage::

            comp = PowerCompensator(config, repository=MongoFFTableRepository(collection))
            await comp.async_init()  # 從 MongoDB 載入 FF Table
        """
        if self._repository is None:
            return
        if hasattr(self._repository, "async_load"):
            table = await self._repository.async_load()
            if table:
                self.load_ff_table(table)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            self.reset()

    @property
    def diagnostics(self) -> dict:
        """診斷資訊（供 logging / API 使用）"""
        return {
            "enabled": self._enabled,
            "integral": round(self._integral, 4),
            "i_contribution": round(self._effective_ki * self._integral, 2),
            "effective_ki": round(self._effective_ki, 6),
            "effective_deadband_kw": round(self._effective_deadband_kw, 4),
            "effective_deadband_at_last_setpoint": round(self._effective_deadband_for_setpoint(self._last_setpoint), 4),
            "last_setpoint": round(self._last_setpoint, 1),
            "last_output": round(self._last_output, 1),
            "last_ff": round(self._get_ff(self._last_setpoint), 4),
            "steady_count": self._steady_count,
            "hold_remaining": self._integral_hold,
        }

    @property
    def ff_table(self) -> dict[int, float]:
        """FF 補償表的淺拷貝"""
        return dict(self._ff_table)

    # ─────────────────────── 內部方法 ───────────────────────

    def _compute_effective_ki(self) -> float:
        """由 integral_time_seconds 推算等效 Ki。

        物理推導：對 error = rated_power 持續，I 累積率 = rated × ki / s。
        要求在 ``integral_time_seconds`` 秒內 I 貢獻打滿 ``integral_max_ratio × rated``：

            ki × rated × T = integral_max_ratio × rated
            → ki = integral_max_ratio / T

        ``integral_time_seconds`` 為 ``None`` / ``0`` / 負值 → 回傳 0（停用 I）。
        負值不 raise，silently 視為停用，跟其他 disable-via-sentinel 參數一致。
        """
        t = self._config.integral_time_seconds
        if t is None or t <= 0:
            return 0.0
        return self._config.integral_max_ratio / t

    def _compute_effective_deadband(self) -> float:
        """由 deadband_ratio 與 measurement_noise_kw 推算 effective 死區 (kW)。

        - 純 ratio: ``deadband = deadband_ratio × rated_power``
        - 有 noise 估計時取較大者: ``max(deadband_ratio × rated, 3σ)``，
          確保死區至少能蓋過 3σ noise，避免 I 在量測雜訊上空積分。

        ``measurement_noise_kw`` 為 ``None`` / ``0`` / 負值 → 純走 ratio。
        負值不 raise，silently fallback 跟 integral_time_seconds 一致。

        Note: 此為「絕對下限」，不隨 setpoint 變動。Per-call 的 effective
        deadband 走 :meth:`_effective_deadband_for_setpoint`，會再依 setpoint
        相對縮放但不低於本函式回傳的 noise floor。
        """
        cfg = self._config
        ratio_kw = cfg.deadband_ratio * cfg.rated_power
        if cfg.measurement_noise_kw is None or cfg.measurement_noise_kw <= 0:
            return ratio_kw
        return max(ratio_kw, _NOISE_SIGMA_MULTIPLIER * cfg.measurement_noise_kw)

    def _effective_deadband_for_setpoint(self, setpoint: float) -> float:
        """Per-setpoint effective deadband (kW)。

        修復「小 setpoint × plant_loss < 固定 deadband」造成積分閘門 + 學習閘門
        雙重鎖死 FF 學習」的問題。

        公式：
            effective = max(noise_floor, min(absolute_deadband, |setpoint| × ratio))

        其中：
            - absolute_deadband = ``self._effective_deadband_kw``（noise-aware）
            - noise_floor = ``3σ`` 若有 measurement_noise_kw，否則 0
            - ratio = ``cfg.deadband_setpoint_ratio``；``<= 0`` 時純回 absolute

        Rationale:
            - 大 setpoint (|setpoint| × ratio > absolute) → 回 absolute，等同原行為
            - 小 setpoint → 縮小 deadband 允許 I 累積與學習
            - noise_floor 永遠是下限，避免在量測雜訊上空積分
        """
        cfg = self._config
        absolute = self._effective_deadband_kw
        ratio = cfg.deadband_setpoint_ratio
        if ratio <= 0:
            return absolute
        relative = abs(setpoint) * ratio
        candidate = min(absolute, relative)
        # 重新計算 noise floor（_effective_deadband_kw 已 fold 進 noise，但取 min
        # 時可能跌破）— 顯式取 max 確保 floor。
        if cfg.measurement_noise_kw is not None and cfg.measurement_noise_kw > 0:
            return max(candidate, _NOISE_SIGMA_MULTIPLIER * cfg.measurement_noise_kw)
        return candidate

    def _build_initial_ff_table(self) -> dict[int, float]:
        step = self._config.power_bin_step_pct
        if step <= 0:
            step = 10
        n_bins = 100 // step
        return {i: 1.0 for i in range(-n_bins, n_bins + 1)}

    def _get_bin_index(self, power_kw: float) -> int:
        cfg = self._config
        pct = power_kw / cfg.rated_power * 100.0
        idx = round(pct / cfg.power_bin_step_pct)
        n_bins = 100 // cfg.power_bin_step_pct
        return int(clamp(idx, -n_bins, n_bins))

    def _get_ff(self, setpoint: float) -> float:
        """查表取 FF 係數，跨 bin 邊界做線性插值。

        Bin 學習仍走 `_get_bin_index` 的 round 取單一 bin（學習資料 attribute
        到最近的 bin），但讀取時插值能避免量測雜訊把 setpoint 推過 bin 邊界
        造成 ff_output step 跳變導致的 chatter；同時跟 `_load_ff_table`
        遷移時的線性插值行為一致。
        """
        cfg = self._config
        pct = setpoint / cfg.rated_power * 100.0
        pos = pct / cfg.power_bin_step_pct
        n_bins = 100 // cfg.power_bin_step_pct

        lo = math.floor(pos)
        hi = math.ceil(pos)
        lo = int(clamp(lo, -n_bins, n_bins))
        hi = int(clamp(hi, -n_bins, n_bins))
        if lo == hi:
            return self._ff_table.get(lo, 1.0)
        frac = pos - lo
        ff_lo = self._ff_table.get(lo, 1.0)
        ff_hi = self._ff_table.get(hi, 1.0)
        return ff_lo * (1.0 - frac) + ff_hi * frac

    def _apply_setpoint_change_policy(self, new_setpoint: float, hold_cycles_needed: int) -> None:
        cfg = self._config
        old = self._last_setpoint
        change_threshold_kw = cfg.setpoint_change_threshold_ratio * cfg.rated_power
        if abs(new_setpoint - old) < change_threshold_kw:
            return
        self._integral = 0.0
        self._steady_count = 0
        self._integral_hold = hold_cycles_needed
        self._settle_threshold = abs(new_setpoint - old) * cfg.settle_ratio
        self._inherit_ff(old, new_setpoint)

    def _inherit_ff(self, old_setpoint: float, new_setpoint: float) -> None:
        # 設計對齊：FF 表的「寫入」路徑（learning + inherit）一律走 _get_bin_index
        # 的 round 取單一 bin；只有 runtime 讀取（_get_ff）才做相鄰 bin 線性插值。
        # 這讓學習資料的 sharpness 不被插值稀釋，但讀取時跨邊界平滑不會 chatter。
        # 若未來改一邊請保持這個非對稱性。
        old_idx = self._get_bin_index(old_setpoint)
        new_idx = self._get_bin_index(new_setpoint)
        if old_idx == new_idx:
            return
        old_ff = self._ff_table.get(old_idx, 1.0)
        new_ff = self._ff_table.get(new_idx, 1.0)
        if abs(new_ff - 1.0) < 1e-6 and abs(old_ff - 1.0) > 1e-6:
            self._ff_table[new_idx] = old_ff
            logger.debug(f"FF inherit: bin[{old_idx}] → bin[{new_idx}], ff={old_ff:.4f}")

    def _clamp_integral(self) -> None:
        cfg = self._config
        if self._effective_ki == 0:
            return
        max_contribution = cfg.integral_max_ratio * cfg.rated_power
        integral_max = max_contribution / self._effective_ki
        self._integral = clamp(self._integral, -integral_max, integral_max)

    def _learn_if_steady(
        self,
        setpoint: float,
        filtered_error: float,
        deadband_kw: float,
        cycles_needed: int,
    ) -> None:
        cfg = self._config
        # BUG-002 guard：deadband=0 時 `abs(setpoint) < 0` 永遠 False，
        # 若 setpoint=0 會在後面的 `filtered_error / setpoint` 除以零。
        # 用 max(deadband_kw, 1e-6) 作為底線，確保零 setpoint 一定被攔截。
        if abs(setpoint) < max(deadband_kw, 1e-6):
            self._steady_count = 0
            return

        # 穩態相對門檻 + absolute floor 對齊 deadband：誤差小於 deadband 不應
        # 同時被「視為穩態可學」與「太小不積分」兩種規則矛盾處理。
        threshold_kw = max(cfg.steady_state_threshold * abs(setpoint), deadband_kw)
        if abs(filtered_error) < threshold_kw:
            self._steady_count += 1
        else:
            self._steady_count = 0
            return

        if self._steady_count < cycles_needed:
            return

        i_term = self._effective_ki * self._integral
        if abs(i_term) < deadband_kw:
            self._steady_count = 0
            return

        idx = self._get_bin_index(setpoint)
        old_ff = self._ff_table.get(idx, 1.0)
        if setpoint >= 0:
            new_ff = (old_ff * setpoint + i_term) / setpoint
        else:
            denom = setpoint / old_ff + i_term
            new_ff = setpoint / denom if abs(denom) > 1e-6 else old_ff

        new_ff = clamp(new_ff, cfg.ff_min, cfg.ff_max)

        if abs(new_ff - old_ff) > 1e-6:
            self._ff_table[idx] = new_ff
            self._integral = 0.0
            logger.debug(f"FF learn: bin[{idx}]({idx * cfg.power_bin_step_pct}%) ff: {old_ff:.4f} → {new_ff:.4f}")
            self._save_ff_table()

        self._steady_count = 0

    def _learn_from_saturation(self, setpoint: float, measurement: float, sat_high: bool, output: float) -> None:
        """飽和學習：飽和期間用物理量直接推算 FF 係數（v0.7.2 BUG-012）。

        與 ``_learn_if_steady`` 的差異：
        - 穩態學習：需要非飽和 + 積分累積 + 連續 steady_count 達標
        - 飽和學習：只要連續飽和 min_cycles，直接用「實際輸出 / 電網讀數」一步到位

        物理推導（用當下實際 PCS 命令 output，含 integral 修正）：
        - 放電飽和（sat_high, setpoint > 0）：PCS 實出 output，電網讀到 measurement。
          觀察 β = measurement / output，要讓下次 grid = setpoint 需 PCS 出 setpoint / β。
          對應 ``ff × setpoint = setpoint / β`` → ``new_ff = output / measurement``
        - 充電飽和（sat_low, setpoint < 0）：PCS 實出 output（負），measurement（負）。
          對應 ``setpoint / ff = setpoint / β`` → ``new_ff = measurement / output``

        Args:
            setpoint: 目標功率 (kW)
            measurement: 電網端實際功率 (kW)
            sat_high: True 表示飽和在上限（放電），False 表示飽和在下限（充電）
            output: 當下實際送給 PCS 的指令（已 clamp，含 integral 修正）
        """
        cfg = self._config

        # 1. min_cycles 閘門：連續飽和週期數不足，不學
        if self._saturation_escape_count < cfg.saturation_learn_min_cycles:
            return

        # 2. measurement 有效性
        if not math.isfinite(measurement):
            return
        # 避免 measurement 過小（接近零）導致物理推算失真或除零
        if abs(measurement) < max(self._effective_deadband_kw, 1.0):
            return

        # 3. 符號一致性：PCS 指令方向與電錶讀數異號 → 線路接反或量測異常，不學
        if sat_high and measurement <= 0:
            return
        if (not sat_high) and measurement >= 0:
            return

        # 4. 物理推算（用當下實際 output，非 output_max，以反映 integral 修正後的真實命令）
        idx = self._get_bin_index(setpoint)
        old_ff = self._ff_table.get(idx, 1.0)
        # 避免 output 過小導致除零或失真
        if abs(output) < max(self._effective_deadband_kw, 1.0):
            return
        if sat_high:
            new_ff_physical = output / measurement
        else:
            new_ff_physical = measurement / output

        # 5. EMA 平滑（α 靠近 1 時快速採用物理值、靠近 0 時保留舊值）
        new_ff = cfg.saturation_learn_alpha * new_ff_physical + (1.0 - cfg.saturation_learn_alpha) * old_ff

        # 6. 單次變動量 clamp（避免單步衝擊過大）
        max_step = cfg.saturation_learn_max_step
        new_ff = clamp(new_ff, old_ff - max_step, old_ff + max_step)

        # 7. ff_min / ff_max 全域 clamp
        new_ff = clamp(new_ff, cfg.ff_min, cfg.ff_max)

        # 8. 更新 FF 表並持久化（只在值確實變動時才寫）
        if abs(new_ff - old_ff) > 1e-6:
            self._ff_table[idx] = new_ff
            logger.debug(
                f"FF sat-learn: bin[{idx}]({idx * cfg.power_bin_step_pct}%) "
                f"ff: {old_ff:.4f} → {new_ff:.4f} (meas={measurement:.1f})"
            )
            self._save_ff_table()

    # ─────────────────────── 持久化 ───────────────────────

    def _save_ff_table(self) -> None:
        """透過 repository 儲存 FF Table"""
        if self._repository is None:
            return
        try:
            self._repository.save(dict(self._ff_table))
        except Exception:
            logger.opt(exception=True).warning("PowerCompensator: failed to save FF table")

    def _load_ff_table(self) -> None:
        """透過 repository 載入 FF Table（含 step 遷移）"""
        if self._repository is None:
            return
        data = self._repository.load()
        if not data:
            return

        file_max_idx = max(abs(i) for i in data.keys()) if data else 0
        cur_n_bins = 100 // self._config.power_bin_step_pct

        if file_max_idx != cur_n_bins and file_max_idx > 0:
            # step 不同 → 線性插值遷移
            old_step_pct = 100 // file_max_idx
            ratio = old_step_pct / self._config.power_bin_step_pct
            migrated = 0
            for new_idx in self._ff_table:
                old_pos = new_idx / ratio
                lo = math.floor(old_pos)
                hi = math.ceil(old_pos)
                if lo == hi:
                    if lo in data:
                        self._ff_table[new_idx] = data[lo]
                        migrated += 1
                elif lo in data and hi in data:
                    frac = old_pos - lo
                    self._ff_table[new_idx] = data[lo] * (1 - frac) + data[hi] * frac
                    migrated += 1
            logger.info(
                f"FF table migrated: old step={old_step_pct}% → new step={self._config.power_bin_step_pct}%, "
                f"interpolated {migrated} bins"
            )
            self._save_ff_table()
        else:
            loaded = 0
            for idx, ff in data.items():
                if idx in self._ff_table:
                    self._ff_table[idx] = ff
                    loaded += 1
            logger.info(f"FF table loaded ({loaded} bins)")


__all__ = [
    "FFTableRepository",
    "JsonFFTableRepository",
    "MongoFFTableRepository",
    "PowerCompensator",
    "PowerCompensatorConfig",
]
