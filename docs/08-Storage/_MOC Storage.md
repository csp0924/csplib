---
tags:
  - type/moc
  - layer/storage
  - status/complete
---

# Storage 模組總覽

MongoDB 與 Redis 非同步客戶端。

Storage 模組提供兩大儲存後端的非同步封裝：MongoDB（透過 motor）用於資料持久化與批次上傳，Redis（透過 redis.asyncio）用於即時狀態同步與 Pub/Sub。兩者皆為可選依賴，按需安裝。

## 安裝

```bash
pip install csp0924_lib[mongo]   # MongoDB 批次上傳
pip install csp0924_lib[redis]   # Redis 客戶端
pip install csp0924_lib[all]     # 所有功能
```

## 頁面索引

### MongoDB

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[MongoConfig]] | config | MongoDB 連線配置（Standalone / X.509 / Replica Set） |
| [[MongoBatchUploader]] | class | 批次上傳器（含 flush interval 與重試機制） |

### Redis

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[RedisConfig]] | config | Redis 連線配置（Standalone / Sentinel） |
| [[RedisClient]] | class | 非同步 Redis 客戶端（Hash / String / Pub/Sub / Key） |
| [[TLSConfig]] | config | Redis TLS 連線配置 |

## 相關模組

- 上游：[[_MOC Manager]] — Manager 層使用 Storage 進行資料持久化與狀態同步
