---
tags:
  - type/config
  - layer/storage
  - status/complete
source: csp_lib/redis/client.py
---

# TLSConfig

Redis TLS 連線配置，隸屬於 [[_MOC Storage|Storage 模組]]。

## 概述

`TLSConfig` 是一個 frozen dataclass，用於配置 Redis 的 TLS/SSL 連線參數。支援單向 TLS（僅驗證伺服器）與雙向 TLS（mTLS，客戶端與伺服器互相驗證）。

## 參數表

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `ca_certs` | `str` | 必填 | CA 憑證檔案路徑 |
| `certfile` | `str \| None` | `None` | 客戶端憑證檔案路徑（雙向 TLS 用） |
| `keyfile` | `str \| None` | `None` | 客戶端私鑰檔案路徑（雙向 TLS 用） |
| `cert_reqs` | `Literal["required", "optional", "none"]` | `"required"` | 憑證驗證模式 |

### cert_reqs 模式

| 值 | 說明 |
|----|------|
| `"required"` | 必須驗證伺服器憑證（預設） |
| `"optional"` | 可選驗證 |
| `"none"` | 不驗證 |

## 驗證規則

- `certfile` 和 `keyfile` 必須同時提供或同時不提供
- 僅提供其一時拋出 `ValueError`

## API

| 方法 | 說明 |
|------|------|
| `to_ssl_context() -> ssl.SSLContext` | 建立配置好的 SSLContext 實例 |

## 使用範例

### 單向 TLS（僅驗證伺服器）

```python
from csp_lib.redis import TLSConfig

tls = TLSConfig(ca_certs="/path/to/ca.crt")
```

### 雙向 TLS（mTLS）

```python
tls = TLSConfig(
    ca_certs="/path/to/ca.crt",
    certfile="/path/to/client.crt",
    keyfile="/path/to/client.key",
)
```

### 搭配 RedisConfig

```python
from csp_lib.redis import RedisConfig, TLSConfig

config = RedisConfig(
    host="redis.example.com",
    tls_config=TLSConfig(
        ca_certs="/path/to/ca.crt",
        certfile="/path/to/client.crt",
        keyfile="/path/to/client.key",
    ),
)
```

## 相關頁面

- [[RedisConfig]] — 使用 TLSConfig 的 Redis 連線配置
- [[RedisClient]] — 使用 TLS 建立安全連線
- [[_MOC Storage]] — Storage 模組總覽
