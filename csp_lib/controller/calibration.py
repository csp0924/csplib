# =============== FF Table Calibration Strategy ===============
#
# 維護型一次性操作：步階校準 PowerCompensator 的 FF Table
#
# 流程：遍歷各功率 bin → 輸出功率指令 → 等穩態 → 記錄 ff_ratio → 下一個 bin
# 完成後寫入 compensator FF Table，觸發 on_complete callback。
#
# 透過 ModeManager.push_override() 啟動，完成後 pop 回正常模式。
# 觸發來源不限：RuntimeParameters、Redis channel、Modbus HR 均可。

from __future__ import annotations

import enum
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from csp_lib.controller.core import Command, ConfigMixin, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.core import get_logger

if TYPE_CHECKING:
    from csp_lib.controller.compensator import PowerCompensator

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FFCalibrationConfig(ConfigMixin):
    """
    FF Table 步階校準配置

    Attributes:
        step_pct: 每步幅度（% of rated power）
        min_pct: 最小校準百分比（負值 = 充電側）
        max_pct: 最大校準百分比
        skip_zero: 是否跳過 0% bin
        steady_threshold: 穩態門檻 |error/setpoint|
        steady_cycles: 連續穩態週期數，達標後記錄 FF
        settle_wait_cycles: 切 bin 後跳過 N 個週期再開始判穩態
        measurement_key: context.extra 中量測值的 key
        interval: 執行週期（秒）
    """

    step_pct: int = 5
    min_pct: int = -100
    max_pct: int = 100
    skip_zero: bool = True
    steady_threshold: float = 0.02
    steady_cycles: int = 10
    settle_wait_cycles: int = 5
    measurement_key: str = "meter_power"
    interval: float = 0.3

    def validate(self) -> None:
        if self.step_pct <= 0:
            raise ValueError("step_pct must be positive")
        if self.min_pct > self.max_pct:
            raise ValueError("min_pct must be <= max_pct")
        if self.steady_cycles <= 0:
            raise ValueError("steady_cycles must be positive")


class _CalibrationState(enum.Enum):
    IDLE = "idle"
    STEPPING = "stepping"
    DONE = "done"


