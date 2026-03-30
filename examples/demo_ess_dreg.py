"""
Demonstrates:
  - DroopStrategy: Droop 一次調頻（排程功率 + 頻率響應）
  - RuntimeParameters: 即時參數容器（EMS 指令同步）
  - DynamicSOCProtection: 動態 SOC 上下限保護
  - GridLimitProtection: 電力公司輸出限制
  - RampStopStrategy: 故障時斜坡降功率（Strategy 而非 Protection）
  - PowerCompensator: FF + I 閉環功率補償（CommandProcessor pipeline）
  - SOCBalancingDistributor: SOC 平衡分配 + 硬體限制 + 溢出轉移
  - FFCalibrationStrategy: FF Table 自動校準（維護型觸發）
  - SystemControllerConfig.builder(): Fluent builder

Scenario:
  模擬 2MW ESS（2×1000kW PCS），對接 EMS 的完整控制流程：
    1. EMS 排程 500kW + 調頻疊加 → 533kW
    2. 保護鏈：DynamicSOC 通過, GridLimit(80%) 通過
    3. 功率補償修正 PCS 非線性
    4. EMS 改排程 1500kW + 限制降為 50% → GridLimit clamp 到 1000kW
    5. 故障觸發 → RampStopStrategy 逐步降至 0（不是直接歸零）
    6. 觸發 FF Table 校準
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from csp_lib.controller.calibration import FFCalibrationConfig, FFCalibrationStrategy
from csp_lib.controller.compensator import PowerCompensator, PowerCompensatorConfig
from csp_lib.controller.core import Command
from csp_lib.controller.strategies import DroopConfig, DroopStrategy, RampStopStrategy
from csp_lib.controller.system import (
    DynamicSOCProtection,
    GridLimitProtection,
    ModePriority,
)
from csp_lib.core import RuntimeParameters, get_logger, set_level
from csp_lib.integration import (
    DeviceRegistry,
    SystemController,
    SystemControllerConfig,
)
from csp_lib.integration.distributor import SOCBalancingDistributor

logger = get_logger("demo")
set_level("INFO")

# ─────────────────────── Mock 設備 ───────────────────────


def _make_device(device_id: str, soc: float = 50.0, p: float = 0.0, frequency: float = 60.0) -> MagicMock:
    """建立 mock AsyncModbusDevice"""
    dev = MagicMock()
    dev.device_id = device_id
    type(dev).is_responsive = PropertyMock(return_value=True)
    type(dev).is_protected = PropertyMock(return_value=False)
    type(dev).is_connected = PropertyMock(return_value=True)
    dev.latest_values = {"p": p, "soc_system": soc, "f": frequency}
    dev.write_point = AsyncMock()
    dev.capabilities = {}
    dev.health = MagicMock(return_value=MagicMock(status=MagicMock(value="healthy")))
    return dev


# ─────────────────────── Demo ───────────────────────


async def demo():
    logger.info("=" * 60)
    logger.info("  Japan ESS Grid Controller Demo (csp_lib 新功能)")
    logger.info("=" * 60)

    # ── 1. RuntimeParameters ──

    params = RuntimeParameters(
        p_command_grid=500,
        p_command_select=1,
        afc_enable=1,
        afc_p_base=1000,
        soc_max=95.0,
        soc_min=5.0,
        grid_limit_pct=80,
        battery_status=0,
        ramp_rate=5.0,
        calibration_trigger=0,
    )
    logger.info(f"[1] RuntimeParameters: {params}")

    # ── 2. Mock 設備 ──

    pcs1 = _make_device("PCS1", soc=75.0, p=200.0)
    pcs2 = _make_device("PCS2", soc=65.0, p=200.0)
    meter = _make_device("MTD1", frequency=59.95)
    grid_meter = _make_device("MM1R", p=-400.0)

    registry = DeviceRegistry()
    for dev, traits in [(pcs1, ["pcs"]), (pcs2, ["pcs"]), (meter, ["meter"]), (grid_meter, ["grid_meter"])]:
        registry.register(dev, traits=traits)

    logger.info("[2] 設備: PCS1(SOC=75%), PCS2(SOC=65%), MTD1(f=59.95Hz), MM1R(p=-400kW)")

    # ── 3. DroopStrategy ──

    droop = DroopStrategy(DroopConfig(f_base=60.0, droop=0.05, deadband=0.01, rated_power=2000.0))
    logger.info("[3] DroopStrategy: f_base=60Hz, droop=5%, deadband=0.01Hz")

    # ── 4. 保護規則（只放 clamp 型，RampStop 改用 Strategy）──

    compensator = PowerCompensator(PowerCompensatorConfig(
        rated_power=2000.0, output_min=-2200.0, output_max=2200.0,
        ki=0.3, deadband=0.5, measurement_key="meter_power",
    ))

    # ── 5. Builder 建構 config ──

    config = (
        SystemControllerConfig.builder()
        .system_base(p_base=2000.0)
        .map_context(point_name="f", target="extra.frequency", device_id="MTD1", default=60.0)
        .map_context(point_name="p", target="extra.meter_power", device_id="MM1R", default=0.0)
        .map_context(point_name="soc_system", target="soc", trait="pcs")
        .protect(DynamicSOCProtection(params))
        .protect(GridLimitProtection(params, total_rated_kw=2000.0))
        .processor(compensator)
        .auto_stop(enabled=False)
        .params(params)
        .build()
    )

    controller = SystemController(registry, config)
    controller.register_mode("droop", droop, ModePriority.SCHEDULE, "排程 + 調頻")

    # 註冊 RampStopStrategy（作為 PROTECTION 級 override）
    ramp_stop = RampStopStrategy(rated_power=2000.0, ramp_rate_pct=50.0)  # 50%/s for demo visibility
    controller.register_mode("ramp_stop", ramp_stop, ModePriority.PROTECTION, "斜坡停機")

    logger.info("[5] Builder 組裝完成")
    logger.info("    保護鏈: DynamicSOC → GridLimit")
    logger.info("    處理器: PowerCompensator")
    logger.info("    策略: DroopStrategy (SCHEDULE) + RampStopStrategy (PROTECTION override)")

    # ── 6. SOCBalancingDistributor ──

    _distributor = SOCBalancingDistributor(  # noqa: F841
        rated_key="rated_p", soc_capability="soc_readable", soc_slot="soc",
        gain=2.0, per_device_max_p=1100.0,
    )
    logger.info("[6] SOCBalancingDistributor: gain=2.0, per_device_max_p=1100kW")

    # ══════════════════════════════════════════════════════════
    # 模擬控制流程
    # ══════════════════════════════════════════════════════════

    logger.info("")
    logger.info("═══ 場景 1: 正常運行（排程 500kW + 調頻）═══")

    ctx = controller.context_builder.build()
    ctx.extra["schedule_p"] = float(params.get("p_command_grid"))

    command = droop.execute(ctx)
    logger.info(f"  [Droop] 輸出: {command.p_target:.1f}kW (500 + droop at 59.95Hz)")

    result = controller.protection_guard.apply(command, ctx)
    logger.info(f"  [Protection] {result.protected_command.p_target:.1f}kW (triggered: {result.triggered_rules})")

    compensated = await compensator.process(result.protected_command, ctx)
    logger.info(f"  [Compensator] {compensated.p_target:.1f}kW")

    # ── 場景 2: EMS 改參數 + GridLimit clamp ──

    logger.info("")
    logger.info("═══ 場景 2: EMS 改排程 1500kW + 電力公司限制降為 50% ═══")

    params.set("p_command_grid", 1500)
    params.set("grid_limit_pct", 50)
    logger.info(f"  params: schedule={params.get('p_command_grid')}kW, limit={params.get('grid_limit_pct')}%")

    ctx2 = controller.context_builder.build()
    ctx2.extra["schedule_p"] = float(params.get("p_command_grid"))

    command2 = droop.execute(ctx2)
    logger.info(f"  [Droop] 輸出: {command2.p_target:.1f}kW (1500 + droop)")

    result2 = controller.protection_guard.apply(command2, ctx2)
    logger.info(
        f"  [Protection] {result2.protected_command.p_target:.1f}kW "
        f"(GridLimit 50% = ±1000kW, triggered: {result2.triggered_rules})"
    )

    # ── 場景 3: 故障 → RampStopStrategy 斜坡降功率 ──

    logger.info("")
    logger.info("═══ 場景 3: 故障觸發 → RampStopStrategy 斜坡降功率 ═══")
    logger.info("  (模擬 EventDrivenOverride push 'ramp_stop')")

    # 模擬啟動 RampStopStrategy
    await ramp_stop.on_activate()
    # 設定 last_command 為故障前的功率
    last_p = result2.protected_command.p_target

    for i in range(6):
        ramp_ctx = controller.context_builder.build()
        ramp_ctx.last_command = Command(p_target=last_p)
        cmd = ramp_stop.execute(ramp_ctx)
        logger.info(f"  cycle {i + 1}: P={cmd.p_target:>8.1f}kW (from {last_p:.1f}kW)")
        last_p = cmd.p_target
        time.sleep(0.1)  # 模擬 100ms 間隔

    logger.info(f"  → 斜坡完成，P={last_p:.1f}kW")

    # ── 場景 4: FF 校準 ──

    logger.info("")
    logger.info("═══ 場景 4: FF Table 步階校準 ═══")

    cal = FFCalibrationStrategy(
        config=FFCalibrationConfig(step_pct=20, min_pct=20, max_pct=40, steady_cycles=3, settle_wait_cycles=0),
        compensator=compensator,
        rated_power=2000.0,
    )
    controller.register_mode("ff_calibration", cal, ModePriority.MANUAL, "FF 校準")

    await cal.on_activate()
    logger.info(f"  校準啟動: {cal.progress['total_bins']} bins 待校準")

    for i in range(3):
        cal_ctx = controller.context_builder.build()
        cal_ctx.extra["meter_power"] = 395.0 + i
        cmd = cal.execute(cal_ctx)
        logger.info(f"  cycle {i + 1}: P={cmd.p_target:.0f}kW, steady={cal._steady_count}/{cal._config.steady_cycles}")

    logger.info(f"  進度: {cal.progress['completed_bins']}/{cal.progress['total_bins']} bins 完成")
    if cal.results:
        for bin_idx, ff in cal.results.items():
            logger.info(f"    bin[{bin_idx}] = {ff:.4f}")

    # ── 完成 ──

    logger.info("")
    logger.info("=" * 60)
    logger.info("  Demo 完成！展示的新功能：")
    logger.info("    RuntimeParameters, DroopStrategy, DynamicSOCProtection,")
    logger.info("    GridLimitProtection, RampStopStrategy, PowerCompensator,")
    logger.info("    FFCalibrationStrategy, SOCBalancingDistributor,")
    logger.info("    CommandProcessor pipeline, Config Builder")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
