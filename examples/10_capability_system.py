"""
Example 10: Capability System — 設備能力宣告與自動解析

學習目標：
  - Capability 定義（標準 + 自訂）
  - CapabilityBinding 將語意 slot 映射到實際點位
  - CapabilityContextMapping 自動讀取多設備聚合值
  - CapabilityCommandMapping 自動寫入多設備
  - CapabilityRequirement + preflight_check 部署驗證
  - DeviceRegistry 能力查詢、健康檢查

核心概念：
  Capability 定義「能做什麼」（語意插槽）
  CapabilityBinding 定義「怎麼做」（插槽→實際點位）
  不同品牌的設備可用不同點位名稱實作同一能力，
  Controller 透過 capability slot 統一操作，不需知道底層細節。

Run:
  uv run python examples/10_capability_system.py
"""

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from csp_lib.controller.strategies import PQModeConfig, PQModeStrategy
from csp_lib.controller.system import ModePriority
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata, RangeValidator
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.equipment.device.capability import (
    ACTIVE_POWER_CONTROL,
    FREQUENCY_MEASURABLE,
    HEARTBEAT,
    MEASURABLE,
    REACTIVE_POWER_CONTROL,
    SOC_READABLE,
    VOLTAGE_MEASURABLE,
    Capability,
    CapabilityBinding,
)
from csp_lib.integration import (
    AggregateFunc,
    CapabilityCommandMapping,
    CapabilityContextMapping,
    CapabilityRequirement,
    DeviceRegistry,
    SystemController,
    SystemControllerConfig,
)
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import PCSSimulator, PowerMeterSimulator, ServerConfig, SimulationServer
from csp_lib.modbus_server.simulator.pcs import default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import default_meter_config

# ============================================================
# 常數
# ============================================================
SIM_HOST, SIM_PORT = "127.0.0.1", 5020


