---
tags:
  - type/class
  - layer/alarm
  - status/complete
source: csp_lib/alarm/redis_adapter.py
created: 2026-04-17
updated: 2026-04-17
version: ">=0.8.2"
---

# Redis Adapter

`RedisAlarmPublisher` / `RedisAlarmSource` — 將 `AlarmAggregator` 與 Redis pub/sub 串接。

> [!note] 需要 `csp_lib[redis]` extra
> ```bash
> pip install "csp0924_lib[redis]"
> ```

> [!info] 回到 [[_MOC Alarm]]

---

## 概述

| 類別 | 方向 | 說明 |
|------|------|------|
| `RedisAlarmPublisher` | 本機 → Redis | 訂閱 `AlarmAggregator.on_change` → 發佈到 Redis channel |
| `RedisAlarmSource` | Redis → 本機 | 訂閱 Redis channel → 透過 `mark_source` 注入 `AlarmAggregator` |

兩者均繼承 `AsyncLifecycleMixin`，以 `async with` 管理生命週期。

---

## Quick Example

```python
import asyncio
from redis.asyncio import Redis

from csp_lib.alarm import AlarmAggregator, RedisAlarmPublisher, RedisAlarmSource

async def main() -> None:
    redis = Redis.from_url("redis://localhost:6379")

    # Publisher：本機聚合器 → Redis
    local_agg = AlarmAggregator()
    local_agg.bind_device(pcs_device)
    publisher = RedisAlarmPublisher(
        local_agg,
        redis,
        channel="gateway:alarm",
    )

    # Source：Redis → 遠端聚合器
    remote_agg = AlarmAggregator()
    remote_agg.on_change(lambda active: print(f"遠端告警：{active}"))
    source = RedisAlarmSource(
        remote_agg,
        redis,
        channel="gateway:alarm",
        name="node_1",
    )

    async with publisher, source:
        await asyncio.sleep(3600)  # 運行 1 小時

asyncio.run(main())
```

---

## RedisAlarmPublisher

### 建構參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `aggregator` | `AlarmAggregator` | — | 要訂閱的聚合器 |
| `redis_client` | `redis.asyncio.Redis` | — | 已建立的 Redis client |
| `channel` | `str` | — | 發佈目標 channel 名稱 |
| `payload_builder` | `PayloadBuilder \| None` | `None` | 自訂 payload 構造器；省略使用預設 schema |

### Payload Schema（預設）

```json
{
    "type": "aggregated_alarm",
    "active": true,
    "sources": ["pcs_a", "gateway_wd"],
    "timestamp": "2026-04-17T00:00:00+00:00"
}
```

- `type`：固定值 `"aggregated_alarm"`
- `active`：布林，聚合後的告警旗標
- `sources`：目前 active 的 source 名稱列表（排序後）
- `timestamp`：UTC ISO 8601 格式

### 自訂 Payload Builder

```python
from csp_lib.alarm.redis_adapter import PayloadBuilder

def my_builder(active: bool, aggregator: AlarmAggregator) -> dict:
    return {
        "alarm": active,
        "node": "japan_node_1",
        "t": time.time(),
    }

publisher = RedisAlarmPublisher(agg, redis, "gateway:alarm", payload_builder=my_builder)
```

### 生命週期

| 事件 | 行為 |
|------|------|
| `_on_start` | 記住 event loop；向 aggregator 登錄 observer |
| `_on_stop` | 移除 observer；等待 pending publish task（最多 5 秒） |

> [!note] 非同步 publish
> Observer 是同步 callback。Publisher 在 callback 內以 `asyncio.create_task` 排程 async publish，保留 task 參照避免 GC。來自非 loop thread 時改用 `run_coroutine_threadsafe`。Publish 失敗僅 log warning，不 raise。

---

## RedisAlarmSource

### 建構參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `aggregator` | `AlarmAggregator` | — | 事件注入目標 |
| `redis_client` | `redis.asyncio.Redis` | — | Redis client |
| `channel` | `str` | — | 訂閱的 channel 名稱 |
| `name` | `str` | — | source 名稱（aggregator 內部 key，必填非空） |
| `event_parser` | `EventParser \| None` | `None` | 自訂 parser；省略讀取 `payload["active"]` |

### 自訂 Event Parser

```python
from csp_lib.alarm.redis_adapter import EventParser

def my_parser(payload: dict) -> bool:
    # 舊格式：payload["alarm"] 而非 payload["active"]
    return bool(payload.get("alarm", False))

source = RedisAlarmSource(agg, redis, "gateway:alarm", name="node_2", event_parser=my_parser)
```

### 生命週期

| 事件 | 行為 |
|------|------|
| `_on_start` | 建立 pubsub，訂閱 channel，啟動背景 listen task |
| `_on_stop` | 取消 task，unsubscribe，關閉 pubsub，呼叫 `aggregator.unbind(name)` |

---

## 型別別名（模組層級）

| 名稱 | 定義 | 說明 |
|------|------|------|
| `PayloadBuilder` | `Callable[[bool, AlarmAggregator], dict[str, Any]]` | 自訂 publish payload 構造器 |
| `EventParser` | `Callable[[dict[str, Any]], bool]` | 從 JSON payload 解出 active 旗標 |

---

## 相關連結

- [[AlarmAggregator]] — 告警聚合器
- [[_MOC Alarm]] — Alarm 模組索引
- [[AsyncLifecycleMixin]] — 生命週期基類
