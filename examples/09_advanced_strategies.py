"""
csp_lib Example 09: 進階策略與保護規則

展示進階控制策略與保護規則：
  - Section A: ProtectionGuard 串接 SOC、逆功率、系統告警保護規則
  - Section B: PVSmoothStrategy 光伏平滑策略（模擬 PV 資料）
  - Section C: FPStrategy 頻率-功率響應曲線
  - Section D: ModeManager 基礎模式切換與覆蓋堆疊
  - Section E: LoadSheddingStrategy 階段性負載卸載（v0.4.2 新增）
  - Section F: EventDrivenOverride 事件驅動自動 Override（v0.4.2 新增）

Run: uv run python examples/09_advanced_strategies.py
"""

import asyncio

from csp_lib.controller.core import Command, StrategyContext, SystemBase
from csp_lib.controller.services import PVDataService
from csp_lib.controller.strategies import (
    FPConfig,
    FPStrategy,
    IslandModeConfig,
    IslandModeStrategy,
    PQModeConfig,
    PQModeStrategy,
    PVSmoothConfig,
    PVSmoothStrategy,
    StopStrategy,
)
from csp_lib.controller.system import (
    ModeManager,
    ModePriority,
    ProtectionGuard,
    ReversePowerProtection,
    SOCProtection,
    SOCProtectionConfig,
    SystemAlarmProtection,
)

# ============================================================
# Section A: 進階保護規則
# ============================================================


async def demo_protection_rules():
    """
    展示 ProtectionGuard 串接多個保護規則。

    規則依序套用：
      1. SOCProtection     — 警告區間漸進功率限制
      2. ReversePowerProtection — 防止電網逆送電（逆功率保護）
      3. SystemAlarmProtection  — 系統告警緊急停止
    """
    print("=" * 60)
    print("Section A: Advanced Protection Rules")
    print("=" * 60)

    # --- 配置保護規則 ---
    soc_protection = SOCProtection(
        SOCProtectionConfig(
            soc_high=95.0,  # SOC 超過 95% 禁止充電
            soc_low=5.0,  # SOC 低於 5% 禁止放電
            warning_band=5.0,  # 距離限制值 5% 內漸進限制
        )
    )
    reverse_power = ReversePowerProtection(
        threshold=0.0,  # 零容忍：不允許任何電網逆送電
        meter_power_key="meter_power",
    )
    alarm_protection = SystemAlarmProtection(alarm_key="system_alarm")

    # 將規則串接為 ProtectionGuard
    guard = ProtectionGuard(rules=[soc_protection, reverse_power, alarm_protection])

    # --- 場景 1: 正常運行（無保護觸發）---
    print("\n[1] Normal operation: SOC=50%, meter=100kW, no alarm")
    command = Command(p_target=200.0, q_target=50.0)
    context = StrategyContext(soc=50.0, extra={"meter_power": 100.0, "system_alarm": False})
    result = guard.apply(command, context)
    print(f"    Original:  {result.original_command}")
    print(f"    Protected: {result.protected_command}")
    print(f"    Modified:  {result.was_modified}  |  Triggered: {result.triggered_rules}")

    # --- 場景 2: SOC 高警告區間（漸進充電限制）---
    # SOC=92% 在 [90%, 95%) 警告區間內。充電 (P<0) 被漸進限制。
    # ratio = (95 - 92) / 5 = 0.6，充電功率縮放為 60%。
    print("\n[2] SOC high warning band: SOC=92%, charging at P=-100kW")
    command = Command(p_target=-100.0, q_target=0.0)
    context = StrategyContext(soc=92.0, extra={"meter_power": 200.0, "system_alarm": False})
    result = guard.apply(command, context)
    print(f"    Original:  {result.original_command}")
    print(f"    Protected: {result.protected_command}")
    print(f"    Modified:  {result.was_modified}  |  Triggered: {result.triggered_rules}")
    print("    (充電限制為 60%: -100 * 0.6 = -60 kW)")

    # --- 場景 3: SOC 達硬限制（充電完全阻止）---
    print("\n[3] SOC at hard limit: SOC=96%, charging at P=-100kW")
    command = Command(p_target=-100.0, q_target=0.0)
    context = StrategyContext(soc=96.0, extra={"meter_power": 200.0, "system_alarm": False})
    result = guard.apply(command, context)
    print(f"    Original:  {result.original_command}")
    print(f"    Protected: {result.protected_command}")
    print(f"    Modified:  {result.was_modified}  |  Triggered: {result.triggered_rules}")
    print("    (充電完全阻止: P 限制為 0)")

    # --- 場景 4: SOC 低警告區間（漸進放電限制）---
    # SOC=7% 在 (5%, 10%] 警告區間內。放電 (P>0) 被漸進限制。
    # ratio = (7 - 5) / 5 = 0.4，放電功率縮放為 40%。
    print("\n[4] SOC low warning band: SOC=7%, discharging at P=200kW")
    command = Command(p_target=200.0, q_target=0.0)
    context = StrategyContext(soc=7.0, extra={"meter_power": 300.0, "system_alarm": False})
    result = guard.apply(command, context)
    print(f"    Original:  {result.original_command}")
    print(f"    Protected: {result.protected_command}")
    print(f"    Modified:  {result.was_modified}  |  Triggered: {result.triggered_rules}")
    print("    (放電限制為 40%: 200 * 0.4 = 80 kW)")

    # --- 場景 5: 逆功率保護（防止電網逆送電）---
    # 電表讀取 50kW 用電。放電 200kW 會產生 150kW 逆送電。
    # 限制為最大放電 = 電表功率 + 門檻值 = 50 + 0 = 50kW。
    print("\n[5] Reverse power: meter=50kW import, discharging P=200kW")
    command = Command(p_target=200.0, q_target=0.0)
    context = StrategyContext(soc=50.0, extra={"meter_power": 50.0, "system_alarm": False})
    result = guard.apply(command, context)
    print(f"    Original:  {result.original_command}")
    print(f"    Protected: {result.protected_command}")
    print(f"    Modified:  {result.was_modified}  |  Triggered: {result.triggered_rules}")
    print("    (放電限制為電表負載: 50 kW)")

    # --- 場景 6: 系統告警（緊急停止）---
    print("\n[6] System alarm: emergency stop overrides everything")
    command = Command(p_target=500.0, q_target=100.0)
    context = StrategyContext(soc=50.0, extra={"meter_power": 600.0, "system_alarm": True})
    result = guard.apply(command, context)
    print(f"    Original:  {result.original_command}")
    print(f"    Protected: {result.protected_command}")
    print(f"    Modified:  {result.was_modified}  |  Triggered: {result.triggered_rules}")
    print("    (告警保護強制 P=0, Q=0)")


