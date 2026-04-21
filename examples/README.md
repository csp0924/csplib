# csp_lib 範例學習指南

## 執行方式

所有範例均可直接執行，無需真實硬體。範例使用 `SimulationServer` 提供 Modbus TCP 模擬。

```bash
uv run python examples/01_hello_device.py
```

## 學習路徑

### 🟢 入門 (Beginner)

| # | 範例 | 學習目標 | 預計時間 |
|---|------|---------|---------|
| 01 | `01_hello_device.py` | Modbus 設備連線、讀寫、事件、告警 | 10 min |
| 02 | `02_device_template.py` | 設備模板、多設備批量管理 | 10 min |

### 🟡 初級 (Intermediate)

| # | 範例 | 學習目標 | 預計時間 |
|---|------|---------|---------|
| 03 | `03_control_strategies.py` | PQ/QV/FP 策略、StrategyExecutor、SystemBase | 15 min |
| 04 | `04_system_controller.py` | SystemController.builder()、DynamicSOCProtection、CommandRouter | 20 min |
| 05 | `05_device_manager.py` | UnifiedDeviceManager、batch_uploader、告警持久化 | 15 min |

### 🟠 進階 (Advanced)

| # | 範例 | 學習目標 | 預計時間 |
|---|------|---------|---------|
| 06 | `06_advanced_protection.py` | DynamicSOCProtection、EventDrivenOverride、RampStop | 20 min |
| 07 | `07_cascading_power.py` | PowerDistributor（多機分配）、CascadingStrategy（多策略組合） | 15 min |
| 08 | `08_custom_strategy.py` | 自定義控制策略（Strategy ABC + ConfigMixin） | 20 min |
| 09 | `09_custom_database.py` | BatchUploader Protocol、自定義資料庫後端 | 15 min |
| 10 | `10_capability_system.py` | Capability 聲明、CapabilityBinding、preflight_check、自動解析 | 20 min |

### 🔴 專家 (Expert)

| # | 範例 | 學習目標 | 預計時間 |
|---|------|---------|---------|
| 11 | `11_modbus_gateway.py` | EMS/SCADA Modbus TCP 閘道整合 | 20 min |
| 12 | `12_distributed_control.py` | GroupControllerManager 多群組分散式控制 | 20 min |
| 13 | `13_microgrid_simulation.py` | 完整微電網模擬 (PCS+BMS+Solar+Load+Meter) | 30 min |
| 14 | `14_logging_system.py` | v0.7.0 日誌系統 (LogFilter/SinkManager/LogContext) | 15 min |
| 15 | `15_runtime_parameters.py` | RuntimeParameters、CircuitBreaker | 15 min |
| 16 | `16_operator_pattern.py` | v0.9.0 Operator Pattern：Reconciler Protocol / SetpointDrift / SiteManifest / TypeRegistry | 20 min |
| 17 | `17_multi_unit_device.py` | v0.9.0 Multi-UnitID：per-point unit_id / PointGrouper 分桶 / used_unit_ids | 10 min |

## 架構概覽

```
Layer 8  Additional    cluster, monitor, notification, modbus_server, modbus_gateway, gui
Layer 7  Storage       mongo, redis
Layer 6  Integration   DeviceRegistry, ContextBuilder, CommandRouter, SystemController
Layer 5  Manager       DeviceManager, AlarmPersistenceManager, DataUploadManager
Layer 4  Controller    Strategies (PQ/QV/FP/...), StrategyExecutor, ModeManager
Layer 3  Equipment     AsyncModbusDevice, Points, Transforms, Alarms, ReadScheduler
Layer 2  Modbus        Data types, async clients (TCP/RTU/Shared), codec
Layer 1  Core          get_logger, AsyncLifecycleMixin, errors, RuntimeParameters
```

## 常見問題

**Port 5020 被佔用？** 修改範例中的 `SIM_PORT` 常數。

**模擬器如何自訂？** 參考 `13_microgrid_simulation.py`，使用 `MicrogridSimulator`。

**如何換成真實硬體？** 將 `SimulationServer` 替換為真實 IP 的 `PymodbusTcpClient`。
