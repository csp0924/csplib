"""
Example 16: Operator Pattern — K8s 風 Reconciler / SiteManifest / TypeRegistry

學習目標：
  - Reconciler Protocol：name / status / reconcile_once 契約 + isinstance 檢查
  - ReconcilerStatus：run_count / last_error / healthy / detail 觀測狀態
  - SetpointDriftReconciler：偵測 Gateway 覆蓋 setpoint 並自動復原
  - SiteManifest + TypeRegistry：用 dict 宣告拓撲、decorator 註冊 kind
  - SystemControllerConfigBuilder.from_manifest：把 manifest 轉成 builder

執行方式：
  uv run python examples/16_operator_pattern.py
"""

from __future__ import annotations

import asyncio
import time

from csp_lib.controller.core import Strategy
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata, RangeValidator
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.integration import (
    CommandRouter,
    DeviceRegistry,
    DriftTolerance,
    Reconciler,
    ReconcilerStatus,
    SetpointDriftReconciler,
    apply_manifest_to_builder,
    device_type_registry,
    load_manifest,
    register_device_type,
    register_strategy_type,
    strategy_type_registry,
)
from csp_lib.integration.system_controller import SystemControllerConfigBuilder
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient
from csp_lib.modbus_server import PCSSimulator, ServerConfig, SimulationServer
from csp_lib.modbus_server.simulator.pcs import default_pcs_config

SIM_HOST, SIM_PORT = "127.0.0.1", 5024


# ============================================================
# Section 1 — Reconciler Protocol：自訂 reconciler
# ============================================================
#
# Reconciler 是 @runtime_checkable Protocol，只要類別具備下列 public 成員
# 就算實作了 Protocol：
#   - name: str 屬性
#   - status: ReconcilerStatus 屬性
#   - async reconcile_once() -> ReconcilerStatus
#
# 契約：reconcile_once() 不得 raise；例外必須 catch 後寫入 status.last_error。


class UptimeReconciler:
    """示範用自訂 Reconciler：僅更新一個 uptime 計數器。

    對應 K8s 的 informer：實際不動任何設備，只是聚合觀測資料讓外部 dashboard 讀取。
    """

    def __init__(self, *, name: str = "uptime") -> None:
        self._name = name
        self._run_count = 0
        self._start_monotonic = time.monotonic()
        self._status = ReconcilerStatus.empty(name)

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> ReconcilerStatus:
        return self._status

    async def reconcile_once(self) -> ReconcilerStatus:
        self._run_count += 1
        from types import MappingProxyType

        self._status = ReconcilerStatus(
            name=self._name,
            last_run_at=time.monotonic(),
            last_error=None,  # 契約：絕不對外拋例外；錯誤記在這
            run_count=self._run_count,
            healthy=True,
            detail=MappingProxyType({"uptime_s": time.monotonic() - self._start_monotonic}),
        )
        return self._status


async def section_1_protocol_demo() -> None:
    print("\n" + "=" * 60)
    print(" Section 1 — Reconciler Protocol 基礎")
    print("=" * 60)

    reconciler = UptimeReconciler()

    # runtime_checkable 讓 isinstance() 可直接驗證 Protocol 符合度
    assert isinstance(reconciler, Reconciler), "UptimeReconciler 應符合 Reconciler Protocol"
    print(f"  isinstance(reconciler, Reconciler) = True ✓  ({reconciler.name})")

    # 初始狀態：尚未執行過
    print(f"  初始 status.run_count = {reconciler.status.run_count}")

    for i in range(3):
        await asyncio.sleep(0.1)  # 讓 uptime 逐 tick 變化
        status = await reconciler.reconcile_once()
        print(
            f"  tick {i + 1}: run_count={status.run_count}, "
            f"healthy={status.healthy}, uptime={status.detail['uptime_s']:.3f}s"
        )


# ============================================================
# Section 2 — SetpointDriftReconciler：偵測 Gateway 覆蓋並復原
# ============================================================
#
# 情境：外部 EMS / 工程師用 Modbus Gateway 直接改了 PCS 的 p_setpoint，
# 導致「控制器意向」與「設備實際值」分歧。SetpointDriftReconciler 會：
#   desired = CommandRouter._last_written[device][point]   # 控制器意向
#   actual  = device.latest_values[point]                 # 設備讀回的快取值
#   若 |actual - desired| > tolerance → 呼叫 router.try_write_single 復原