class FFCalibrationStrategy(Strategy):
    """
    FF Table 步階校準策略（維護型一次性操作）

    遍歷各功率 bin，在每個 bin：
    1. 輸出對應功率指令（PCS 接收到實際功率）
    2. 等穩態（量測值與 setpoint 的偏差 < threshold）
    3. 計算 ff_ratio 並記錄
    4. 切到下一個 bin

    完成後寫入 compensator FF Table 並觸發 on_complete callback。

    觸發方式：透過 ModeManager.push_override() 啟動，
    on_complete callback 中呼叫 pop_override() 回到正常模式。

    Usage::

        cal = FFCalibrationStrategy(
            config=FFCalibrationConfig(step_pct=5, steady_cycles=10),
            compensator=compensator,
            rated_power=2000.0,
            on_complete=handle_done,
        )
        controller.register_mode("ff_cal", cal, ModePriority.MANUAL)
        # 觸發: await controller.push_override("ff_cal")
    """

    def __init__(
        self,
        config: FFCalibrationConfig | None = None,
        compensator: PowerCompensator | None = None,
        rated_power: float = 0.0,
        on_complete: Callable[[dict[int, float]], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config or FFCalibrationConfig()
        self._compensator = compensator
        self._rated_power = rated_power
        self._on_complete = on_complete

        # 狀態
        self._state = _CalibrationState.IDLE
        self._bin_sequence: list[int] = []
        self._bin_index: int = 0
        self._results: dict[int, float] = {}

        # 當前 bin 的追蹤
        self._steady_count: int = 0
        self._settle_remaining: int = 0
        self._measurement_sum: float = 0.0
        self._measurement_count: int = 0

    # ─────────────────────── Strategy interface ───────────────────────

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=max(1, int(self._config.interval)))

    def execute(self, context: StrategyContext) -> Command:
        """狀態機：IDLE → STEPPING → DONE"""
        if self._state == _CalibrationState.IDLE:
            return context.last_command

        if self._state == _CalibrationState.DONE:
            return Command(p_target=0.0, q_target=0.0)

        # ── STEPPING ──
        cfg = self._config
        current_bin = self._bin_sequence[self._bin_index]
        rated = self._rated_power or (context.system_base.p_base if context.system_base else 0.0)
        if rated <= 0:
            logger.warning("FFCalibration: rated_power is 0, cannot calibrate")
            return context.last_command

        setpoint = rated * current_bin * cfg.step_pct / 100.0

        # 讀取量測值
        measurement = context.extra.get(cfg.measurement_key)
        if measurement is None:
            return Command(p_target=setpoint, q_target=0.0)

        measurement = float(measurement)

        # settle 期間：跳過，不判穩態
        if self._settle_remaining > 0:
            self._settle_remaining -= 1
            return Command(p_target=setpoint, q_target=0.0)

        # 判斷穩態
        error = setpoint - measurement
        if abs(setpoint) > 1e-6:
            relative_error = abs(error / setpoint)
        else:
            relative_error = abs(error)

        if relative_error < cfg.steady_threshold:
            self._steady_count += 1
            self._measurement_sum += measurement
            self._measurement_count += 1
        else:
            self._steady_count = 0
            self._measurement_sum = 0.0
            self._measurement_count = 0

        # 穩態達標 → 記錄 FF ratio → 下一個 bin
        if self._steady_count >= cfg.steady_cycles:
            avg_measurement = self._measurement_sum / self._measurement_count
            if abs(avg_measurement) > 1e-6:
                ff_ratio = setpoint / avg_measurement
            else:
                ff_ratio = 1.0

            # Clamp FF ratio to reasonable range
            ff_ratio = max(0.8, min(ff_ratio, 1.5))
            self._results[current_bin] = ff_ratio

            logger.info(
                f"FFCalibration: bin[{current_bin}] ({current_bin * cfg.step_pct}%) "
                f"setpoint={setpoint:.1f}kW measurement={avg_measurement:.1f}kW ff={ff_ratio:.4f}"
            )

            # 下一個 bin
            self._bin_index += 1
            self._steady_count = 0
            self._settle_remaining = cfg.settle_wait_cycles
            self._measurement_sum = 0.0
            self._measurement_count = 0

            if self._bin_index >= len(self._bin_sequence):
                self._finish()
                return Command(p_target=0.0, q_target=0.0)

        return Command(p_target=setpoint, q_target=0.0)

    async def on_activate(self) -> None:
        """開始校準"""
        self._build_bin_sequence()
        self._bin_index = 0
        self._results = {}
        self._steady_count = 0
        self._settle_remaining = self._config.settle_wait_cycles
        self._measurement_sum = 0.0
        self._measurement_count = 0
        self._state = _CalibrationState.STEPPING

        logger.info(
            f"FFCalibration started: {len(self._bin_sequence)} bins, "
            f"step={self._config.step_pct}%, range=[{self._config.min_pct}%, {self._config.max_pct}%]"
        )

    async def on_deactivate(self) -> None:
        """校準被中斷或完成"""
        if self._state == _CalibrationState.STEPPING:
            logger.warning(
                f"FFCalibration interrupted at bin {self._bin_index}/{len(self._bin_sequence)}, FF table NOT updated"
            )
        self._state = _CalibrationState.IDLE

    # ─────────────────────── 公開屬性 ───────────────────────

    @property
    def state(self) -> str:
        """目前狀態"""
        return self._state.value

    @property
    def progress(self) -> dict:
        """校準進度"""
        return {
            "state": self._state.value,
            "current_bin": self._bin_sequence[self._bin_index] if self._bin_index < len(self._bin_sequence) else None,
            "total_bins": len(self._bin_sequence),
            "completed_bins": len(self._results),
            "steady_count": self._steady_count,
            "results": dict(self._results),
        }

    @property
    def results(self) -> dict[int, float]:
        """校準結果 {bin_index: ff_ratio}"""
        return dict(self._results)

    # ─────────────────────── 內部 ───────────────────────

    def _build_bin_sequence(self) -> None:
        """建立校準 bin 序列"""
        cfg = self._config
        step = cfg.step_pct
        n_bins = 100 // step

        # 正功率 bins: 1, 2, ..., max_pct/step
        # 負功率 bins: -1, -2, ..., min_pct/step
        bins: list[int] = []
        max_bin = min(n_bins, cfg.max_pct // step)
        min_bin = max(-n_bins, cfg.min_pct // step)

        # 正功率先（從小到大）
        for i in range(1 if cfg.skip_zero else 0, max_bin + 1):
            bins.append(i)
        # 負功率（從 -1 到最小）
        for i in range(-1, min_bin - 1, -1):
            bins.append(i)

        self._bin_sequence = bins

    def _finish(self) -> None:
        """校準完成：寫入 FF Table"""
        self._state = _CalibrationState.DONE

        if self._compensator is not None and self._results:
            updated = 0
            for bin_idx, ff_ratio in self._results.items():
                try:
                    self._compensator.update_ff_bin(bin_idx, ff_ratio, persist=False)
                    updated += 1
                except (ValueError, TypeError) as e:
                    logger.warning(f"FFCalibration: skip invalid bin[{bin_idx}]={ff_ratio}: {e}")
            self._compensator.persist_ff_table()
            logger.info(f"FFCalibration: updated {updated} bins in compensator FF table")

        logger.info(f"FFCalibration complete: {len(self._results)} bins calibrated")

        # 觸發 callback
        if self._on_complete is not None:
            import asyncio

            try:
                asyncio.ensure_future(self._on_complete(dict(self._results)))
            except RuntimeError:
                logger.warning("FFCalibration: no running event loop for on_complete callback")

    def __str__(self) -> str:
        return (
            f"FFCalibrationStrategy(step={self._config.step_pct}%, "
            f"range=[{self._config.min_pct}%, {self._config.max_pct}%], "
            f"state={self._state.value})"
        )


__all__ = [
    "FFCalibrationConfig",
    "FFCalibrationStrategy",
]
