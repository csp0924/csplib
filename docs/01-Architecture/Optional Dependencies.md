---
tags: [type/concept, status/complete]
---
# Optional Dependencies

> 可選依賴架構與惰性載入模式

## 依賴樹

csp_lib 核心套件零外部依賴，所有通訊與儲存功能透過可選依賴安裝：

```
csp_lib (核心，零外部依賴)
    │
    ├── csp_lib[modbus]   →  pymodbus>=3.0.0        (Modbus 通訊)
    ├── csp_lib[can]      →  python-can>=4.0         (CAN Bus 通訊)
    ├── csp_lib[mongo]    →  motor>=3.0.0            (MongoDB 非同步客戶端)
    ├── csp_lib[redis]    →  redis>=5.0.0            (Redis 非同步客戶端)
    ├── csp_lib[monitor]  →  psutil>=5.9.0           (系統監控)
    ├── csp_lib[cluster]  →  etcetra>=0.1.0          (etcd 叢集協調)
    ├── csp_lib[gui]      →  fastapi, uvicorn, pyyaml (Web GUI)
    └── csp_lib[all]      →  以上全部
```

## 安裝方式

```bash
# 僅安裝核心（資料模型、控制策略、事件系統）
pip install csp0924_lib

# 安裝 Modbus 通訊支援
pip install csp0924_lib[modbus]

# 安裝 CAN Bus 通訊支援（v0.4.2）
pip install csp0924_lib[can]

# 安裝 MongoDB 儲存支援
pip install csp0924_lib[mongo]

# 安裝 Redis 即時同步支援
pip install csp0924_lib[redis]

# 安裝系統監控支援
pip install csp0924_lib[monitor]

# 安裝叢集高可用支援
pip install csp0924_lib[cluster]

# 安裝 Web GUI 支援
pip install csp0924_lib[gui]

# 安裝全部功能
pip install csp0924_lib[all]
```

## 各依賴的用途

| 可選依賴 | 第三方套件 | 提供功能 | 對應模組 |
|---------|-----------|---------|---------|
| `modbus` | `pymodbus>=3.0.0` | Modbus TCP/RTU 非同步通訊 | [[_MOC Modbus]] |
| `can` | `python-can>=4.0` | CAN Bus 幀收發（v0.4.2） | [[_MOC CAN]] |
| `mongo` | `motor>=3.0.0` | MongoDB 非同步客戶端、批次上傳 | [[_MOC Storage]] |
| `redis` | `redis>=5.0.0` | Redis Hash/Set/Pub/Sub 操作 | [[_MOC Storage]] |
| `monitor` | `psutil>=5.9.0` | 系統資源監控 (CPU/RAM/Disk) | [[_MOC Monitor]] |
| `cluster` | `etcetra>=0.1.0` | etcd 叢集協調、Leader 選舉 | [[_MOC Cluster]] |
| `gui` | `fastapi, uvicorn, pyyaml` | Web API / GUI 服務 | (gui module) |

## 惰性載入模式 (Lazy Import)

csp_lib 使用惰性載入確保未安裝的可選依賴不會在 import 時就引發錯誤。只有在真正使用到相關功能時才會載入對應的第三方套件。

### 載入時機

| 模組 | 延遲載入的套件 | 觸發時機 |
|------|--------------|---------|
| `csp_lib.modbus.clients` | `pymodbus` | 建立 Modbus 客戶端實例時 |
| `csp_lib.can.clients` | `python-can` | 建立 CAN 客戶端實例時 |
| `csp_lib.mongo` | `motor` | 建立 MongoDB 客戶端或上傳器時 |
| `csp_lib.redis` | `redis` | 建立 Redis 客戶端時 |
| `csp_lib.monitor` | `psutil` | 建立系統監控實例時 |

### 設計優點

1. **漸進式採用** — 使用者可以只安裝需要的功能，例如僅使用控制策略模組時不需安裝 pymodbus
2. **快速啟動** — 不載入未使用的重型依賴，減少 import 時間
3. **清晰的錯誤訊息** — 使用未安裝的功能時，會提示使用者安裝對應的可選依賴
4. **測試友好** — CI 環境僅安裝測試所需的依賴

### 核心零依賴的範圍

即使不安裝任何可選依賴，以下功能仍可正常使用：

- **資料模型** — [[ReadPoint]]、[[WritePoint]]、[[AlarmDefinition]] 等所有 dataclass
- **控制策略** — 所有 [[Strategy]] 子類別的邏輯運算
- **事件系統** — [[DeviceEventEmitter]] 與所有 Payload 類別
- **資料轉換** — [[ProcessingPipeline]] 與所有 Transform
- **生命週期** — [[AsyncLifecycleMixin]]
- **日誌** — loguru-based 日誌系統

## 相關頁面

- [[Layered Architecture]] — 各層與依賴的對應關係
- [[_MOC Modbus]] — Modbus 模組（需 `pymodbus`）
- [[_MOC Storage]] — 儲存模組（需 `motor` / `redis`）
- [[_MOC Architecture]] — 返回架構索引
