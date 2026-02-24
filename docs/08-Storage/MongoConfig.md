---
tags:
  - type/config
  - layer/storage
  - status/complete
source: csp_lib/mongo/client.py
---

# MongoConfig

MongoDB 連線配置，隸屬於 [[_MOC Storage|Storage 模組]]。

## 概述

`MongoConfig` 是一個 frozen dataclass，用於定義 MongoDB 連線參數。支援兩種模式：

- **Standalone**：單機模式，使用 `host` / `port`
- **Replica Set**：副本集模式，使用 `replica_hosts` / `replica_set`

當同時提供 `replica_hosts` 和 `replica_set` 時自動切換為 Replica Set 模式。

## 參數表

| 參數 | 預設 | 說明 |
|------|------|------|
| `host` | `"localhost"` | 主機位址（Standalone） |
| `port` | `27017` | 連接埠（Standalone） |
| `replica_hosts` | `None` | 副本集主機列表 |
| `replica_set` | `None` | 副本集名稱 |
| `username` / `password` | `None` | 驗證資訊 |
| `auth_source` | `"admin"` | 驗證資料庫 |
| `auth_mechanism` | `None` | 驗證機制（例如 `"MONGODB-X509"`） |
| `tls` | `False` | 啟用 TLS |
| `tls_cert_key_file` | `None` | 客戶端憑證 |
| `tls_ca_file` | `None` | CA 憑證 |
| `tls_allow_invalid_hostnames` | `False` | 是否允許無效主機名 |
| `direct_connection` | `True` | 直連模式 |
| `server_selection_timeout_ms` | `None` | Server Selection 超時（毫秒） |
| `connect_timeout_ms` | `None` | 連線超時（毫秒） |
| `socket_timeout_ms` | `None` | Socket 讀寫超時（毫秒） |

## 使用範例

### Standalone

```python
from csp_lib.mongo import MongoConfig, create_mongo_client

config = MongoConfig(host="localhost", port=27017)
client = create_mongo_client(config)
db = client["my_database"]
```

### Standalone + X.509

```python
config = MongoConfig(
    host="mongo.example.com",
    port=27017,
    tls=True,
    tls_cert_key_file="/path/to/client.pem",
    tls_ca_file="/path/to/ca.crt",
    auth_mechanism="MONGODB-X509",
)
```

### Replica Set

```python
config = MongoConfig(
    replica_hosts=("rs1:27017", "rs2:27017", "rs3:27017"),
    replica_set="myReplicaSet",
    username="user",
    password="password",
)
```

## 工廠函式

`create_mongo_client(config) -> AsyncIOMotorClient`：根據配置自動選擇 Standalone 或 Replica Set 模式建立客戶端。

## 相關頁面

- [[MongoBatchUploader]] — 使用 MongoDB 客戶端進行批次上傳
- [[_MOC Storage]] — Storage 模組總覽
