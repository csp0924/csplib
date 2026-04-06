"""
csp_lib Example 08: 自定義策略 — 繼承 Strategy ABC + PID 控制

學習目標：
  - 繼承 Strategy ABC 建立自定義控制策略
  - ConfigMixin 提供 frozen config + from_dict() 支援
  - 比例（P）控制器實作頻率調整
  - on_activate() / on_deactivate() 生命週期掛鉤
  - 完整的「定義策略 → 配置 → 運行 → 觀察效果」流程

情境：
  電網頻率偏離 60Hz 時，儲能系統自動輸出有功功率補償：
    - 頻率低於 60Hz → 放電（P > 0）支撐電網
    - 頻率高於 60Hz → 充電（P < 0）吸收多餘功率
    - 補償量 = Kp * (f_target - f_actual) * p_base

架構：
  SimulationServer (PCS + 電表)
       ↕ TCP
  AsyncModbusDevice
       ↓ context (extra.frequency)
  SystemController
    └── FrequencyRegulationStrategy (自定義)
          → 讀取頻率偏差 → 輸出 P 補償

Run: uv run python examples/08_custom_strategy.py
"""

import asyncio
import sys
from dataclasses import dataclass

# Windows 終端 UTF-8 支援
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from csp_lib.controller.core import (
    Command,
    ConfigMixin,
    ExecutionConfig,
    ExecutionMode,
    Strategy,
    StrategyContext,
)
from csp_lib.controller.system import ModePriority
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.integration import (
    CommandMapping,
    ContextMapping,
    DeviceRegistry,
    SystemController,
    SystemControllerConfig,
)
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import PCSSimulator, PowerMeterSimulator, ServerConfig, SimulationServer
from csp_lib.modbus_server.simulator.pcs import default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import default_meter_config

# ============================================================
# 常量
# ============================================================

SIM_HOST = "127.0.0.1"
SIM_PORT = 5080  # 避免與其他範例衝突


# ============================================================
# Section 1: 自定義策略定義
# ============================================================


@dataclass
class FrequencyRegulationConfig(ConfigMixin):
    """
    頻率調節策略配置

    Attributes:
        f_target: 目標頻率 (Hz)
        kp: 比例增益 (kW/Hz)，偏差 1Hz 時的輸出功率
        p_max: 最大輸出功率 (kW)
        deadband: 死區寬度 (Hz)，頻率偏差小於此值時不輸出
    """

    f_target: float = 60.0
    kp: float = 500.0  # 偏差 1Hz → 輸出 500kW
    p_max: float = 200.0
    deadband: float = 0.05  # ±0.05Hz 內不響應


class FrequencyRegulationStrategy(Strategy):
    """
    頻率調節策略 — 比例控制器

    從 context.extra["frequency"] 讀取電網頻率，
    計算偏差後用比例控制輸出有功功率補償。

    功率方向：
      - f < f_target → 電網缺電 → 放電 P > 0
      - f > f_target → 電網過剩 → 充電 P < 0
    """

    def __init__(self, config: FrequencyRegulationConfig | None = None) -> None:
        self._config = config or FrequencyRegulationConfig()
        self._last_output: float = 0.0  # 追蹤上次輸出（診斷用）

    @property
    def config(self) -> FrequencyRegulationConfig:
        """當前配置"""
        return self._config

    @property
    def execution_config(self) -> ExecutionConfig:
        """每秒執行一次"""
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        """
        執行頻率調節策略

        Args:
            context: 策略上下文，需要 extra["frequency"] 欄位

        Returns:
            Command: 有功功率補償命令
        """
        # 從 context 讀取頻率
        frequency = context.extra.get("frequency")
        if frequency is None:
            # 無頻率資料時維持上次輸出
            return Command(p_target=self._last_output, q_target=0.0)

        cfg = self._config

        # 計算頻率偏差
        error = cfg.f_target - frequency  # 正值 = 頻率偏低

        # 死區處理
        if abs(error) < cfg.deadband:
            self._last_output = 0.0
            return Command(p_target=0.0, q_target=0.0)

        # 比例控制：P = Kp * error
        p_output = cfg.kp * error

        # 限幅
        p_output = max(-cfg.p_max, min(cfg.p_max, p_output))

        self._last_output = p_output
        return Command(p_target=p_output, q_target=0.0)

    def update_config(self, config: FrequencyRegulationConfig) -> None:
        """更新配置"""
        self._config = config

    async def on_activate(self) -> None:
        """策略啟用時重設內部狀態"""
        self._last_output = 0.0
        print("  [FreqReg] 策略已啟用，內部狀態已重設")

    async def on_deactivate(self) -> None:
        """策略停用時清理"""
        self._last_output = 0.0
        print("  [FreqReg] 策略已停用")

    def __str__(self) -> str:
        return (
            f"FrequencyRegulationStrategy("
            f"f_target={self._config.f_target}Hz, "
            f"Kp={self._config.kp}, "
            f"deadband={self._config.deadband}Hz)"
        )