# ============================================================
# Section B: 光伏平滑策略
# ============================================================


async def demo_pv_smooth():
    """
    展示 PVSmoothStrategy 平滑快速 PV 功率波動。

    策略流程：
      1. 對歷史 PV 功率讀數取平均
      2. 扣除系統損耗
      3. 套用斜率限制防止輸出突變
    """
    print("\n" + "=" * 60)
    print("Section B: PV Smooth Strategy")
    print("=" * 60)

    # 配置 PV 資料服務與策略
    pv_service = PVDataService(max_history=10)
    config = PVSmoothConfig(
        capacity=500.0,  # 500 kW 光伏系統
        ramp_rate=10.0,  # 每週期最大變化 10%（50 kW）
        pv_loss=5.0,  # 系統損耗 5 kW
        min_history=3,  # 需要至少 3 筆歷史資料
    )
    strategy = PVSmoothStrategy(config=config, pv_service=pv_service, interval_seconds=900)

    print(f"\nPV System: capacity={config.capacity} kW, ramp_rate={config.ramp_rate}%")
    print(f"Ramp limit per cycle: {config.capacity * config.ramp_rate / 100:.0f} kW")
    print(f"System loss: {config.pv_loss} kW, min_history: {config.min_history}")

    # 模擬 PV 功率讀數（太陽能輸出 kW）
    # 早晨爬升 -> 雲遮蔽 -> 恢復
    pv_readings = [100.0, 150.0, 200.0, 350.0, 120.0, 130.0, 280.0, 400.0, 380.0, 350.0]

    print(f"\nSimulated PV readings: {pv_readings}")
    print(f"\n{'Cycle':>5} | {'PV Reading':>10} | {'Avg Power':>10} | {'Adjusted':>10} | {'P Target':>10} | {'Note'}")
    print("-" * 80)

    last_command = Command(p_target=0.0, q_target=0.0)

    for i, pv_power in enumerate(pv_readings, 1):
        pv_service.append(pv_power)

        context = StrategyContext(last_command=last_command)
        command = strategy.execute(context)

        # 顯示計算細節
        avg = pv_service.get_average()
        adjusted = max((avg or 0.0) - config.pv_loss, 0.0) if avg else 0.0
        note = ""
        if pv_service.count < config.min_history:
            note = "歷史資料不足"
        elif abs(command.p_target - adjusted) > 0.01:
            note = "斜率限制中"

        print(
            f"{i:>5} | {pv_power:>10.1f} | {avg or 0:>10.1f} | {adjusted:>10.1f} | {command.p_target:>10.1f} | {note}"
        )
        last_command = command


