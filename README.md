# CSP Library

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13%2B-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-0.7.1-blue.svg)](CHANGELOG.md)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/csp0924-lib?period=total&units=INTERNATIONAL_SYSTEM&left_color=GRAY&right_color=BLUE&left_text=downloads)](https://pepy.tech/projects/csp0924-lib)

CSP Common Library 是一個模組化的 Python 工具集，專為**能源管理系統**與**工業設備通訊**設計。

## 特點

- **8 層分層架構**：Core → Modbus/CAN → Equipment → Controller → Manager → Integration → Storage → Additional
- **Async-first**：所有設備 I/O 與管理器皆採用 asyncio
- **多協議支援**：Modbus TCP/RTU 與 CAN Bus 雙協議設備抽象
- **策略引擎**：PQ/QV/FP/Droop/Island/PVSmooth/LoadShedding/RampStop 等 10+ 內建策略
- **功率補償**：前饋 + 積分閉環補償（PowerCompensator），含 FF Table 自動學習
- **動態保護**：DynamicSOCProtection / GridLimitProtection 從 RuntimeParameters 即時讀取參數
- **功率分配**：Equal / Proportional / SOCBalancing 多機分配，含硬體限制 + 溢出轉移
- **Modbus TCP Gateway**：宣告式暫存器映射、寫入驗證、資料同步，對接 EMS/SCADA
- **韌性機制**：CircuitBreaker（指數退避 + jitter）+ RetryPolicy
- **Event-driven**：設備事件系統 + WeakRef 自動清理
- **Fluent Builder**：`SystemControllerConfig.builder()` 鏈式配置
- **按需安裝**：Optional dependencies 避免引入不必要的套件

## 安裝

```bash
# 基本安裝
pip install csp0924_lib

# 按需安裝
pip install csp0924_lib[modbus]     # Modbus 通訊
pip install csp0924_lib[can]        # CAN Bus 通訊
pip install csp0924_lib[mongo]      # MongoDB
pip install csp0924_lib[redis]      # Redis（含 Sentinel + TLS）
pip install csp0924_lib[monitor]    # 系統監控
pip install csp0924_lib[cluster]    # 分散式叢集
pip install csp0924_lib[gui]        # FastAPI Web GUI
pip install csp0924_lib[all]        # 所有功能
```

## 架構

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 8  Additional                                         │
│  Cluster · Monitor · Notification · ModbusServer · Gateway   │
│  Statistics · GUI                                            │
├──────────────────────────────┬──────────────────────────────┤
│  Layer 7  Storage            │  Layer 6  Integration         │
│  MongoDB · Redis             │  Registry · SystemController  │
│                              │  ContextBuilder · CommandRouter│
├──────────────────────────────┤  Distributor · Orchestrator   │
│  Layer 5  Manager            ├──────────────────────────────┤
│  Unified · Alarm · Command   │  Layer 4  Controller          │
│  DataUpload · StateSync      │  Strategies · Executor        │
│                              │  Protection · Compensator     │
├──────────────────────────────┴──────────────────────────────┤
│  Layer 3  Equipment                                          │
│  AsyncModbusDevice · Points · Alarms · Transport · Pipeline  │
├─────────────────────────────────────────────────────────────┤
│  Layer 2  Modbus / CAN                                       │
│  DataTypes · Codec · Clients (TCP/RTU/Shared) · CAN Bus      │
├─────────────────────────────────────────────────────────────┤
│  Layer 1  Core                                               │
│  Logging · Lifecycle · Errors · Health · Resilience           │
│  RuntimeParameters                                           │
└─────────────────────────────────────────────────────────────┘

依賴方向：下層 → 上層（下層不可 import 上層）
```

## Quick Start

```python
import asyncio
from csp_lib.modbus import PymodbusTcpClient, ModbusTcpConfig, Float32, UInt16
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig

device = AsyncModbusDevice(
    config=DeviceConfig(device_id="inverter_001", unit_id=1),
    client=PymodbusTcpClient(ModbusTcpConfig(host="192.168.1.100")),
    always_points=[
        ReadPoint(name="voltage", address=0, data_type=Float32()),
        ReadPoint(name="power", address=2, data_type=UInt16()),
    ],
)

async def main():
    async with device:
        values = await device.read_all()
        print(f"Voltage: {values['voltage']}V, Power: {values['power']}W")

asyncio.run(main())
```

更多範例見 [`examples/`](examples/) 目錄。

## 模組總覽

| 層 | 模組 | 說明 | 文件 |
|----|------|------|------|
| L1 | [`core`](docs/02-Core/) | Logging · Lifecycle · Errors · Health · Resilience · RuntimeParameters | [→](docs/02-Core/) |
| L2 | [`modbus`](docs/03-Modbus/) | 資料型別 · Codec · TCP/RTU/Shared 客戶端 | [→](docs/03-Modbus/) |
| L2 | [`can`](docs/03-CAN/) | CAN Bus 客戶端 · 配置 · 例外 | [→](docs/03-CAN/) |
| L3 | [`equipment`](docs/04-Equipment/) | AsyncModbusDevice · Points · Alarms · Transport · Transforms | [→](docs/04-Equipment/) |
| L4 | [`controller`](docs/05-Controller/) | 10+ 策略 · Executor · Protection · Compensator · Calibration | [→](docs/05-Controller/) |
| L5 | [`manager`](docs/07-Manager/) | Unified · Alarm · Command · DataUpload · StateSync | [→](docs/07-Manager/) |
| L6 | [`integration`](docs/06-Integration/) | Registry · SystemController · ContextBuilder · CommandRouter · Distributor | [→](docs/06-Integration/) |
| L7 | [`mongo`](docs/08-Storage/) | MongoConfig · MongoBatchUploader | [→](docs/08-Storage/) |
| L7 | [`redis`](docs/08-Storage/) | RedisClient（Standalone/Sentinel/TLS）· Pub/Sub | [→](docs/08-Storage/) |
| L8 | [`cluster`](docs/09-Cluster/) | Leader Election · State Sync · HA Controller | [→](docs/09-Cluster/) |
| L8 | [`monitor`](docs/10-Monitor/) | 系統指標收集 · 告警評估 · Redis 發佈 | [→](docs/10-Monitor/) |
| L8 | [`notification`](docs/11-Notification/) | 多通道告警分發（Telegram/LINE/自訂） | [→](docs/11-Notification/) |
| L8 | [`modbus_server`](docs/12-Modbus-Server/) | Modbus TCP 模擬伺服器（測試用） | [→](docs/12-Modbus-Server/) |
| L8 | [`modbus_gateway`](docs/12-Modbus-Server/) | Modbus TCP Gateway（EMS/SCADA 介面） | [→](docs/12-Modbus-Server/) |
| L8 | [`statistics`](docs/) | 能源統計（累計度數、運行時數） | — |
| L8 | [`gui`](docs/) | FastAPI Web 介面 | — |

## 控制流程

```
設備讀取 → ContextBuilder → StrategyContext
                                ↓
                    StrategyExecutor（策略由 ModeManager 決定）
                                ↓
                    Command → ProtectionGuard → CommandProcessor
                                ↓
                    PowerDistributor → CommandRouter → 設備寫入
```

## 範例

| 檔案 | 說明 |
|------|------|
| [`01_basic_device.py`](examples/01_basic_device.py) | 基本設備讀寫 |
| [`03_control_strategies.py`](examples/03_control_strategies.py) | 控制策略使用 |
| [`05_system_controller.py`](examples/05_system_controller.py) | SystemController 進階控制 |
| [`14_power_distributor.py`](examples/14_power_distributor.py) | 多機功率分配 |
| [`15_modbus_gateway.py`](examples/15_modbus_gateway.py) | Modbus TCP Gateway |
| [`demo_ess_dreg.py`](examples/demo_ess_dreg.py) | ESS Droop 調頻 + 補償 + 校準 |
| [`demo_full_system.py`](examples/demo_full_system.py) | 完整系統端到端整合 |

完整範例列表見 [`examples/`](examples/)。

## 開發

```bash
# 安裝所有依賴
uv sync --all-groups --all-extras

# 測試
uv run python -m pytest tests/ -v

# Lint + Format + Type Check
uv run ruff check .
uv run ruff format .
uv run mypy csp_lib/
```

## 授權

[Apache License 2.0](LICENSE) — Copyright 2024-2026 Cheng Sin Pang（鄭善淜）

## 引用

```bibtex
@software{csp_library,
  title = {CSP Library},
  author = {Cheng Sin Pang (鄭善淜)},
  year = {2024},
  url = {https://github.com/csp0924/csp_lib},
  version = {0.7.1},
  license = {Apache-2.0}
}
```

詳見 [CITATION.cff](CITATION.cff) · [CHANGELOG.md](CHANGELOG.md)
