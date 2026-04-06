---
tags:
  - type/guide
  - layer/manager
  - status/complete
created: 2026-04-06
updated: 2026-04-06
version: ">=0.7.1"
---

# 自訂資料庫後端

本指南說明如何實作 `BatchUploader` Protocol，將設備資料上傳到 MongoDB 以外的自訂儲存後端（例如 InfluxDB、PostgreSQL、TimescaleDB 等），並整合到 `UnifiedDeviceManager`。

---

## 概觀

csp_lib Manager 層透過 `BatchUploader` Protocol 解耦儲存後端。只要實作兩個方法，任何儲存系統均可作為後端：

```
DataUploadManager
       ↓ 呼叫
BatchUploader Protocol  ←── 你的自訂實作（InfluxDB / PostgreSQL / ...）
       ↓ 或
MongoBatchUploader       ←── csp_lib 內建（MongoDB）
```

---

## Quick Example

以下是一個最簡的 `InMemoryUploader` 實作，適合測試或沒有外部資料庫的場景：

```python
import asyncio
from collections import defaultdict
from typing import Any
from csp_lib.manager import UnifiedConfig, UnifiedDeviceManager


class InMemoryUploader:
    """最簡 BatchUploader 實作 — 將文件存入記憶體字典"""

    def __init__(self) -> None:
        self._documents: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def register_collection(self, collection_name: str) -> None:
        # 可選：預先初始化 collection
        _ = self._documents[collection_name]

    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None:
        self._documents[collection_name].append(document)

    def get_documents(self, collection_name: str) -> list[dict[str, Any]]:
        return list(self._documents.get(collection_name, []))


async def main() -> None:
    uploader = InMemoryUploader()

    config = UnifiedConfig(
        alarm_repository=...,
        command_repository=...,
        mongo_uploader=uploader,   # 替換預設 MongoBatchUploader
        redis_client=None,
        notification_dispatcher=None,
    )

    manager = UnifiedDeviceManager(config)
    manager.register(device, collection_name="device_data")

    async with manager:
        await asyncio.sleep(10)

    docs = uploader.get_documents("device_data")
    print(f"收集到 {len(docs)} 筆資料")
```

---

## BatchUploader Protocol

`BatchUploader` 是 `@runtime_checkable` Protocol，只需實作以下兩個方法：

```python
from csp_lib.manager.base import BatchUploader

# Protocol 定義（僅供參考，不需繼承）
class BatchUploader(Protocol):
    def register_collection(self, collection_name: str) -> None:
        """
        預先宣告一個 collection 名稱。
        DataUploadManager 在 register() 時會呼叫此方法。
        Args:
            collection_name: 資料集合的名稱
        """
        ...

    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None:
        """
        將一份文件加入上傳佇列。
        DataUploadManager 在 read_complete 事件時呼叫此方法。
        Args:
            collection_name: 目標 collection 名稱
            document: 要上傳的資料字典
        """
        ...
```

| 方法 | 呼叫時機 | 說明 |
|------|---------|------|
| `register_collection(name)` | `manager.register(device, collection_name=...)` 時 | 可用於建立 table/measurement/collection |
| `async enqueue(name, doc)` | 每次設備 `read_complete` 事件 | 接收一份資料文件，可立即寫入或加入佇列 |

> [!note] Protocol 不需繼承
> Python Protocol 是結構性子型別，你的類別只需有相同簽名的方法，**不需要** `class MyUploader(BatchUploader)` 繼承。但加上繼承可讓 mypy 靜態檢查更嚴格。

---

## 實作自訂後端

### 範例：InfluxDB 後端

```python
import asyncio
from collections import defaultdict
from typing import Any

try:
    from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
    from influxdb_client.client.write_api_async import WriteApiAsync
    from influxdb_client.domain.write_precision import WritePrecision
    from influxdb_client import Point
except ImportError:
    raise ImportError("需要安裝 influxdb-client: pip install influxdb-client[async]")


class InfluxDBUploader:
    """
    InfluxDB 2.x 批次上傳器

    BatchUploader Protocol 實作，將設備資料寫入 InfluxDB measurement。
    每個 collection_name 對應一個 measurement。
    """

    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        bucket: str,
        *,
        flush_interval_ms: int = 5000,
    ) -> None:
        self._url = url
        self._token = token
        self._org = org
        self._bucket = bucket
        self._flush_interval_ms = flush_interval_ms
        self._client: InfluxDBClientAsync | None = None
        self._write_api: WriteApiAsync | None = None
        self._measurements: set[str] = set()

    async def start(self) -> None:
        """啟動連線（使用前需呼叫）"""
        self._client = InfluxDBClientAsync(
            url=self._url, token=self._token, org=self._org
        )
        self._write_api = self._client.write_api()

    async def stop(self) -> None:
        """關閉連線"""
        if self._client:
            await self._client.close()

    def register_collection(self, collection_name: str) -> None:
        """將 collection_name 記錄為 InfluxDB measurement 名稱"""
        self._measurements.add(collection_name)

    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None:
        """將文件轉換為 InfluxDB Point 並寫入"""
        if self._write_api is None:
            return

        # 取出時間戳（若有）
        ts = document.get("timestamp")

        # 建立 Point，所有數值型欄位作為 field
        point = Point(collection_name)
        if "device_id" in document:
            point = point.tag("device_id", document["device_id"])

        for key, value in document.items():
            if key in ("timestamp", "device_id"):
                continue
            if isinstance(value, (int, float)):
                point = point.field(key, value)
            elif isinstance(value, str):
                point = point.tag(key, value)

        if ts is not None:
            point = point.time(ts, WritePrecision.SECONDS)

        await self._write_api.write(
            bucket=self._bucket,
            org=self._org,
            record=point,
        )
```