# ============================================================
# Section C: 頻率-功率（FP）策略
# ============================================================


async def demo_fp_strategy():
    """
    展示 FPStrategy 對電網頻率偏差的響應。

    FP 曲線使用 6 個斷點（分段線性內插）：
      f < f1: 最大放電（電網低頻緊急狀態）
      f1-f2: 重放電區域
      f2-f3: 輕放電接近死區
      f3-f4: 死區（不響應）
      f4-f5: 輕充電離開死區
      f5-f6: 重充電區域
      f > f6: 最大充電（電網高頻緊急狀態）
    """
    print("\n" + "=" * 60)
    print("Section C: Frequency-Power (FP) Strategy")
    print("=" * 60)

    # 配置 FP 曲線，使用偏移量斷點
    config = FPConfig(
        f_base=60.0,  # 電網標稱頻率（Hz）
        # 相對於基準的頻率偏移（必須遞增）
        f1=-0.50,  # 59.50 Hz
        f2=-0.25,  # 59.75 Hz
        f3=-0.02,  # 59.98 Hz（死區下限）
        f4=0.02,  # 60.02 Hz（死區上限）
        f5=0.25,  # 60.25 Hz
        f6=0.50,  # 60.50 Hz
        # 功率百分比（必須遞減）
        p1=100.0,  # f1 處最大放電
        p2=52.0,  # f2 處中等放電
        p3=9.0,  # 接近死區時輕放電
        p4=-9.0,  # 接近死區時輕充電
        p5=-52.0,  # f5 處中等充電
        p6=-100.0,  # f6 處最大充電
    )
    strategy = FPStrategy(config)

    # 系統額定容量（百分比轉 kW 用）
    system_base = SystemBase(p_base=1000.0, q_base=500.0)

    # 印出 FP 曲線斷點
    abs_freqs = config.get_absolute_frequencies()
    powers = [config.p1, config.p2, config.p3, config.p4, config.p5, config.p6]
    print(f"\nFP Curve (f_base={config.f_base} Hz, P_base={system_base.p_base} kW):")
    print(f"  Deadband: {abs_freqs[2]:.2f} Hz - {abs_freqs[3]:.2f} Hz")
    print(f"\n  {'Freq (Hz)':>10} | {'Offset':>8} | {'P (%)':>8} | {'P (kW)':>8}")
    print("  " + "-" * 45)
    for freq, pwr in zip(abs_freqs, powers, strict=True):
        offset = freq - config.f_base
        p_kw = pwr * system_base.p_base / 100
        print(f"  {freq:>10.2f} | {offset:>+8.2f} | {pwr:>+8.1f} | {p_kw:>+8.0f}")

    # 模擬頻率掃描
    test_frequencies = [59.30, 59.50, 59.75, 59.90, 59.99, 60.00, 60.01, 60.10, 60.25, 60.50, 60.70]

    print(f"\n{'Frequency (Hz)':>15} | {'P Output (kW)':>14} | {'Action'}")
    print("-" * 55)

    for freq in test_frequencies:
        context = StrategyContext(system_base=system_base, extra={"frequency": freq})
        command = strategy.execute(context)

        # 判斷動作描述
        if command.p_target > 10:
            action = "DISCHARGE (支撐電網)"
        elif command.p_target < -10:
            action = "CHARGE (吸收多餘電力)"
        else:
            action = "DEADBAND (死區待機)"

        print(f"{freq:>15.2f} | {command.p_target:>+14.1f} | {action}")


# ============================================================
# Section D: ModeManager 與覆蓋堆疊
# ============================================================