# ============================================================
# Section 2: 獨立展示 — 策略行為驗證
# ============================================================


async def demo_strategy_standalone():
    """獨立測試自定義策略，不需要 SimulationServer"""
    print("=" * 70)
    print("Section A: FrequencyRegulationStrategy 獨立展示")
    print("=" * 70)

    config = FrequencyRegulationConfig(f_target=60.0, kp=500.0, p_max=200.0, deadband=0.05)
    strategy = FrequencyRegulationStrategy(config)
    await strategy.on_activate()

    # 測試不同頻率場景
    test_cases = [
        (60.00, "正常頻率（在死區內）"),
        (59.80, "頻率偏低 0.2Hz → 放電支撐"),
        (60.20, "頻率偏高 0.2Hz → 充電吸收"),
        (59.50, "頻率大幅偏低 0.5Hz → 放電（限幅）"),
        (60.50, "頻率大幅偏高 0.5Hz → 充電（限幅）"),
        (59.96, "微小偏差 0.04Hz（在死區內）"),
    ]

    print(
        f"\n  配置: f_target={config.f_target}Hz, Kp={config.kp}, "
        f"P_max={config.p_max}kW, deadband=±{config.deadband}Hz\n"
    )

    for freq, desc in test_cases:
        ctx = StrategyContext(extra={"frequency": freq})
        cmd = strategy.execute(ctx)
        error = config.f_target - freq
        print(f"  f={freq:.2f}Hz (偏差={error:+.2f}Hz): P={cmd.p_target:+.1f}kW — {desc}")

    await strategy.on_deactivate()

    # 展示 ConfigMixin.from_dict()
    print("\n  --- ConfigMixin.from_dict() 展示 ---")
    config_dict = {"f_target": 50.0, "kp": 300.0, "p_max": 100.0, "deadband": 0.1}
    new_config = FrequencyRegulationConfig.from_dict(config_dict)
    print(f"  從 dict 建立: f_target={new_config.f_target}Hz, Kp={new_config.kp}")

    # 展示 to_dict()
    as_dict = new_config.to_dict()
    print(f"  轉回 dict: {as_dict}")


# ============================================================
# Section 3: SimulationServer 建立
# ============================================================