async def main() -> None:
    print("=" * 60)
    print("  Example 10: Capability System — 設備能力宣告與自動解析")
    print("=" * 60)

    # ==========================================================
    # Section A: Capability 基礎概念
    # ==========================================================

    # ---- Step 1: 標準 Capability 介紹 ----
    print("\n=== Step 1: 標準 Capability 介紹 ===")
    print("  csp_lib 預定義了 9 個標準能力：")
    standard_caps = [
        HEARTBEAT,
        ACTIVE_POWER_CONTROL,
        REACTIVE_POWER_CONTROL,
        SOC_READABLE,
        MEASURABLE,
        FREQUENCY_MEASURABLE,
        VOLTAGE_MEASURABLE,
    ]
    for cap in standard_caps:
        slots = list(cap.write_slots) + list(cap.read_slots)
        print(f"  - {cap.name:<25s} slots={slots}  ({cap.description})")

    # 自訂能力也很簡單
    TEMPERATURE_READABLE = Capability(
        name="temperature_readable",
        read_slots=("temperature",),
        description="設備溫度量測",
    )
    print(f"\n  自訂能力範例: {TEMPERATURE_READABLE.name}, slots={list(TEMPERATURE_READABLE.all_slots)}")

    # ---- Step 2: CapabilityBinding — 同一能力、不同品牌映射 ----
    print("\n=== Step 2: CapabilityBinding — 不同品牌的點位映射 ===")

    # Sungrow PCS: p_setpoint slot → "p_set" 點位, p_measurement slot → "active_power" 點位
    sungrow_p_binding = CapabilityBinding(
        ACTIVE_POWER_CONTROL,
        {"p_setpoint": "p_set", "p_measurement": "active_power"},
    )
    # Huawei PCS: 同一能力，不同點位名
    huawei_p_binding = CapabilityBinding(
        ACTIVE_POWER_CONTROL,
        {"p_setpoint": "p_cmd", "p_measurement": "p_out"},
    )

    print(f"  Sungrow 映射: p_setpoint → '{sungrow_p_binding.resolve('p_setpoint')}'")
    print(f"                p_measurement → '{sungrow_p_binding.resolve('p_measurement')}'")
    print(f"  Huawei  映射: p_setpoint → '{huawei_p_binding.resolve('p_setpoint')}'")
    print(f"                p_measurement → '{huawei_p_binding.resolve('p_measurement')}'")

    # ---- Step 3: resolve_point() 解析語意插槽 ----
    print("\n=== Step 3: resolve_point() 解析語意插槽 ===")
    print("  Controller 不需要知道 Sungrow 叫 'p_set' 還是 Huawei 叫 'p_cmd'")
    print("  只要統一用: binding.resolve('p_setpoint') 即可取得實際點位名")
    for label, binding in [("Sungrow", sungrow_p_binding), ("Huawei", huawei_p_binding)]:
        point = binding.resolve("p_setpoint")
        print(f"  {label}: resolve('p_setpoint') → '{point}'")

    # ==========================================================
    # Section B: Registry 能力查詢（SimulationServer + 真實設備）
    # ==========================================================
    print("\n" + "=" * 60)
    print("  Section B: DeviceRegistry 能力查詢")
    print("=" * 60)

    # ---- Step 4: 建立 3 台 PCS + 1 台電表，用 SimulationServer ----
    print("\n=== Step 4: 建立 SimulationServer + 設備 ===")

    sim_server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    # 3 台 PCS（unit_id=10, 11, 12）
    for uid, soc_init in [(10, 75.0), (11, 60.0), (12, 85.0)]:
        pcs = PCSSimulator(config=default_pcs_config(f"pcs_{uid}", unit_id=uid), capacity_kwh=200.0, p_ramp_rate=50.0)
        pcs.set_value("soc", soc_init)
        pcs.set_value("operating_mode", 1)
        pcs._running = True
        sim_server.add_simulator(pcs)

    # 1 台電表（unit_id=1）
    meter_sim = PowerMeterSimulator(config=default_meter_config("meter_01", unit_id=1))
    meter_sim.set_system_reading(v=380.0, f=60.0, p=30.0, q=5.0)
    sim_server.add_simulator(meter_sim)

    async with sim_server:
        print(f"  SimulationServer 已啟動: {SIM_HOST}:{SIM_PORT}")
        print("  設備: PCS x3 (unit 10,11,12), Meter x1 (unit 1)")

        # PCS 共用點位定義 + capability bindings
        # 標準 PCS register 佈局: p_setpoint=0, q_setpoint=2, p_actual=4, soc=8, voltage=15, frequency=17
        def make_pcs(device_id: str, unit_id: int) -> AsyncModbusDevice:
            """建立 PCS 設備（含 capability bindings）"""
            client = PymodbusTcpClient(ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT))
            return AsyncModbusDevice(
                config=DeviceConfig(device_id=device_id, unit_id=unit_id, read_interval=0.5),
                client=client,
                always_points=[
                    ReadPoint(name="p_actual", address=4, data_type=Float32(), metadata=PointMetadata(unit="kW")),
                    ReadPoint(name="soc", address=8, data_type=Float32(), metadata=PointMetadata(unit="%")),
                    ReadPoint(name="operating_mode", address=10, data_type=UInt16()),
                    ReadPoint(name="voltage", address=15, data_type=Float32(), metadata=PointMetadata(unit="V")),
                    ReadPoint(name="frequency", address=17, data_type=Float32(), metadata=PointMetadata(unit="Hz")),
                ],
                write_points=[
                    WritePoint(
                        "p_setpoint",
                        address=0,
                        data_type=Float32(),
                        validator=RangeValidator(min_value=-200.0, max_value=200.0),
                    ),
                    WritePoint(
                        "q_setpoint",
                        address=2,
                        data_type=Float32(),
                        validator=RangeValidator(min_value=-100.0, max_value=100.0),
                    ),
                ],
                capability_bindings=[
                    # 實功控制: slot → 實際點位
                    CapabilityBinding(ACTIVE_POWER_CONTROL, {"p_setpoint": "p_setpoint", "p_measurement": "p_actual"}),
                    CapabilityBinding(REACTIVE_POWER_CONTROL, {"q_setpoint": "q_setpoint"}),
                    CapabilityBinding(SOC_READABLE, {"soc": "soc"}),
                    CapabilityBinding(VOLTAGE_MEASURABLE, {"voltage": "voltage"}),
                    CapabilityBinding(FREQUENCY_MEASURABLE, {"frequency": "frequency"}),
                    CapabilityBinding(MEASURABLE, {"active_power": "p_actual"}),
                ],
            )

        pcs_devices = [make_pcs(f"pcs_{uid}", uid) for uid in [10, 11, 12]]

        # 電表設備（含 MEASURABLE + FREQUENCY_MEASURABLE）
        meter_client = PymodbusTcpClient(ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT))
        meter_device = AsyncModbusDevice(
            config=DeviceConfig(device_id="meter_01", unit_id=1, read_interval=0.5),
            client=meter_client,
            always_points=[
                ReadPoint(name="active_power", address=12, data_type=Float32(), metadata=PointMetadata(unit="kW")),
                ReadPoint(name="frequency", address=20, data_type=Float32(), metadata=PointMetadata(unit="Hz")),
            ],
            capability_bindings=[
                CapabilityBinding(MEASURABLE, {"active_power": "active_power"}),
                CapabilityBinding(FREQUENCY_MEASURABLE, {"frequency": "frequency"}),
            ],
        )

        # 註冊到 Registry（使用 register_with_capabilities 自動產生 cap: traits）
        registry = DeviceRegistry()
        for pcs in pcs_devices:
            registry.register_with_capabilities(pcs, extra_traits=["pcs", "energy_storage"])
        registry.register_with_capabilities(meter_device, extra_traits=["meter"])

        print(f"  已註冊 {len(registry)} 台設備")
        print(f"  所有 traits: {registry.all_traits}")

        # ---- Step 5: get_devices_with_capability() 查詢 ----
        print("\n=== Step 5: 依 Capability 查詢設備 ===")

        for cap in [ACTIVE_POWER_CONTROL, SOC_READABLE, MEASURABLE, FREQUENCY_MEASURABLE]:
            devices = registry.get_devices_with_capability(cap)
            ids = [d.device_id for d in devices]
            print(f"  {cap.name:<25s} → {ids}")

        # ---- Step 6: get_capability_map_text() 可視化 ----
        print("\n=== Step 6: Capability Map 全域視圖 ===")
        print(registry.get_capability_map_text())

        # ---- Step 7: capability_health() 健康檢查 ----
        print("\n=== Step 7: Capability 健康檢查 ===")
        print("  (設備尚未連線，responsive 為 False)")
        health = registry.capability_health(ACTIVE_POWER_CONTROL)
        print(f"  {health['capability']}:")
        print(f"    總設備: {health['total_devices']}, 可用: {health['responsive_devices']}")
        print(f"    可用比例: {health['responsive_ratio']:.0%}")
        for d in health["devices"]:
            print(f"    - {d['device_id']}: responsive={d['is_responsive']}")

        # ==========================================================
        # Section C: preflight_check 部署驗證
        # ==========================================================
        print("\n" + "=" * 60)
        print("  Section C: preflight_check 部署驗證")
        print("=" * 60)

        # ---- Step 8: 定義能力需求 ----
        print("\n=== Step 8: CapabilityRequirement 定義 ===")
        requirements = [
            CapabilityRequirement(ACTIVE_POWER_CONTROL, min_count=3),
            CapabilityRequirement(SOC_READABLE, min_count=2),
            CapabilityRequirement(FREQUENCY_MEASURABLE, min_count=1, trait_filter="meter"),
        ]
        for req in requirements:
            trait_info = f" (trait={req.trait_filter})" if req.trait_filter else ""
            print(f"  需要: {req.capability.name} >= {req.min_count} 台{trait_info}")

        # ---- Step 9: validate_capabilities() — 先測試不足再補齊 ----
        print("\n=== Step 9: validate_capabilities() 驗證 ===")

        # 9a: 故意用過高的需求測試失敗
        strict_reqs = [
            CapabilityRequirement(ACTIVE_POWER_CONTROL, min_count=5),  # 只有 3 台
            CapabilityRequirement(SOC_READABLE, min_count=2),  # 有 3 台，OK
        ]
        failures = registry.validate_capabilities(strict_reqs)
        if failures:
            print("  [不足] 以下需求未滿足：")
            for f in failures:
                print(f"    - {f}")
        else:
            print("  [通過] 所有需求已滿足")

        # 9b: 用合理的需求測試成功
        print()
        failures = registry.validate_capabilities(requirements)
        if failures:
            print("  [不足] 以下需求未滿足：")
            for f in failures:
                print(f"    - {f}")
        else:
            print("  [通過] 所有需求已滿足！部署可繼續")

        # ==========================================================
        # Section D: SystemController 整合（完整控制迴路）
        # ==========================================================
        print("\n" + "=" * 60)
        print("  Section D: SystemController Capability-Driven 控制迴路")
        print("=" * 60)

        # ---- Step 10: CapabilityContextMapping 讀取 ----
        print("\n=== Step 10: CapabilityContextMapping 設定 ===")
        print("  SOC: 從所有 PCS 平均 SOC → context.soc")
        print("  meter_power: 從 meter 讀取 active_power → context.extra['meter_power']")
        print("  frequency: 從 meter 讀取 frequency → context.extra['frequency']")

        # ---- Step 11: CapabilityCommandMapping 寫入 ----
        print("\n=== Step 11: CapabilityCommandMapping 設定 ===")
        print("  p_target → 寫入所有 PCS 的 p_setpoint slot（自動解析到各設備實際點位）")
        print("  q_target → 寫入所有 PCS 的 q_setpoint slot")

        # 用 builder 建構 config
        config = (
            SystemControllerConfig.builder()
            # Capability Context: SOC 從所有具備 SOC_READABLE 的 PCS 平均
            .map_capability_context(
                CapabilityContextMapping(
                    capability=SOC_READABLE,
                    slot="soc",
                    context_field="soc",
                    trait="pcs",
                    aggregate=AggregateFunc.AVERAGE,
                    min_device_ratio=0.5,
                )
            )
            # Capability Context: 電表功率
            .map_capability_context(
                CapabilityContextMapping(
                    capability=MEASURABLE,
                    slot="active_power",
                    context_field="extra.meter_power",
                    trait="meter",
                    aggregate=AggregateFunc.FIRST,
                )
            )
            # Capability Context: 電表頻率
            .map_capability_context(
                CapabilityContextMapping(
                    capability=FREQUENCY_MEASURABLE,
                    slot="frequency",
                    context_field="extra.frequency",
                    trait="meter",
                    aggregate=AggregateFunc.FIRST,
                )
            )
            # Capability Command: P target → 所有 PCS 的 p_setpoint
            .map_capability_command(
                CapabilityCommandMapping(
                    command_field="p_target",
                    capability=ACTIVE_POWER_CONTROL,
                    slot="p_setpoint",
                    trait="pcs",
                )
            )
            # Capability Command: Q target → 所有 PCS 的 q_setpoint
            .map_capability_command(
                CapabilityCommandMapping(
                    command_field="q_target",
                    capability=REACTIVE_POWER_CONTROL,
                    slot="q_setpoint",
                    trait="pcs",
                )
            )
            # preflight 需求
            .require_capability(CapabilityRequirement(ACTIVE_POWER_CONTROL, min_count=3))
            .require_capability(CapabilityRequirement(SOC_READABLE, min_count=2))
            .auto_stop(enabled=True)
            .build()
        )

        print("\n  Config 建構完成:")
        print(f"    Capability context mappings: {len(config.capability_context_mappings)}")
        print(f"    Capability command mappings: {len(config.capability_command_mappings)}")
        print(f"    Capability requirements: {len(config.capability_requirements)}")

        # ---- Step 12: 啟動 SystemController 運行控制迴路 ----
        print("\n=== Step 12: 啟動 SystemController 控制迴路 ===")

        controller = SystemController(registry, config)

        # 註冊 PQ 模式: 每台 PCS 寫入 P=30 kW
        pq = PQModeStrategy(PQModeConfig(p=30.0, q=5.0))
        controller.register_mode("pq", pq, ModePriority.SCHEDULE, "PQ 固定功率模式")
        await controller.set_base_mode("pq")

        # 連線所有設備
        all_devices = pcs_devices + [meter_device]
        for dev in all_devices:
            await dev.connect()
            await dev.start()
        print("  所有設備已連線並啟動讀取")

        # preflight check（在 controller start 前手動呼叫看結果）
        preflight_failures = controller.preflight_check()
        if preflight_failures:
            print(f"  [警告] preflight 未通過: {preflight_failures}")
        else:
            print("  preflight_check 通過！所有能力需求已滿足")

        # 啟動控制迴路
        async with controller:
            print("  SystemController 已啟動，控制迴路運行中...")
            print()

            for cycle in range(5):
                await asyncio.sleep(1.0)

                # 顯示各 PCS 的 P 和 SOC
                parts = []
                for pcs in pcs_devices:
                    p = pcs.latest_values.get("p_actual", 0)
                    soc = pcs.latest_values.get("soc", 0)
                    p_str = f"{p:.1f}" if isinstance(p, float) else str(p)
                    soc_str = f"{soc:.1f}" if isinstance(soc, float) else str(soc)
                    parts.append(f"{pcs.device_id}: P={p_str}kW SOC={soc_str}%")

                # 電表功率
                mp = meter_device.latest_values.get("active_power", 0)
                mp_str = f"{mp:.1f}" if isinstance(mp, float) else str(mp)

                print(f"  Cycle {cycle + 1}: {' | '.join(parts)} | meter={mp_str}kW")

            print("\n  (capability-driven 自動解析：Controller 用 slot 名稱操作，")
            print("   每台設備的 CapabilityBinding 自動轉換為實際點位)")

        # 清理
        for dev in all_devices:
            await dev.stop()
            await dev.disconnect()
        print("\n  所有設備已停止")

    # ==========================================================
    # 總結
    # ==========================================================
    print("\n" + "=" * 60)
    print("  學到了什麼：")
    print("  1. Capability: 用語意 slot 定義設備「能做什麼」")
    print("  2. CapabilityBinding: 將 slot 映射到各品牌的實際點位名")
    print("  3. resolve_point(): 統一的語意查詢，屏蔽品牌差異")
    print("  4. DeviceRegistry: capability 查詢、map 視圖、健康檢查")
    print("  5. CapabilityRequirement + preflight_check: 部署前驗證")
    print("  6. CapabilityContextMapping: 自動讀取+聚合多設備值")
    print("  7. CapabilityCommandMapping: 自動寫入多設備（slot 自動解析）")
    print("  8. SystemController: Capability-driven 完整控制迴路")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
