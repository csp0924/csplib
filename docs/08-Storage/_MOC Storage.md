---
tags:
  - type/moc
  - layer/storage
  - status/complete
updated: 2026-04-18
version: ">=0.8.2"
---

# Storage 模組總覽

MongoDB 與 Redis 非同步客戶端。

Storage 模組提供兩大儲存後端的非同步封裝：MongoDB（透過 motor）用於資料持久化與批次上傳，Redis（透過 redis.asyncio）用於即時狀態同步與 Pub/Sub。兩者皆為可選依賴，按需安裝。

## 安裝

```bash
pip install csp0924_lib[mongo]                # MongoDB 批次上傳（motor）
pip install 'csp0924_lib[local-buffer]'       # 本地 SQLite 緩衝（SqliteBufferStore，aiosqlite，v0.8.2）
pip install 'csp0924_lib[mongo,local-buffer]' # MongoDB + SQLite 本地緩衝（完整功能）
pip install csp0924_lib[redis]                # Redis 客戶端
pip install csp0924_lib[all]                  # 所有功能
```

> [!note] v0.8.2 extras 異動
> `[mongo]` 已瘦身為純 `motor>=3.3.0`；`aiosqlite` 移至獨立 `[local-buffer]` extra。
> `pyproject.toml` 需手動更新（diff 見 [[LocalBufferedUploader#安裝需求]]）。

## 頁面索引

### MongoDB

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[MongoConfig]] | config | MongoDB 連線配置（Standalone / X.509 / Replica Set） |
| [[MongoBatchUploader]] | class | 批次上傳器（含 flush interval、閾值觸發與重試機制） |
| [[LocalBufferedUploader]] | class | 本地緩衝上傳器；backend-agnostic，透過 `LocalBufferStore` Protocol 插拔（v0.8.2） |

#### 本地緩衝（Local Buffer，v0.8.2）

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[LocalBufferStore]] | protocol | Backend-agnostic 儲存介面（10 個 async CRUD method）+ `BufferedRow` dataclass |
| [[SqliteBufferStore]] | class | `LocalBufferStore` 的 aiosqlite + WAL 實作（需 `csp_lib[local-buffer]`） |
| [[MongoBufferStore]] | class | `LocalBufferStore` 的第二個實作，本地 mongod 當 buffer backend（需 `csp_lib[mongo]`，適用雙 MongoDB 拓樸，v0.8.2） |

### Redis

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[RedisConfig]] | config | Redis 連線配置（Standalone / Sentinel） |
| [[RedisClient]] | class | 非同步 Redis 客戶端（Hash / String / Set / Pub/Sub / Scan / Key） |
| [[TLSConfig]] | config | Redis TLS 連線配置 |

## 相關模組

- 上游：[[_MOC Manager]] — Manager 層使用 Storage 進行資料持久化與狀態同步
