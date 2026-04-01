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

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.core import get_logger

logger = get_logger(__name__)


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


@dataclass
class PowerCompensatorConfig:
    """
    功率補償器配置

    Attributes:
        rated_power: 系統額定功率 (kW)
        output_min: 輸出下限 (kW)
        output_max: 輸出上限 (kW)
        ki: 積分增益 (1/s)
        integral_max_ratio: I 項最大貢獻 = ratio × rated_power
        deadband: 死區 (kW)，誤差低於此值不累積 I
        power_bin_step_pct: FF 表功率區間寬度 (% of rated)
        steady_state_threshold: 穩態門檻 |error/setpoint|
        steady_state_cycles: 連續穩態週期數，達標後觸發 FF 學習
        settle_ratio: 暫態閘門比例，setpoint 變更後 |error| > 變化量 × settle_ratio 時不倒數
        hold_cycles: setpoint 變更後暫停積分的週期數
        ff_min: FF 補償係數下限
        ff_max: FF 補償係數上限
        error_ema_alpha: 誤差 EMA 濾波係數 (0=停用)
        rate_limit: 輸出變化率限制 (kW/s, 0=停用)
        measurement_key: context.extra 中量測值的 key
        persist_path: FF 表持久化路徑 (空=不持久化)
    """

    rated_power: float = 2000.0
    output_min: float = -2000.0
    output_max: float = 2000.0
    ki: float = 0.3
    integral_max_ratio: float = 0.05
    deadband: float = 0.5
    power_bin_step_pct: int = 5
    steady_state_threshold: float = 0.02
    steady_state_cycles: int = 5
    settle_ratio: float = 0.15
    hold_cycles: int = 2
    ff_min: float = 0.8
    ff_max: float = 1.5
    error_ema_alpha: float = 0.0
    rate_limit: float = 0.0
    measurement_key: str = "meter_power"
    persist_path: str = ""


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

    # ─────────────────────── CommandProcessor Protocol ───────────────────────

    async def process(self, command: Command, context: StrategyContext) -> Command:
        """
        CommandProcessor.process() 實作

        從 context.extra 讀取量測值，計算補償後的功率指令。
        若補償器停用或無量測值，直接回傳原始 command。
        """
        if not self._enabled:
            return command

        measurement_key = self._config.measurement_key
        measurement = context.extra.get(measurement_key)
        if measurement is None:
            return command

        # 計算 dt（從 context.extra 取得，或預設 0.3s）
        dt = float(context.extra.get("dt", 0.3))

        compensated_p = self.compensate(
            setpoint=command.p_target,
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

        # 1. Setpoint 變動策略
        self._apply_setpoint_change_policy(setpoint)
        self._last_setpoint = setpoint

        # 2. 計算誤差
        error = setpoint - measurement

        # 3. 誤差濾波
        if cfg.error_ema_alpha > 0:
            self._filtered_error = cfg.error_ema_alpha * error + (1.0 - cfg.error_ema_alpha) * self._filtered_error
            filtered_error = self._filtered_error
        else:
            filtered_error = error

        # 4. 前饋查表
        ff = self._get_ff(setpoint)
        if setpoint >= 0:
            ff_output = ff * setpoint
        else:
            ff_output = setpoint / ff if abs(ff) > 1e-6 else setpoint

        # 5. 飽和檢測
        saturated = ff_output >= cfg.output_max or ff_output <= cfg.output_min

        # 6. 積分更新
        if saturated:
            self._integral = 0.0
        elif self._integral_hold > 0:
            if abs(filtered_error) <= self._settle_threshold:
                self._integral_hold -= 1
        elif abs(filtered_error) >= cfg.deadband:
            self._integral += filtered_error * dt
            self._clamp_integral()

        # 7. 計算輸出
        output = ff_output + cfg.ki * self._integral

        # 8. 輸出限幅
        output = max(cfg.output_min, min(output, cfg.output_max))

        # 9. 變化率限制
        if cfg.rate_limit > 0:
            max_delta = cfg.rate_limit * dt
            delta = output - self._last_output
            if abs(delta) > max_delta:
                output = self._last_output + math.copysign(max_delta, delta)

        # 10. 穩態學習
        if not saturated:
            self._learn_if_steady(setpoint, filtered_error)

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
        cfg = self._config
        return {
            "enabled": self._enabled,
            "integral": round(self._integral, 4),
            "i_contribution": round(cfg.ki * self._integral, 2),
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
        return max(-n_bins, min(idx, n_bins))

    def _get_ff(self, setpoint: float) -> float:
        idx = self._get_bin_index(setpoint)
        return self._ff_table.get(idx, 1.0)

    def _apply_setpoint_change_policy(self, new_setpoint: float) -> None:
        old = self._last_setpoint
        if abs(new_setpoint - old) < 0.1:
            return
        self._integral = 0.0
        self._steady_count = 0
        self._integral_hold = self._config.hold_cycles
        self._settle_threshold = abs(new_setpoint - old) * self._config.settle_ratio
        self._inherit_ff(old, new_setpoint)

    def _inherit_ff(self, old_setpoint: float, new_setpoint: float) -> None:
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
        if cfg.ki == 0:
            return
        max_contribution = cfg.integral_max_ratio * cfg.rated_power
        integral_max = max_contribution / cfg.ki
        self._integral = max(-integral_max, min(self._integral, integral_max))

    def _learn_if_steady(self, setpoint: float, filtered_error: float) -> None:
        cfg = self._config
        if abs(setpoint) < cfg.deadband:
            self._steady_count = 0
            return

        relative_error = abs(filtered_error / setpoint)
        if relative_error < cfg.steady_state_threshold:
            self._steady_count += 1
        else:
            self._steady_count = 0
            return

        if self._steady_count < cfg.steady_state_cycles:
            return

        i_term = cfg.ki * self._integral
        if abs(i_term) < cfg.deadband:
            self._steady_count = 0
            return

        idx = self._get_bin_index(setpoint)
        old_ff = self._ff_table.get(idx, 1.0)
        if setpoint >= 0:
            new_ff = (old_ff * setpoint + i_term) / setpoint
        else:
            denom = setpoint / old_ff + i_term
            new_ff = setpoint / denom if abs(denom) > 1e-6 else old_ff

        new_ff = max(cfg.ff_min, min(new_ff, cfg.ff_max))

        if abs(new_ff - old_ff) > 1e-6:
            self._ff_table[idx] = new_ff
            self._integral = 0.0
            logger.debug(f"FF learn: bin[{idx}]({idx * cfg.power_bin_step_pct}%) ff: {old_ff:.4f} → {new_ff:.4f}")
            self._save_ff_table()

        self._steady_count = 0

    # ─────────────────────── 持久化 ───────────────────────

    def _save_ff_table(self) -> None:
        """透過 repository 儲存 FF Table"""
        if self._repository is None:
            return
        self._repository.save(dict(self._ff_table))

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
