---
tags: [type/concept, status/complete]
updated: 2026-04-04
version: 0.6.1
---
# Design Patterns

> csp_lib 設計模式總覽

## 模式一覽表

| 模式 | 應用位置 | 說明 |
|------|---------|------|
| Strategy | Controller 全部策略 | 可插拔的控制演算法，統一 `execute()` 介面 |
| Command | [[Command]] dataclass | 不可變命令物件，安全跨 async 傳遞 |
| Observer | [[DeviceEventEmitter]] | 設備事件的發布/訂閱，async Queue-based |
| Chain of Responsibility | [[ProtectionGuard]] | 多個保護規則依序套用 |
| Pipeline | [[ProcessingPipeline]] | Transform 步驟串接處理 |
| Mixin | [[AlarmMixin]], [[WriteMixin]] | 設備功能解耦 |
| Facade | [[UnifiedDeviceManager]] | 整合所有子管理器的統一介面 |
| Template Method | [[AsyncLifecycleMixin]] | `_on_start()` / `_on_stop()` 由子類覆寫 |
| Singleton (引用計數) | RTU/SharedTCP Client | 同一 port 共享連線，引用計數管理生命週期 |
| Protocol (Structural) | AlarmRepository, ValueValidator, DeviceProtocol, EventDrivenOverride | Python Protocol 定義介面契約 |
| Registry | [[DeviceRegistry]] | Trait-based 雙索引設備查詢 |
| CommandProcessor Pipeline | [[CommandProcessor]], [[PowerCompensator]] | Post-Protection 命令處理管線，支援功率補償等擴展 |
| Builder | [[SystemControllerConfigBuilder]] | Fluent Builder API 建構 SystemControllerConfig |
| Delta-based Clamping | [[CascadingStrategy]] | 只縮放增量功率，保護高優先策略的分配 |

## 各模式詳解

### Strategy 模式

**應用位置**：`csp_lib.controller.strategies`

所有控制策略繼承自 [[Strategy]] ABC，實作統一的 `execute(context) -> Command` 介面。這使得策略可以在執行時期動態切換，而不影響呼叫端程式碼。

相關類別：[[PQModeStrategy]]、[[PVSmoothStrategy]]、[[QVStrategy]]、[[FPStrategy]]、[[IslandModeStrategy]]、[[ScheduleStrategy]]、[[StopStrategy]]、[[BypassStrategy]]

### Command 模式

**應用位置**：`csp_lib.controller.core.command`

[[Command]] 是一個 frozen dataclass，封裝了控制策略的輸出（`p_target`、`q_target` 等）。不可變性確保命令物件能安全地跨 async 邊界傳遞，不會產生競爭條件。

### Observer 模式

**應用位置**：`csp_lib.equipment.device.events`

[[DeviceEventEmitter]] 實作了基於 `asyncio.Queue` 的發布/訂閱模式。設備透過 `emit()` 發射事件，訂閱者透過 `on()` 註冊處理器。事件在背景 worker 中順序處理，避免阻塞讀取循環。

詳見 [[Event System]]。

### Chain of Responsibility 模式

**應用位置**：`csp_lib.controller.system.protection`

[[ProtectionGuard]] 將多個保護規則（[[SOCProtection]]、[[ReversePowerProtection]]、[[SystemAlarmProtection]]）串成鏈，依序套用至 [[Command]]。每個規則可以修改或攔截命令。

### Pipeline 模式

**應用位置**：`csp_lib.equipment.core.pipeline`

[[ProcessingPipeline]] 將多個 Transform 步驟串接，依序處理設備讀取的原始值。支援的 Transform 包括 [[ScaleTransform]]、[[BitExtractTransform]]、EnumMap 等共 10 種。

### Mixin 模式

**應用位置**：`csp_lib.equipment.device.mixins`

將 [[AsyncModbusDevice]] 的功能拆分為獨立 Mixin：
- [[AlarmMixin]] — 告警評估與狀態管理
- [[WriteMixin]] — 驗證寫入與回讀確認

### Facade 模式

**應用位置**：`csp_lib.manager.unified`

[[UnifiedDeviceManager]] 組合了 [[DeviceManager]]、[[AlarmPersistenceManager]]、[[DataUploadManager]]、[[WriteCommandManager]]、[[StateSyncManager]]，提供統一的管理介面。

### Template Method 模式

**應用位置**：`csp_lib.core.lifecycle`

[[AsyncLifecycleMixin]] 定義了 `start()` / `stop()` 的固定流程，子類只需覆寫 `_on_start()` 和 `_on_stop()` 鉤子方法。

