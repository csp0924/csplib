---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/state/sync.py
updated: 2026-04-23
version: ">=0.10.0"
---

# StateSyncManager

Redis 即時狀態同步管理器，隸屬於 [[_MOC Manager|Manager 模組]]。

## 概述

`StateSyncManager` 繼承自 [[DeviceEventSubscriber]]，自動將設備狀態同步至 Redis，並透過 Pub/Sub 通知前端。

### 職責

1. 訂閱 `AsyncModbusDevice` 的多種事件
2. `read_complete` → 更新 Hash + 發布 data channel
3. `connected` / `disconnected` → 更新 online 狀態 + 發布 status channel
4. `alarm_triggered` / `alarm_cleared` → 更新 alarms Set + 發布 alarm channel

## 建構參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `redis_client` | [[RedisClient]] | 必填 | Redis 客戶端實例 |
| `config` | `StateSyncConfig \| None` | `None` | 狀態同步配置（優先使用） |
| `state_ttl` | `int \| None` | `60` | 設備狀態 Hash TTL（秒），`config` 為 `None` 時使用 |
| `online_ttl` | `int \| None` | `60` | 連線狀態 TTL（秒），`config` 為 `None` 時使用 |
| `leader_gate` | [[LeaderGate]] `\| None`（kw-only） | `None` | Leader 閘門（v0.10.0）；非 leader 時所有事件 handler 早退，不寫 Redis |

### StateSyncConfig

`@dataclass(frozen=True, slots=True)` 配置。

> [!note] v0.10.0 新增 key_prefix / channel_prefix（PR #112）
> 多站共用同一 Redis 時，可用 prefix 隔離各站的 key/channel 空間。

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `state_ttl` | `int` | `60` | 設備狀態 Hash TTL（秒，必須 > 0） |
| `online_ttl` | `int` | `60` | 連線狀態 TTL（秒，必須 > 0） |
| `key_prefix` | `str` | `"device"` | Redis key 前綴（不可為空字串）；多站時設為 `"taiwan-s1.device"` 等 |
| `channel_prefix` | `str` | `"channel:device"` | Pub/Sub channel 前綴（不可為空字串） |

## Redis Key 結構

Key 實際格式：`"{key_prefix}:{device_id}:state"` 等（預設值同下表）。

| Key 格式（預設 prefix） | 型別 | TTL | 說明 |
|------------------------|------|-----|------|
| `device:{device_id}:state` | Hash | `state_ttl` | 所有點位最新值（Redis pipeline 批次寫入） |
| `device:{device_id}:online` | String | `online_ttl` | `"1"` 或 `"0"` |
| `device:{device_id}:alarms` | Set | 無 | 活躍告警 codes |

## Pub/Sub Channel

Channel 實際格式：`"{channel_prefix}:{device_id}:data"` 等（預設值同下表）。

| Channel 格式（預設 prefix） | 觸發事件 | 說明 |
|---------------------------|---------|------|
| `channel:device:{device_id}:data` | `read_complete` | 資料更新（JSON: timestamp + values） |
| `channel:device:{device_id}:status` | `connected` / `disconnected` | 連線狀態（JSON: online + timestamp） |
| `channel:device:{device_id}:alarm` | `alarm_triggered` / `alarm_cleared` | 告警事件（JSON: type + alarm + timestamp） |

## Redis Pipeline 批次寫入（v0.10.0）

`read_complete` 事件的 `_on_read_complete` handler 改為 Redis pipeline 批次執行：

1. `hset` + `expire`（state Hash）
2. `set` + `expire`（online String）
3. `publish`（data channel）

三個指令合為一個 pipeline，減少 round-trip 次數。

## 訂閱的事件

| 事件 | 處理 |
|------|------|
| `read_complete` | 更新 Hash + 刷新 online 心跳 + 發布 data channel |
| `connected` | 設定 `online=1` + 發布 status channel |
| `disconnected` | 設定 `online=0` + 發布 status channel |
| `alarm_triggered` | 新增至 alarms Set + 發布 alarm channel |
| `alarm_cleared` | 從 alarms Set 移除 + 發布 alarm channel |

## Quick Example

### 基本使用

```python
from csp_lib.redis import RedisClient
from csp_lib.manager.state import StateSyncManager, StateSyncConfig

redis_client = RedisClient("redis://localhost:6379")
await redis_client.connect()

config = StateSyncConfig(state_ttl=120, online_ttl=60)
state_manager = StateSyncManager(redis_client, config=config)
state_manager.subscribe(device)

# 設備事件自動同步至 Redis + Pub/Sub
# read_complete → device:dev_001:state (Hash) + channel:device:dev_001:data
# connected    → device:dev_001:online = "1"  + channel:device:dev_001:status
```

### 多站共用 Redis（key_prefix / channel_prefix）

```python
config = StateSyncConfig(
    state_ttl=60,
    online_ttl=60,
    key_prefix="taiwan-s1.device",          # Key:  taiwan-s1.device:{device_id}:state
    channel_prefix="taiwan-s1.channel:device",  # Ch:   taiwan-s1.channel:device:{device_id}:data
)
state_manager = StateSyncManager(redis_client, config=config)
```

### HA 部署（注入 leader_gate）

```python
from csp_lib.manager.base import AlwaysLeaderGate

# follower 節點不寫 Redis（只 subscribe 設備事件，handler 早退）
state_manager = StateSyncManager(redis_client, config=config, leader_gate=cluster_gate)
```

## 相關頁面

- [[DeviceEventSubscriber]] — 基底類別
- [[RedisClient]] — Redis 客戶端
- [[UnifiedDeviceManager]] — 自動串接狀態同步管理器
- [[LeaderGate]] — Leader 閘門 Protocol（v0.10.0）
