---
tags:
  - type/guide
  - layer/integration
  - status/complete
created: 2026-04-20
updated: 2026-04-20
version: ">=0.9.0"
---

# Site Manifest（站點宣告式配置）

v0.9.0 引入的 `SiteManifest` 讓你以 YAML 宣告整個站點的設備、策略與 Reconciler 配置，再透過 `SystemControllerConfigBuilder.from_manifest()` 自動組裝 `SystemControllerConfig`。風格對應 Kubernetes 的 `kubectl apply -f site.yaml`。

## 安裝

Site Manifest 使用 `pyyaml` 解析 YAML（僅 `load_manifest()` 需要）：

```bash
pip install "csp0924_lib[manifest]"
# 或連同其他 extras 一起安裝
pip install "csp0924_lib[modbus,mongo,redis,manifest]"
```

若你只使用 Python `dict` 直接傳入（不讀 YAML 檔案），則不需要安裝 `[manifest]` extra。

## Manifest 結構

```yaml
apiVersion: csp_lib/v1
kind: Site
metadata:
  name: example-bess-site
  labels:
    env: production

spec:
  devices:
    - id: pcs_main
      kind: ExamplePCS            # 對應 TypeRegistry 中 @register_device_type("ExamplePCS")
      host: 192.168.1.10
      port: 502
      unit_id: 1
      config:
        read_interval: 1.0
        reconnect_delay: 5.0

    - id: bms_rack1
      kind: CustomBMS
      host: 192.168.1.20
      port: 502
      unit_id: 2
      config:
        read_interval: 2.0

    - id: meter_grid
      kind: ExampleMeter         # 對應 TypeRegistry 中 @register_device_type("ExampleMeter")
      host: 192.168.1.30
      port: 502
      unit_id: 3

  strategies:
    - mode: pq_control
      kind: PQModeStrategy    # 對應 TypeRegistry 中 @register_strategy_type("PQModeStrategy")
      priority: 100
      config:
        p_kw: 0.0
        q_kvar: 0.0

    - mode: droop_control
      kind: DroopStrategy
      priority: 80
      config:
        droop_gain: 0.05

  reconcilers:
    - kind: CommandRefresh    # 內建 kind，直接映射 builder.command_refresh(...)
      config:
        interval_seconds: 1.0
        enabled: true

    - kind: SetpointDrift     # 自訂 Reconciler kind
      config:
        tolerance_absolute: 5.0
        tolerance_relative: 0.02
```

> [!warning] 安全警告：只使用 yaml.safe_load
> `load_manifest()` 強制使用 `yaml.safe_load`，不允許 `!!python/object/apply:...` 等任意 Python 物件構造。**請勿在 manifest 中使用 YAML 標籤**，否則會引發 `yaml.constructor.ConstructorError`。
>
> YAML 檔案若來自不可信來源，請在呼叫 `load_manifest()` 前先進行路徑白名單驗證。

## 載入 Manifest

```python
from pathlib import Path
from csp_lib.integration import load_manifest, SiteManifest

# 從檔案路徑載入
manifest = load_manifest("configs/site.yaml")

# 從 Path 物件載入
manifest = load_manifest(Path("configs/site.yaml"))

# 從 dict 載入（不需要 pyyaml）
manifest = load_manifest({
    "apiVersion": "csp_lib/v1",
    "kind": "Site",
    "metadata": {"name": "test-site"},
    "spec": {
        "devices": [...],
        "strategies": [...],
        "reconcilers": [],
    },
})

# 直接從 YAML 字串載入
import yaml
manifest = load_manifest(yaml.safe_load(yaml_string))
```

## TypeRegistry：動態映射 kind 到 class

`TypeRegistry` 是 manifest 中 `kind` 欄位的動態解析器，對應 Kubernetes CRD 的 GroupVersionKind 概念：