詳見 [[Async Patterns]]。

### Singleton (引用計數) 模式

**應用位置**：`csp_lib.modbus.clients`

RTU 和 SharedTCP 客戶端使用引用計數確保同一串口或 IP 只建立一個連線。當最後一個使用者釋放時，連線才會真正關閉。

### Protocol (Structural) 模式

**應用位置**：多處

使用 Python `Protocol` 類別定義介面契約，實現鬆耦合。無需繼承即可滿足介面要求。csp_lib 中廣泛使用的 Protocol 範例：

| Protocol | 定義位置 | 用途 |
|---------|---------|------|
| `AlarmRepository` | `csp_lib.manager.alarm` | 告警儲存後端抽象 |
| `ValueValidator` | `csp_lib.equipment.core` | 寫入值驗證器 |
| `DeviceProtocol` | `csp_lib.equipment.device` | 通用設備介面（v0.4.2） |
| `EventDrivenOverride` | `csp_lib.controller.system` | 事件驅動覆蓋協定（v0.4.2） |
| `LoadCircuitProtocol` | `csp_lib.controller.strategies` | 負載迴路控制（v0.4.2） |
| `GridControllerProtocol` | `csp_lib.controller` | 網格控制器介面 |
| `CommandProcessor` | `csp_lib.controller.core` | Post-Protection 命令處理管線（v0.5+） |
| `FFTableRepository` | `csp_lib.controller.compensator` | FF 表持久化介面（v0.5+） |

`DeviceProtocol` 的重要性在於：它讓 Integration 層的 [[DeviceRegistry]]、[[ContextBuilder]] 等元件可以統一處理 [[AsyncModbusDevice]] 和 [[AsyncCANDevice]]，無需關心底層通訊協定。

```python
from csp_lib.equipment.device import DeviceProtocol

def process_device(device: DeviceProtocol) -> None:
    # 適用於任何實現 DeviceProtocol 的設備
    values = device.latest_values
    device_id = device.device_id
```

### Registry 模式

**應用位置**：`csp_lib.integration.registry`

[[DeviceRegistry]] 提供 Trait-based 的雙索引設備查詢，支援以 `device_id` 或 `trait`（如 `"pcs"`、`"bms"`）查找設備。

### CommandProcessor Pipeline 模式

**應用位置**：`csp_lib.controller.core.processor`

[[CommandProcessor]] 是一個 `@runtime_checkable Protocol`，定義在 [[ProtectionGuard]] 和 [[CommandRouter]] 之間的 post-protection 處理管線。每個 processor 接收經保護鏈處理後的 [[Command]] 與 [[StrategyContext]]，回傳處理後的 Command。

典型用途：功率補償、命令日誌、審計追蹤。

```python
# 執行流程
# Strategy.execute() → ProtectionGuard.apply()
#   → [CommandProcessor 1] → [CommandProcessor 2] → ...
#   → CommandRouter.route()

class MyCompensator:
    async def process(self, command: Command, context: StrategyContext) -> Command:
        compensated_p = self._compensate(command.p_target)
        return command.with_p(compensated_p)

config = SystemControllerConfig(
    post_protection_processors=[MyCompensator()],
)
```

內建實作：[[PowerCompensator]]（前饋 + 積分閉環功率補償）、[[FFCalibrationStrategy]]（FF 表步進校準）。

### Builder 模式

**應用位置**：`csp_lib.integration.system_controller`

[[SystemControllerConfigBuilder]] 提供 Fluent Builder API，讓使用者透過鏈式呼叫逐步建構 [[SystemControllerConfig]]：

```python
config = (
    SystemControllerConfig.builder()
    .system_base(p_base=1000)
    .map_context(point_name="soc", target="soc", device_id="bms_001")
    .map_command(field="p_target", trait="pcs", point_name="p_setpoint")
    .protect(SOCProtection(soc_config))
    .processor(compensator)
    .build()
)
```

### Delta-based Clamping 模式

**應用位置**：`csp_lib.controller.system.cascading`

[[CascadingStrategy]] 在功率級聯分配時，只縮放增量功率（delta），保護高優先級策略已分配的功率不被削減。

## 相關頁面

- [[Layered Architecture]] — 各模式在架構中的位置
- [[Data Flow]] — 模式在資料流中的運作
- [[Async Patterns]] — 非同步相關模式
- [[Event System]] — Observer 模式深入說明
- [[_MOC Architecture]] — 返回架構索引
