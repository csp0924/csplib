---
tags:
  - type/config
  - layer/storage
  - status/complete
source: csp_lib/redis/config.py
---

# RedisConfig

Redis 連線配置，隸屬於 [[_MOC Storage|Storage 模組]]。

## 概述

`RedisConfig` 是一個 frozen dataclass，用於定義 Redis 連線參數。支援兩種模式：

- **Standalone**：單機模式，使用 `host` / `port`
- **Sentinel**：高可用模式，使用 `sentinels` / `sentinel_master`

當同時提供 `sentinels` 和 `sentinel_master` 時自動切換為 Sentinel 模式。

## 參數表

| 參數 | 預設 | 說明 |
|------|------|------|
| `host` | `"localhost"` | Redis 主機位址（Standalone） |
| `port` | `6379` | Redis 連接埠（Standalone） |
| `password` | `None` | Redis 密碼 |
| `sentinels` | `None` | Sentinel 節點列表 `((host, port), ...)` |
| `sentinel_master` | `None` | Sentinel 監控的 master 名稱 |
| `sentinel_password` | `None` | Sentinel 本身的密碼 |
| `tls_config` | `None` | [[TLSConfig]] TLS 配置 |
| `socket_timeout` | `None` | Socket 讀寫超時（秒） |
| `socket_connect_timeout` | `None` | Socket 連線超時（秒） |
| `retry_on_timeout` | `False` | 超時時是否重試 |

## 使用範例

### Standalone

```python
from csp_lib.redis import RedisConfig

config = RedisConfig(host="localhost", port=6379, password="secret")
```

### Sentinel

```python
config = RedisConfig(
    sentinels=(("sentinel1", 26379), ("sentinel2", 26379)),
    sentinel_master="mymaster",
    password="redis_password",
    sentinel_password="sentinel_password",
)
```

### TLS

```python
from csp_lib.redis import RedisConfig, TLSConfig

config = RedisConfig(
    host="redis.example.com",
    tls_config=TLSConfig(
        ca_certs="/path/to/ca.crt",
        certfile="/path/to/client.crt",  # For mTLS
        keyfile="/path/to/client.key",
    ),
)
```

## 相關頁面

- [[RedisClient]] — 使用 RedisConfig 建立客戶端
- [[TLSConfig]] — TLS 連線配置
- [[_MOC Storage]] — Storage 模組總覽