### 範例：PostgreSQL / TimescaleDB 後端

```python
import asyncio
import json
from datetime import datetime
from typing import Any

try:
    import asyncpg
except ImportError:
    raise ImportError("需要安裝 asyncpg: pip install asyncpg")


class PostgreSQLUploader:
    """
    PostgreSQL / TimescaleDB 批次上傳器

    每個 collection_name 對應一張 table（自動建立）。
    文件以 JSONB 欄位儲存，保留最大彈性。
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._tables: set[str] = set()

    async def start(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn)

    async def stop(self) -> None:
        if self._pool:
            await self._pool.close()

    def register_collection(self, collection_name: str) -> None:
        """記錄 table 名稱（實際建表在首次寫入時懶執行）"""
        self._tables.add(collection_name)

    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None:
        if self._pool is None:
            return

        async with self._pool.acquire() as conn:
            # 懶建表
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS "{collection_name}" (
                    id        BIGSERIAL PRIMARY KEY,
                    ts        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    device_id TEXT,
                    data      JSONB NOT NULL
                )
            """)

            device_id = document.get("device_id")
            ts = document.get("timestamp")
            data_json = json.dumps({k: v for k, v in document.items()
                                    if k not in ("device_id", "timestamp")})

            await conn.execute(
                f'INSERT INTO "{collection_name}" (ts, device_id, data) VALUES ($1, $2, $3)',
                datetime.fromtimestamp(ts) if ts else None,
                device_id,
                data_json,
            )
```

---

## 整合到 UnifiedConfig

自訂 Uploader 完成後，傳入 `UnifiedConfig` 的 `mongo_uploader` 欄位（欄位名稱沿用，但接受任何 `BatchUploader`）：

```python
from csp_lib.manager import UnifiedConfig, UnifiedDeviceManager

influx = InfluxDBUploader(
    url="http://localhost:8086",
    token="my-token",
    org="my-org",
    bucket="csp_data",
)
await influx.start()

config = UnifiedConfig(
    alarm_repository=alarm_repo,
    command_repository=command_repo,
    mongo_uploader=influx,        # 傳入自訂後端
    redis_client=redis_client,
    notification_dispatcher=None,
)

manager = UnifiedDeviceManager(config)
manager.register(device, collection_name="pcs_data")

async with manager:
    await asyncio.sleep(3600)

await influx.stop()
```

---

## 內建替代實作

若不需要自訂後端，csp_lib 已提供以下開箱即用的替代方案（v0.6.1+）：

| 類別 | 說明 | 匯入路徑 |
|------|------|---------|
| `NullBatchUploader` | 丟棄所有文件（靜默） | `csp_lib.manager` |
| `InMemoryBatchUploader` | 存入記憶體字典（測試用） | `csp_lib.manager` |
| `MongoBatchUploader` | 完整 MongoDB 批次上傳（正式環境） | `csp_lib.mongo` |

```python
from csp_lib.manager import NullBatchUploader, InMemoryBatchUploader

# 不需要任何持久化
config = UnifiedConfig(mongo_uploader=NullBatchUploader(), ...)

# 測試用，可驗收資料
uploader = InMemoryBatchUploader()
config = UnifiedConfig(mongo_uploader=uploader, ...)
# ... 測試後
docs = uploader.get_documents("pcs_data")
assert len(docs) > 0
```

詳見 [[No MongoDB Setup]]。

---

## 常見問題

### Q: 需要實作 `start()` / `stop()` 嗎？

`BatchUploader` Protocol 只要求 `register_collection` 和 `enqueue`，**不強制**生命週期方法。
但若你的後端需要連線管理，建議自行新增 `start()` / `stop()` 並在 `async with manager:` 之前呼叫。

### Q: `enqueue` 是同步佇列還是直接寫入？

Protocol 僅要求 `async enqueue`，具體行為由你決定：
- 直接寫入（簡單，但高頻設備可能造成 DB 壓力）
- 加入本地佇列 + 背景批次刷新（類似 `MongoBatchUploader` 的做法）

對高頻設備（每秒多筆），建議實作批次緩衝。

### Q: 如何驗證自訂實作符合 Protocol？

```python
from csp_lib.manager.base import BatchUploader
assert isinstance(my_uploader, BatchUploader)  # runtime_checkable
```

---

## 相關頁面

- [[No MongoDB Setup]] — 不使用 MongoDB 的完整指南
- [[Custom Repository]] — 自訂 AlarmRepository / CommandRepository
- [[_MOC Manager]] — Manager 層模組索引
- [[DeviceEventSubscriber]] — BatchUploader 所在的 manager.base 模組
