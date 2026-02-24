---
tags:
  - type/class
  - layer/storage
  - status/complete
source: csp_lib/redis/client.py
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

## 連線管理

| 方法 | 說明 |
|------|------|
| `connect()` | 建立 Redis 連線（自動選擇 Standalone / Sentinel） |
| `disconnect()` | 關閉 Redis 連線 |
| `is_connected` | 是否已連線 |
| `is_sentinel_mode` | 是否為 Sentinel 模式 |

支援 `async with` context manager 自動管理連線。

## 操作 API

### Hash 操作

| 方法 | 說明 |
|------|------|
| `hset(name, mapping)` | 設定 Hash 欄位（值自動 JSON 序列化） |
| `hgetall(name)` | 取得 Hash 所有欄位（值自動 JSON 反序列化） |
| `hdel(name, *keys)` | 刪除 Hash 欄位 |

### String 操作

| 方法 | 說明 |
|------|------|
| `set(name, value, ex=None)` | 設定字串值（可設定過期秒數） |
| `get(name)` | 取得字串值 |

### Set 操作

| 方法 | 說明 |
|------|------|
| `sadd(name, *values)` | 新增 Set 成員 |
| `srem(name, *values)` | 移除 Set 成員 |
| `smembers(name)` | 取得 Set 所有成員 |

### Pub/Sub

| 方法 | 說明 |
|------|------|
| `publish(channel, message)` | 發布訊息到 channel |

### Key 操作

| 方法 | 說明 |
|------|------|
| `delete(*names)` | 刪除 Key |
| `exists(*names)` | 檢查 Key 是否存在 |
| `expire(name, seconds)` | 設定 Key 過期時間 |

## 使用範例

```python
from csp_lib.redis import RedisClient

client = RedisClient(config)
await client.connect()

# Hash operations
await client.hset("device:001", "voltage", "220.5")
value = await client.hget("device:001", "voltage")
all_fields = await client.hgetall("device:001")

# String operations
await client.set("key", "value", ex=60)
value = await client.get("key")

# Pub/Sub
await client.publish("channel", "message")
async for message in client.subscribe("channel"):
    print(message)

# Key operations
await client.delete("key")
await client.expire("key", 300)
exists = await client.exists("key")

await client.disconnect()
```

## 相關頁面

- [[RedisConfig]] — 連線配置
- [[TLSConfig]] — TLS 配置
- [[StateSyncManager]] — 使用 RedisClient 進行狀態同步
- [[_MOC Storage]] — Storage 模組總覽