```python
from csp_lib.integration import (
    register_device_type,
    register_strategy_type,
    device_type_registry,
    strategy_type_registry,
    TypeRegistry,
)

# 使用 decorator 註冊設備型別
@register_device_type("ExamplePCS")
class ExamplePCSDevice(AsyncModbusDevice):
    """範例 PCS 設備"""
    ...

@register_device_type("ExampleMeter")
class ExampleMeterDevice(AsyncModbusDevice):
    """範例電錶設備"""
    ...

# 使用 decorator 註冊策略型別
@register_strategy_type("PQModeStrategy")
class PQModeStrategy(Strategy):
    ...

# 直接操作 registry（等價於 decorator）
device_type_registry.register("CustomBMS", CustomBMSDevice)

# 查詢
cls = device_type_registry.get("ExamplePCS")   # 回傳 ExamplePCSDevice；未找到 → ConfigurationError
"ExamplePCS" in device_type_registry           # True

# 列出所有已註冊的 kind
all_kinds = device_type_registry.list()    # ["ExamplePCS", "ExampleMeter", "CustomBMS"]
```

### kind 命名規則

- 允許：`[A-Za-z_][A-Za-z0-9_-]*`（如 `ExamplePCS`、`custom-bms`、`PQMode_V2`）
- 不允許：包含 `/`（如 `csp_lib/PCS`）
- 重複 `register` 同一 kind 會 raise `ValueError`；需覆寫請用 `force=True`：

```python
device_type_registry.register("ExamplePCS", NewExamplePCSDevice, force=True)
```

- TypeRegistry 是 Thread-safe（使用 `threading.Lock`）

## from_manifest：Manifest 驅動建構 Builder

```python
from csp_lib.integration import SystemControllerConfigBuilder, load_manifest

manifest = load_manifest("configs/site.yaml")

# 方法一：直接從 manifest 建立 builder
builder = SystemControllerConfigBuilder.from_manifest(manifest)

# 方法二：傳入 path / dict，自動呼叫 load_manifest
builder = SystemControllerConfigBuilder.from_manifest("configs/site.yaml")
builder = SystemControllerConfigBuilder.from_manifest({"apiVersion": "csp_lib/v1", ...})

# 使用自訂 TypeRegistry（不用全域 singleton）
builder = SystemControllerConfigBuilder.from_manifest(
    manifest,
    device_registry=my_device_registry,
    strategy_registry=my_strategy_registry,
)
```

### from_manifest 後繼續 Fluent Chain

`from_manifest` 回傳正常的 `SystemControllerConfigBuilder`，可繼續接其他配置：

```python
config = (
    SystemControllerConfigBuilder.from_manifest("configs/site.yaml")
    # 繼續加入保護規則
    .protect(SOCProtection(min_soc=0.1, max_soc=0.95))
    # 加入更多 context mapping
    .map_context(ContextMapping(field="grid_power", device_id="meter_grid", point_name="power"))
    # 最後 build
    .build()
)
```

### Builder 新增的 manifest 唯讀 properties

| Property | 型別 | 說明 |
|----------|------|------|
| `manifest_source` | `str \| None` | manifest 檔案路徑（若從 Path 載入）|
| `manifest_devices` | `list[BoundDeviceSpec]` | 已成功繫結到 class 的設備規格 |
| `manifest_strategies` | `list[BoundStrategySpec]` | 已成功繫結到 class 的策略規格 |
| `manifest_reconcilers` | `list[BoundReconcilerSpec]` | 未被內建處理的自訂 Reconciler 規格 |

## ManifestBindResult：繫結結果

```python
from csp_lib.integration import apply_manifest_to_builder, ManifestBindResult

result: ManifestBindResult = apply_manifest_to_builder(builder, manifest)

print(result.bound_devices)       # list[BoundDeviceSpec]
print(result.bound_strategies)    # list[BoundStrategySpec]
print(result.bound_reconcilers)   # list[BoundReconcilerSpec]（已被 builder 消化的 built-in）
print(result.manifest_reconcilers)  # list[BoundReconcilerSpec]（留給使用者自行處理）
```

### 內建 Reconciler kind

`CommandRefresh` 是唯一的內建 kind，`apply_manifest_to_builder` 會自動呼叫 `builder.command_refresh(**config)`：

```yaml
reconcilers:
  - kind: CommandRefresh
    config:
      interval_seconds: 1.0
      enabled: true
      devices: ["pcs_main", "pcs_backup"]  # None = 全部設備
```

其他 kind（如 `SetpointDrift`）會保留在 `ManifestBindResult.manifest_reconcilers`，使用者自行實例化後傳入 `SystemController`。

## 完整使用範例