# p_setpoint 同時是 write 與 read 點位：simulator 會把寫入直接反映在同一個 register，
# 因此 ReadScheduler 下一輪就能讀回最新值。
PCS_READ_POINTS = [
    ReadPoint(name="p_setpoint", address=0, data_type=Float32(), metadata=PointMetadata(unit="kW")),
    ReadPoint(name="p_actual", address=4, data_type=Float32(), metadata=PointMetadata(unit="kW")),
    ReadPoint(name="soc", address=8, data_type=Float32(), metadata=PointMetadata(unit="%")),
]
PCS_WRITE_POINTS = [
    WritePoint(
        name="p_setpoint",
        address=0,
        data_type=Float32(),
        validator=RangeValidator(min_value=-200.0, max_value=200.0),
    ),
]


def _build_sim() -> SimulationServer:
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=0.3))
    pcs = PCSSimulator(config=default_pcs_config("pcs_01", unit_id=10), capacity_kwh=200.0, p_ramp_rate=200.0)
    pcs.set_value("soc", 70.0)
    pcs._running = True
    server.add_simulator(pcs)
    return server


async def _wait_until_point_equals(
    device: AsyncModbusDevice, point: str, expected: float, *, tol: float = 0.5, timeout: float = 3.0
) -> None:
    """poll-until-condition：等 ReadScheduler 把寫入值讀回 latest_values。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        val = device.latest_values.get(point)
        if isinstance(val, (int, float)) and abs(float(val) - expected) <= tol:
            return
        await asyncio.sleep(0.1)


async def section_2_setpoint_drift() -> None:
    print("\n" + "=" * 60)
    print(" Section 2 — SetpointDriftReconciler 實戰")
    print("=" * 60)

    sim = _build_sim()
    async with sim:
        # 建立設備
        client = PymodbusTcpClient(ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT))
        device = AsyncModbusDevice(
            config=DeviceConfig(device_id="pcs_01", unit_id=10, read_interval=0.3),
            client=client,
            always_points=PCS_READ_POINTS,
            write_points=PCS_WRITE_POINTS,
        )

        # Registry + CommandRouter（純手動，不啟動 SystemController，突顯 reconciler 是獨立能力）
        registry = DeviceRegistry()
        registry.register(device, traits=["pcs"])
        router = CommandRouter(registry, mappings=[])  # 這範例直接用 try_write_single，不需要 CommandMapping

        reconciler = SetpointDriftReconciler(
            router=router,
            registry=registry,
            tolerance=DriftTolerance(absolute=1.0, relative=0.02),  # 1 kW 或 2%
        )
        assert isinstance(reconciler, Reconciler)  # 同一 Protocol 契約
        print(f"  Reconciler name={reconciler.name}, tolerance=±1.0 kW 或 2%")

        await device.connect()
        await device.start()
        try:
            # Step A：控制器寫入 desired state（模擬策略下命令）
            ok = await router.try_write_single("pcs_01", "p_setpoint", 40.0)
            print(f"\n  [A] 控制器下命令 p_setpoint=40 kW → try_write_single ok={ok}")
            print(f"      router.get_last_written('pcs_01') = {router.get_last_written('pcs_01')}")
            await _wait_until_point_equals(device, "p_setpoint", 40.0)
            print(f"      ReadScheduler 讀回 latest={device.latest_values.get('p_setpoint'):.1f} kW（與 desired 一致）")

            # Step B：呼叫 reconcile_once → 無 drift，drift_count=0
            status = await reconciler.reconcile_once()
            print(f"\n  [B] 無漂移 reconcile：drift_count={status.detail['drift_count']}, healthy={status.healthy}")

            # Step C：模擬 Gateway 在 controller 不知情的情況下覆蓋 setpoint
            sim.simulators[10].set_value("p_setpoint", 120.0)  # 外部粗暴覆蓋
            print("\n  [C] 外部 Gateway 把 p_setpoint 改成 120 kW（繞過控制器）...")
            await _wait_until_point_equals(device, "p_setpoint", 120.0)
            print(f"      ReadScheduler 偵測到 latest={device.latest_values.get('p_setpoint'):.1f} kW")

            # Step D：reconciler 比對 desired(40) vs actual(120) → 重寫 40
            status = await reconciler.reconcile_once()
            print(
                f"\n  [D] 有漂移 reconcile："
                f"drift_count={status.detail['drift_count']}, "
                f"devices_fixed={list(status.detail['devices_fixed'])}"
            )
            await _wait_until_point_equals(device, "p_setpoint", 40.0)
            print(f"      設備端已復原至 {device.latest_values.get('p_setpoint'):.1f} kW ✓")
        finally:
            await device.stop()
            await device.disconnect()


# ============================================================
# Section 3 — SiteManifest + TypeRegistry + from_manifest
# ============================================================
#
# manifest 用 dict 宣告一整個站點的 devices / strategies / reconcilers，
# 由 TypeRegistry 把 `kind: ExamplePCS` 動態 map 到實際 class。


@register_device_type("ExamplePCS", force=True)  # force=True 讓範例可重複執行
class ExamplePCSDevice(AsyncModbusDevice):
    """示範用 device kind；實務上可以塞任何 AsyncModbusDevice 子類。"""


@register_strategy_type("PQStrategy", force=True)
class DummyPQStrategy(Strategy):
    """示範用 strategy kind；只要符合 Strategy ABC 即可。"""

    def __init__(self, p: float = 0.0, q: float = 0.0) -> None:
        self.p = p
        self.q = q

    async def execute(self, context):  # type: ignore[override]
        from csp_lib.controller.core import Command

        return Command(p_target=self.p, q_target=self.q)


def section_3_manifest() -> None:
    print("\n" + "=" * 60)
    print(" Section 3 — SiteManifest + TypeRegistry")
    print("=" * 60)

    # 檢視 registry（decorator 註冊的結果）
    print(f"  device_type_registry: {device_type_registry.list()}")
    print(f"  strategy_type_registry: {strategy_type_registry.list()}")

    # 用 dict 宣告 manifest（等同 kubectl apply -f site.yaml）
    manifest_dict: dict = {
        "apiVersion": "csp_lib/v1",
        "kind": "Site",
        "metadata": {"name": "example-bess-site", "labels": {"env": "dev"}},
        "spec": {
            "devices": [
                {"kind": "ExamplePCS", "name": "pcs_main", "config": {"host": "192.168.1.10", "unit_id": 1}},
            ],
            "strategies": [
                {"kind": "PQStrategy", "name": "default-pq", "config": {"p": 50.0, "q": 10.0}},
            ],
            "reconcilers": [
                # CommandRefresh 是內建 kind → 會被 apply_manifest_to_builder 直接消化成 builder.command_refresh(...)
                {"kind": "CommandRefresh", "name": "cmd-refresh", "config": {"interval_seconds": 2.0, "enabled": True}},
                # SetpointDrift 是自訂 kind → 保留在 builder.manifest_reconcilers 供使用者自行實例化
                {"kind": "SetpointDrift", "name": "drift", "config": {"tolerance_absolute": 5.0}},
            ],
        },
    }

    manifest = load_manifest(manifest_dict)
    print(f"\n  載入 manifest: apiVersion={manifest.apiVersion}, site={manifest.metadata.name}")

    # from_manifest：把 manifest 直接轉成已預填的 builder
    builder = SystemControllerConfigBuilder.from_manifest(manifest)

    # 已被 bound 的 device class（kind → class）
    for bound in builder.manifest_devices:
        print(f"  ✓ device bound: name={bound.name!r}, kind={bound.source.kind!r}, cls={bound.cls.__name__}")
    for bound in builder.manifest_strategies:
        print(f"  ✓ strategy bound: name={bound.name!r}, kind={bound.source.kind!r}, cls={bound.cls.__name__}")

    # 內建 reconciler（CommandRefresh）已被 builder.command_refresh 消化
    # 自訂 reconciler 留在 manifest_reconcilers 給使用者自行實例化
    print("\n  自訂 Reconciler specs（待使用者實例化）：")
    for rec in builder.manifest_reconcilers:
        print(f"    - kind={rec.kind!r}, name={rec.name!r}, config={dict(rec.config)}")

    # 也可直接呼叫 apply_manifest_to_builder 拿到完整 bind 結果
    fresh_builder = SystemControllerConfigBuilder()
    result = apply_manifest_to_builder(fresh_builder, manifest)
    print(
        f"\n  apply_manifest_to_builder: {len(result.devices)} device, "
        f"{len(result.strategies)} strategy, "
        f"{len(result.reconcilers)} 自訂 reconciler（CommandRefresh 已消化不在此）"
    )


# ============================================================
# Main
# ============================================================


async def main() -> None:
    print("=" * 60)
    print(" Example 16: Operator Pattern (K8s 風 Reconciler)")
    print("=" * 60)

    await section_1_protocol_demo()
    await section_2_setpoint_drift()
    section_3_manifest()

    print("\n" + "=" * 60)
    print(" 學到了什麼")
    print("=" * 60)
    print("  1. Reconciler Protocol：name + status + reconcile_once，不得對外 raise")
    print("  2. ReconcilerStatus：frozen dataclass，含 run_count / last_error / detail")
    print("  3. SetpointDriftReconciler：偵測外部覆蓋並自動復原（desired vs actual）")
    print("  4. CommandRefreshService / HeartbeatService 同樣實作 Reconciler Protocol")
    print("  5. @register_device_type / @register_strategy_type：decorator 式 kind 註冊")
    print("  6. SiteManifest：dict / YAML 宣告站點拓撲（apiVersion: csp_lib/v1）")
    print("  7. SystemControllerConfigBuilder.from_manifest：manifest → builder")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