class MockRelay:
    """簡易 mock 繼電器，用於 IslandModeStrategy 演示。"""

    def __init__(self):
        self._is_open = False
        self._sync_ok = True
        self._sync_counter = 0

    @property
    def sync_ok(self) -> bool:
        return self._sync_ok

    @property
    def sync_counter(self) -> int:
        return self._sync_counter

    async def set_open(self) -> None:
        self._is_open = True
        print("    [Relay] ACB 斷開（孤島模式）")

    async def set_close(self) -> None:
        self._is_open = False
        print("    [Relay] ACB 合閘（併網）")

    async def set_force_close(self) -> None:
        self._is_open = False
        print("    [Relay] ACB 強制合閘")


async def demo_mode_manager():
    """
    展示 ModeManager 基礎模式切換與覆蓋堆疊。

    ModeManager 支援：
      - 基礎模式：預設運行策略
      - 覆蓋堆疊：暫時取代基礎模式的高優先級模式
      - 優先級排序：多個覆蓋同時存在時，最高優先級者勝出
    """
    print("\n" + "=" * 60)
    print("Section D: ModeManager with Override Stack")
    print("=" * 60)

    # 透過回呼追蹤策略變更
    async def on_strategy_change(old_strategy, new_strategy):
        old_name = str(old_strategy) if old_strategy else "None"
        new_name = str(new_strategy) if new_strategy else "None"
        print(f"    [Callback] Strategy changed: {old_name} -> {new_name}")

    mode_manager = ModeManager(on_strategy_change=on_strategy_change)

    # --- 註冊模式 ---
    pq_strategy = PQModeStrategy(PQModeConfig(p=500.0, q=0.0))
    stop_strategy = StopStrategy()
    relay = MockRelay()
    island_strategy = IslandModeStrategy(relay, config=IslandModeConfig(sync_timeout=5.0))

    mode_manager.register("pq_base", pq_strategy, priority=ModePriority.SCHEDULE, description="PQ 固定輸出")
    mode_manager.register("stop", stop_strategy, priority=ModePriority.MANUAL, description="手動停止")
    mode_manager.register("island", island_strategy, priority=ModePriority.PROTECTION, description="孤島模式（緊急）")

    print("\n已註冊模式：")
    for name, mode_def in mode_manager.registered_modes.items():
        print(f"  {name:>12}: priority={mode_def.priority:>3}, desc={mode_def.description}")

    # --- 步驟 1: 設定基礎模式 ---
    print("\n[Step 1] 設定 PQ 為基礎模式")
    await mode_manager.set_base_mode("pq_base")
    effective = mode_manager.effective_mode
    print(f"  Effective mode: {effective.name if effective else 'None'}")
    print(f"  Effective strategy: {mode_manager.effective_strategy}")
    print(f"  Base mode: {mode_manager.base_mode_name}")
    print(f"  Active overrides: {mode_manager.active_override_names}")

    # 執行有效策略以展示其運作
    context = StrategyContext(soc=50.0)
    command = mode_manager.effective_strategy.execute(context)
    print(f"  Command output: {command}")

    # --- 步驟 2: 推入 stop 覆蓋（優先級 50 > 基礎 10）---
    print("\n[Step 2] 推入 'stop' 覆蓋（手動停止, priority=50）")
    await mode_manager.push_override("stop")
    effective = mode_manager.effective_mode
    print(f"  Effective mode: {effective.name if effective else 'None'}")
    print(f"  Effective strategy: {mode_manager.effective_strategy}")
    print(f"  Active overrides: {mode_manager.active_override_names}")

    command = mode_manager.effective_strategy.execute(context)
    print(f"  Command output: {command}")

    # --- 步驟 3: 推入 island 覆蓋（優先級 100 > stop 50）---
    print("\n[Step 3] 推入 'island' 覆蓋（緊急, priority=100）")
    await mode_manager.push_override("island")
    effective = mode_manager.effective_mode
    print(f"  Effective mode: {effective.name if effective else 'None'}")
    print(f"  Effective strategy: {mode_manager.effective_strategy}")
    print(f"  Active overrides: {mode_manager.active_override_names}")
    print("  （孤島模式勝出，因為優先級 100 > stop 的 50）")

    # --- 步驟 4: 彈出 island 覆蓋（回落到 stop）---
    print("\n[Step 4] 彈出 'island' 覆蓋（緊急狀態解除）")
    await mode_manager.pop_override("island")
    effective = mode_manager.effective_mode
    print(f"  Effective mode: {effective.name if effective else 'None'}")
    print(f"  Effective strategy: {mode_manager.effective_strategy}")
    print(f"  Active overrides: {mode_manager.active_override_names}")
    print("  （回落到 'stop' 覆蓋，仍然有效）")

    # --- 步驟 5: 彈出 stop 覆蓋（回到基礎模式）---
    print("\n[Step 5] 彈出 'stop' 覆蓋（恢復正常運行）")
    await mode_manager.pop_override("stop")
    effective = mode_manager.effective_mode
    print(f"  Effective mode: {effective.name if effective else 'None'}")
    print(f"  Effective strategy: {mode_manager.effective_strategy}")
    print(f"  Active overrides: {mode_manager.active_override_names}")
    print("  （無覆蓋殘留；基礎模式 'pq_base' 生效）")

    # --- 步驟 6: 切換基礎模式 ---
    print("\n[Step 6] 切換基礎模式: PQ -> Stop")
    await mode_manager.set_base_mode("stop")
    effective = mode_manager.effective_mode
    print(f"  Effective mode: {effective.name if effective else 'None'}")
    print(f"  Base mode: {mode_manager.base_mode_name}")

    # --- 優先級摘要 ---
    print("\n--- 模式優先級摘要 ---")
    print(f"  SCHEDULE   = {ModePriority.SCHEDULE:>3}  （正常運行：PQ、PVSmooth、FP）")
    print(f"  MANUAL     = {ModePriority.MANUAL:>3}  （操作員覆蓋：停止、旁路）")
    print(f"  PROTECTION = {ModePriority.PROTECTION:>3}  （安全覆蓋：孤島、緊急）")
    print("  最高優先級覆蓋始終優先於基礎模式。")