```python
import asyncio
from pathlib import Path
from csp_lib.integration import (
    SystemControllerConfigBuilder,
    load_manifest,
    register_device_type,
    SetpointDriftReconciler, DriftTolerance,
)
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.modbus import PymodbusTcpClient, ModbusTcpConfig


# 1. 先在模組載入時註冊型別
@register_device_type("ExamplePCS")
class ExamplePCSDevice(AsyncModbusDevice):
    pass


# 2. 載入 manifest 並建構 config
manifest = load_manifest(Path("configs/site.yaml"))

builder = SystemControllerConfigBuilder.from_manifest(manifest)
config = builder.protect(...).build()

# 3. 取得未處理的 reconciler specs，自行實例化
result = builder.manifest_reconcilers  # list[BoundReconcilerSpec]
reconcilers = []
for spec in result:
    if spec.kind == "SetpointDrift":
        reconcilers.append(
            SetpointDriftReconciler(
                router=command_router,
                registry=device_registry,
                tolerance=DriftTolerance(
                    absolute=spec.config.get("tolerance_absolute", 5.0),
                    relative=spec.config.get("tolerance_relative", 0.02),
                ),
            )
        )

# 4. 啟動系統
async def main():
    async with SystemController(registry, config) as controller:
        await controller.run()

asyncio.run(main())
```

## Dataclass 結構參考

### SiteManifest

```python
@dataclass(frozen=True, slots=True)
class SiteManifest:
    api_version: str          # 必須為 "csp_lib/v1"
    kind: str                 # 必須為 "Site"
    metadata: ManifestMetadata
    spec: SiteSpec
```

### ManifestMetadata

```python
@dataclass(frozen=True, slots=True)
class ManifestMetadata:
    name: str
    labels: dict[str, str]    # 預設空 dict
```

### SiteSpec / DeviceSpec / StrategySpec / ReconcilerSpec

```python
@dataclass(frozen=True, slots=True)
class SiteSpec:
    devices: tuple[DeviceSpec, ...]
    strategies: tuple[StrategySpec, ...]
    reconcilers: tuple[ReconcilerSpec, ...]

@dataclass(frozen=True, slots=True)
class DeviceSpec:
    id: str
    kind: str
    host: str
    port: int
    unit_id: int
    config: dict[str, Any]    # 傳遞給設備類別 __init__ 的額外 kwargs

@dataclass(frozen=True, slots=True)
class StrategySpec:
    mode: str                 # ModeManager 中的模式名稱
    kind: str                 # TypeRegistry 中的策略 kind
    priority: int
    config: dict[str, Any]

@dataclass(frozen=True, slots=True)
class ReconcilerSpec:
    kind: str
    config: dict[str, Any]
```

## 與 Fluent Builder 的定位比較

| 方式 | 適用場景 | 優點 |
|------|---------|------|
| Fluent Builder（Python code）| 複雜邏輯、動態條件、IDE 型別輔助 | 完整 Python 靈活性；IDE 補全 |
| Site Manifest（YAML）| 單純拓撲宣告、GitOps、多環境切換 | 可版控 config；非工程師可讀 |
| `from_manifest` 後接 chain | 混合需求 | 拓撲 YAML 化 + 細節程式碼化 |

> [!tip] 建議用法
> 把「設備清單 + 策略清單 + reconciler 清單」放 YAML（拓撲宣告），把「保護規則 + context mapping + command mapping」留在 Python Builder chain（業務邏輯），兩者透過 `from_manifest(...).protect(...).map_context(...).build()` 結合。

## Gotchas

> [!warning] kind 須先註冊
> `from_manifest()` 載入時，manifest 中的每個 `kind` 值必須已在 `device_type_registry` / `strategy_type_registry` 中存在，否則 `ConfigurationError`。確保在 import 模組時 `@register_device_type` decorator 已執行（例如在主程式入口 `import` 對應模組）。

> [!note] labels 目前僅作資訊用途
> `ManifestMetadata.labels` 在 v0.9.0 不影響任何邏輯，僅供日誌識別與未來 Admission Validator 使用。

## 相關頁面

- [[Operator Pattern]] — Reconciler Protocol 設計原則與三個實作對照
- [[Reconciliation Pattern]] — v0.8.1 引入的調和器模式詳細說明
- [[Command Refresh]] — `CommandRefreshService` 使用指南
- [[SystemController]] — 系統控制器 API 參考
- [[Import Paths]] — 新增符號的完整 import 路徑