def create_simulation_server() -> tuple[SimulationServer, PCSSimulator, PowerMeterSimulator]:
    """建立模擬伺服器：1 台 PCS + 1 台電表"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    pcs_config = default_pcs_config("pcs_01", unit_id=10)
    pcs_sim = PCSSimulator(config=pcs_config, capacity_kwh=200.0, p_ramp_rate=200.0)
    pcs_sim.set_value("soc", 70.0)
    pcs_sim.set_value("operating_mode", 1)
    pcs_sim._running = True

    meter_config = default_meter_config("meter_01", unit_id=1)
    meter_sim = PowerMeterSimulator(config=meter_config)
    meter_sim.set_system_reading(v=380.0, f=60.0, p=20.0, q=5.0)

    server.add_simulator(pcs_sim)
    server.add_simulator(meter_sim)
    return server, pcs_sim, meter_sim


def create_devices() -> tuple[AsyncModbusDevice, AsyncModbusDevice]:
    """建立 PCS 和電表的 AsyncModbusDevice"""
    tcp_config = ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT, timeout=2.0)
    f32 = Float32()
    u16 = UInt16()

    pcs_read_points = [
        ReadPoint(name="p_actual", address=4, data_type=f32, metadata=PointMetadata(unit="kW")),
        ReadPoint(name="q_actual", address=6, data_type=f32, metadata=PointMetadata(unit="kVar")),
        ReadPoint(name="soc", address=8, data_type=f32, metadata=PointMetadata(unit="%")),
        ReadPoint(name="operating_mode", address=10, data_type=u16),
    ]
    pcs_write_points = [
        WritePoint(name="p_setpoint", address=0, data_type=f32, metadata=PointMetadata(unit="kW")),
        WritePoint(name="q_setpoint", address=2, data_type=f32, metadata=PointMetadata(unit="kVar")),
    ]
    pcs_client = PymodbusTcpClient(tcp_config)
    pcs_device = AsyncModbusDevice(
        config=DeviceConfig(device_id="pcs_01", unit_id=10, read_interval=0.5),
        client=pcs_client,
        always_points=pcs_read_points,
        write_points=pcs_write_points,
    )

    meter_read_points = [
        ReadPoint(name="active_power", address=12, data_type=f32, metadata=PointMetadata(unit="kW")),
        ReadPoint(name="frequency", address=20, data_type=f32, metadata=PointMetadata(unit="Hz")),
    ]
    meter_client = PymodbusTcpClient(tcp_config)
    meter_device = AsyncModbusDevice(
        config=DeviceConfig(device_id="meter_01", unit_id=1, read_interval=0.5),
        client=meter_client,
        always_points=meter_read_points,
    )

    return pcs_device, meter_device


# ============================================================
# Section 4: 完整系統 — 自定義策略 + SystemController
# ============================================================


async def demo_custom_strategy_system():
    """
    完整展示自定義策略搭配 SystemController。
    改變模擬電表頻率，觀察策略自動調整功率輸出。
    """
    print("\n" + "=" * 70)
    print("Section B: 自定義策略 + SystemController 完整展示")
    print("=" * 70)

    server, pcs_sim, meter_sim = create_simulation_server()
    pcs_device, meter_device = create_devices()

    async with server:
        print("\n[1] SimulationServer 啟動完成")
        await asyncio.sleep(0.5)

        async with pcs_device, meter_device:
            print("[2] PCS 和電表設備已連線")
            await asyncio.sleep(1.5)

            # --- 註冊設備 ---
            registry = DeviceRegistry()
            registry.register(pcs_device, traits=["pcs"])
            registry.register(meter_device, traits=["meter"])

            # --- 建立 SystemController ---
            config = SystemControllerConfig(
                context_mappings=[
                    ContextMapping(point_name="soc", context_field="soc", device_id="pcs_01"),
                    # 將電表頻率映射到 context.extra["frequency"]
                    ContextMapping(point_name="frequency", context_field="extra.frequency", device_id="meter_01"),
                ],
                command_mappings=[
                    CommandMapping(command_field="p_target", point_name="p_setpoint", device_id="pcs_01"),
                    CommandMapping(command_field="q_target", point_name="q_setpoint", device_id="pcs_01"),
                ],
                auto_stop_on_alarm=False,
            )
            controller = SystemController(registry, config)

            # --- 註冊自定義策略 ---
            freq_config = FrequencyRegulationConfig(
                f_target=60.0,
                kp=500.0,
                p_max=200.0,
                deadband=0.05,
            )
            freq_strategy = FrequencyRegulationStrategy(freq_config)
            controller.register_mode("freq_reg", freq_strategy, ModePriority.SCHEDULE, "頻率調節模式")
            await controller.set_base_mode("freq_reg")

            async with controller:
                print("[3] SystemController 已啟動，使用自定義 FrequencyRegulationStrategy")
                print("    配置: f_target=60.0Hz, Kp=500, P_max=200kW, deadband=0.05Hz\n")

                # 定義頻率變化場景
                scenarios = [
                    (60.0, "正常頻率 60.0Hz → P 應接近 0"),
                    (59.8, "頻率偏低 59.8Hz → 放電 +100kW 支撐"),
                    (60.2, "頻率偏高 60.2Hz → 充電 -100kW 吸收"),
                    (59.5, "頻率大幅偏低 59.5Hz → 放電 +200kW（限幅）"),
                    (60.0, "頻率恢復 60.0Hz → P 回到 0"),
                ]

                for freq, desc in scenarios:
                    print(f"--- 場景: {desc} ---")
                    # 更新模擬電表頻率
                    meter_sim.set_system_reading(v=380.0, f=freq, p=20.0, q=5.0)
                    await asyncio.sleep(3)

                    pcs_vals = pcs_device.latest_values
                    meter_vals = meter_device.latest_values
                    print(f"  電表頻率: {meter_vals.get('frequency', 'N/A'):.2f}Hz")
                    print(
                        f"  PCS 輸出: P_actual={pcs_vals.get('p_actual', 0.0):.1f}kW, "
                        f"SOC={pcs_vals.get('soc', 'N/A'):.1f}%\n"
                    )

            print("[4] SystemController 已停止")
        print("[5] 設備已斷線")
    print("[6] SimulationServer 已關閉")


# ============================================================
# Main
# ============================================================


async def main():
    print()
    print("csp_lib Example 08: 自定義策略")
    print("==============================")

    # Section A: 獨立展示策略行為
    await demo_strategy_standalone()

    # Section B: 完整系統展示
    await demo_custom_strategy_system()

    print("\n" + "=" * 70)
    print("範例完成！")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