# ============================================================
# Section E: LoadSheddingStrategy（階段性負載卸載）
# ============================================================


class MockCircuit:
    """
    Mock load circuit implementing LoadCircuitProtocol.

    In production, this would write to a breaker/relay via Modbus or CAN.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._is_shed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_shed(self) -> bool:
        return self._is_shed

    async def shed(self) -> None:
        self._is_shed = True
        print(f"    [Circuit] '{self._name}' SHED (disconnected)")

    async def restore(self) -> None:
        self._is_shed = False
        print(f"    [Circuit] '{self._name}' RESTORED (connected)")


async def demo_load_shedding():
    """
    Demonstrates LoadSheddingStrategy: multi-stage load shedding based on
    context conditions (SOC threshold, remaining time, etc.).

    Shedding order: low priority first (priority=0 before priority=1)
    Restore order:  high priority first (priority=1 before priority=0)
    """
    print("\n" + "=" * 60)
    print("Section E: LoadSheddingStrategy")
    print("=" * 60)

    from csp_lib.controller.strategies.load_shedding import (
        LoadSheddingConfig,
        LoadSheddingStrategy,
        ShedStage,
        ThresholdCondition,
    )

    # Define shedding conditions
    low_soc_condition = ThresholdCondition(
        context_key="soc",
        shed_below=25.0,  # Shed when SOC < 25%
        restore_above=35.0,  # Restore when SOC > 35%
    )

    # Define load circuits
    ac_unit = MockCircuit("air_conditioner")
    water_heater = MockCircuit("water_heater")
    ev_charger = MockCircuit("ev_charger")

    config = LoadSheddingConfig(
        stages=[
            ShedStage(
                name="stage1_non_critical",
                circuits=[ac_unit, water_heater],
                condition=low_soc_condition,
                priority=0,  # Shed first (lowest priority)
                min_hold_seconds=0.0,  # No hold time for demo
            ),
            ShedStage(
                name="stage2_semi_critical",
                circuits=[ev_charger],
                condition=ThresholdCondition(context_key="soc", shed_below=15.0, restore_above=20.0),
                priority=1,  # Shed second (higher priority)
                min_hold_seconds=0.0,
            ),
        ],
        evaluation_interval=1,
        restore_delay=0.1,  # Short delay for demo
        auto_restore_on_deactivate=True,
    )

    strategy = LoadSheddingStrategy(config)

    # --- Activate and simulate low SOC ---
    await strategy.on_activate()

    print("\n[1] Normal SOC=50% (no shedding)")
    ctx = StrategyContext(soc=50.0, extra={"soc": 50.0})
    strategy.execute(ctx)
    await asyncio.sleep(0.2)
    print(f"    Shed stages: {strategy.shed_stage_names}")

    print("\n[2] SOC drops to 20% → stage1 shed trigger")
    ctx = StrategyContext(soc=20.0, extra={"soc": 20.0})
    strategy.execute(ctx)
    await asyncio.sleep(0.5)  # Wait for background action loop
    print(f"    Shed stages: {strategy.shed_stage_names}")
    print(f"    AC shed: {ac_unit.is_shed}, Water heater shed: {water_heater.is_shed}")

    print("\n[3] SOC drops to 10% → stage2 shed trigger")
    ctx = StrategyContext(soc=10.0, extra={"soc": 10.0})
    strategy.execute(ctx)
    await asyncio.sleep(0.5)
    print(f"    Shed stages: {strategy.shed_stage_names}")
    print(f"    EV charger shed: {ev_charger.is_shed}")

    print("\n[4] SOC recovers to 40% → staged restore (high priority first)")
    ctx = StrategyContext(soc=40.0, extra={"soc": 40.0})
    strategy.execute(ctx)
    await asyncio.sleep(0.5)

    print("\n[5] on_deactivate → auto-restore all remaining circuits")
    await strategy.on_deactivate()
    print(f"    AC shed: {ac_unit.is_shed}, EV shed: {ev_charger.is_shed}")


# ============================================================
# Section F: EventDrivenOverride（事件驅動自動 Override）
# ============================================================


async def demo_event_driven_override():
    """
    Demonstrates EventDrivenOverride protocol and built-in implementations:
      - AlarmStopOverride: auto-stop on system alarm flag
      - ContextKeyOverride: generic key-based trigger

    SystemController evaluates all registered EventDrivenOverride instances
    on every execution cycle and automatically push/pop the corresponding mode.
    """
    print("\n" + "=" * 60)
    print("Section F: EventDrivenOverride")
    print("=" * 60)

    from csp_lib.controller.system.event_override import (
        AlarmStopOverride,
        ContextKeyOverride,
    )

    # --- AlarmStopOverride ---
    print("\n[1] AlarmStopOverride: triggers on context.extra['system_alarm'] = True")
    alarm_override = AlarmStopOverride(name="__auto_stop__", alarm_key="system_alarm")
    print(f"    name={alarm_override.name}, cooldown={alarm_override.cooldown_seconds}s")

    ctx_no_alarm = StrategyContext(soc=60.0, extra={"system_alarm": False})
    ctx_alarm = StrategyContext(soc=60.0, extra={"system_alarm": True})
    print(f"    should_activate(no alarm): {alarm_override.should_activate(ctx_no_alarm)}")
    print(f"    should_activate(alarm):    {alarm_override.should_activate(ctx_alarm)}")

    # --- ContextKeyOverride ---
    print("\n[2] ContextKeyOverride: ACB trip → island mode")
    acb_override = ContextKeyOverride(
        name="island",
        context_key="acb_tripped",
        activate_when=lambda v: v is True,
        cooldown_seconds=5.0,
    )
    print(f"    name={acb_override.name}, cooldown={acb_override.cooldown_seconds}s")

    ctx_normal = StrategyContext(soc=60.0, extra={"acb_tripped": False})
    ctx_tripped = StrategyContext(soc=60.0, extra={"acb_tripped": True})
    print(f"    should_activate(normal):  {acb_override.should_activate(ctx_normal)}")
    print(f"    should_activate(tripped): {acb_override.should_activate(ctx_tripped)}")

    # --- Frequency deviation override ---
    print("\n[3] ContextKeyOverride: frequency deviation → FP emergency mode")
    freq_override = ContextKeyOverride(
        name="fp_emergency",
        context_key="frequency",
        activate_when=lambda f: abs(f - 60.0) > 0.5,
        cooldown_seconds=10.0,
    )
    for freq in [60.0, 60.3, 60.55, 59.45, 59.9]:
        activated = freq_override.should_activate(StrategyContext(soc=60.0, extra={"frequency": freq}))
        print(f"    freq={freq:.2f}Hz → activate={activated}")

    print("\n  Note: In production, register overrides via:")
    print("    controller.register_event_override(acb_override)")
    print("  SystemController auto-pushes/pops the named mode on each cycle.")


# ============================================================
# 執行所有段落
# ============================================================


async def main():
    await demo_protection_rules()
    await demo_pv_smooth()
    await demo_fp_strategy()
    await demo_mode_manager()
    await demo_load_shedding()
    await demo_event_driven_override()


if __name__ == "__main__":
    asyncio.run(main())
