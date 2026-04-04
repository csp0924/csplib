---
tags:
  - type/class
  - layer/storage
  - status/complete
source: csp_lib/redis/client.py
updated: 2026-04-04
version: 0.6.0
---

# RedisClient

非同步 Redis 客戶端封裝，隸屬於 [[_MOC Storage|Storage 模組]]。

## 概述

`RedisClient` 基於 `redis.asyncio` 提供連線管理與常用操作的封裝。支援 Standalone 與 Sentinel 兩種模式，並支援 [[TLSConfig|TLS]] 安全連線。

### 建立方式

| 方式 | 說明 |
|------|------|
| `RedisClient(host, port, ...)` | 直接建構（Standalone 模式） |
| `RedisClient.from_config(config)` | 從 [[RedisConfig]] 建立（推薦，自動選擇模式） |

## Quick Example

```python
from csp_lib.redis import RedisClient, RedisConfig

config = RedisConfig(host="localhost", port=6379)
client = RedisClient.from_config(config)

async with client:
    await client.hset("device:001", {"voltage": 220.5, "current": 10.2})
    data = await client.hgetall("device:001")
```

## 連線管理

| 方法 / 屬性 | 說明 |
|------|------|
| `connect()` | 建立 Redis 連線（自動選擇 Standalone / Sentinel） |
| `disconnect()` | 關閉 Redis 連線 |
| `is_connected` | 是否已連線（property） |
| `is_sentinel_mode` | 是否為 Sentinel 模式（property） |

支援 `async with` context manager 自動管理連線。

## 操作 API

### Hash 操作

| 方法 | 回傳 | 說明 |
|------|------|------|
| `hset(name, mapping)` | `int` | 設定 Hash 欄位（值自動 JSON 序列化） |
| `hgetall(name)` | `dict[str, Any]` | 取得 Hash 所有欄位（值自動 JSON 反序列化） |
| `hdel(name, *keys)` | `int` | 刪除 Hash 欄位 |

### String 操作

| 方法 | 回傳 | 說明 |
|------|------|------|
| `set(name, value, ex=None)` | `bool` | 設定字串值（可設定過期秒數） |
| `get(name)` | `str \| None` | 取得字串值 |

### Set 操作

| 方法 | 回傳 | 說明 |
|------|------|------|
| `sadd(name, *values)` | `int` | 新增 Set 成員 |
| `srem(name, *values)` | `int` | 移除 Set 成員 |
| `smembers(name)` | `set[str]` | 取得 Set 所有成員 |

### Pub/Sub

| 方法 | 回傳 | 說明 |
|------|------|------|
| `publish(channel, message)` | `int` | 發布訊息到 channel，回傳接收者數量 |
| `pubsub()` | `PubSub` | 取得 PubSub 實例，用於訂閱與監聽（*v0.6.0 新增*） |

> [!tip] `pubsub()` 用法
> `pubsub()` 回傳 `redis.asyncio.client.PubSub` 實例，支援 `subscribe()` / `psubscribe()` / `listen()` 等原生操作。

```python
ps = client.pubsub()
await ps.subscribe("channel:data")
async for msg in ps.listen():
    if msg["type"] == "message":
        print(msg["data"])
```

### Key 操作

| 方法 | 回傳 | 說明 |
|------|------|------|
| `delete(*names)` | `int` | 刪除 Key |
| `exists(*names)` | `int` | 檢查 Key 是否存在（回傳存在的數量） |
| `expire(name, seconds)` | `bool` | 設定 Key 過期時間 |
| `keys(pattern)` | `list[str]` | 取得匹配 pattern 的 Key 列表 |

### Scan 操作

*v0.6.0 新增*

| 方法 | 回傳 | 說明 |
|------|------|------|
| `scan(cursor=0, match=None, count=None)` | `tuple[int, list[str]]` | 增量掃描 Key |

> [!tip] `scan()` vs `keys()`
> `keys()` 會阻塞 Redis 直到掃描完成，不適合生產環境大量 Key 的場景。`scan()` 使用游標增量掃描，對 Redis 負載較小。

```python
# 掃描所有 device: 開頭的 key
cursor = 0
all_keys: list[str] = []
while True:
    cursor, keys = await client.scan(cursor=cursor, match="device:*", count=100)
    all_keys.extend(keys)
    if cursor == 0:
        break
```

## Sentinel TLS 支援

*v0.6.0 新增*

Sentinel 模式下，[[TLSConfig]] 會同時套用至 Sentinel 連線與 Master 連線。透過 [[RedisConfig]] 的 `tls_config` 欄位統一配置：

```python
from csp_lib.redis import RedisClient, RedisConfig, TLSConfig

config = RedisConfig(
    sentinels=(("sentinel1", 26379), ("sentinel2", 26379)),
    sentinel_master="mymaster",
    password="redis_password",
    sentinel_password="sentinel_password",
    tls_config=TLSConfig(
        ca_certs="/path/to/ca.crt",
        certfile="/path/to/client.crt",
        keyfile="/path/to/client.key",
    ),
)

client = RedisClient.from_config(config)
await client.connect()  # Sentinel 與 Master 皆使用 TLS
```

## 使用範例

### Standalone

```python
from csp_lib.redis import RedisClient

client = RedisClient(host="localhost", port=6379, password="secret")
await client.connect()

await client.set("key", "value", ex=60)
value = await client.get("key")

await client.disconnect()
```

### 使用 Config（推薦）

```python
from csp_lib.redis import RedisClient, RedisConfig, TLSConfig

config = RedisConfig(
    host="redis.example.com",
    port=6379,
    password="secret",
    tls_config=TLSConfig(ca_certs="/path/to/ca.crt"),
)
client = RedisClient.from_config(config)

async with client:
    await client.hset("device:001", {"voltage": 220.5})
    data = await client.hgetall("device:001")
```

### Sentinel

```python
config = RedisConfig(
    sentinels=(("sentinel1", 26379), ("sentinel2", 26379)),
    sentinel_master="mymaster",
    password="redis_password",
)
client = RedisClient.from_config(config)
await client.connect()
```

## 相關頁面

- [[RedisConfig]] — 連線配置
- [[TLSConfig]] — TLS 配置
- [[StateSyncManager]] — 使用 RedisClient 進行狀態同步
- [[_MOC Storage]] — Storage 模組總覽
