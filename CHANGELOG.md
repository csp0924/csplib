# Changelog

本專案的所有重要變更皆記錄於此檔案。

格式基於 [Keep a Changelog](https://keepachangelog.com/)，版本號遵循 [Semantic Versioning](https://semver.org/)。

## [0.9.0](https://github.com/csp0924/csplib/compare/v0.8.4...v0.9.0) (2026-04-21)


### Added

* **equipment:** AsyncModbusDevice.used_unit_ids property + sentinel resolve ([#92](https://github.com/csp0924/csplib/issues/92)) ([30f50e8](https://github.com/csp0924/csplib/commit/30f50e8aa66e9d9467eb01ff09df93bfd2e0f8e2))
* **equipment:** ReadGroup.unit_id + PointGrouper 按 unit_id 分桶 ([#90](https://github.com/csp0924/csplib/issues/90)) ([b0a1084](https://github.com/csp0924/csplib/commit/b0a108472aafaea6ee293075e601185cf3c60295))
* **equipment:** ReadPoint/WritePoint 新增 optional unit_id 欄位 ([#89](https://github.com/csp0924/csplib/issues/89)) ([9b6bf4e](https://github.com/csp0924/csplib/commit/9b6bf4ef5a38b3e05171306ef228e71d59f10b46))
* **integration:** Operator Pattern 基礎（Reconciler + TypeRegistry + SiteManifest） ([#87](https://github.com/csp0924/csplib/issues/87)) ([4606bcb](https://github.com/csp0924/csplib/commit/4606bcb3ab2d9453ca66308ac8d8d33ea6a785b8))
* **manager:** DataUploadManager fan-out transform 與 ON_CHANGE policy ([#94](https://github.com/csp0924/csplib/issues/94)) ([174eca1](https://github.com/csp0924/csplib/commit/174eca1ced10d357ec8b30a2a5c571ff215ba62d))


### Fixed

* **ci:** CITATION.cff date 同步改推 Release PR branch 避開 main protection ([#83](https://github.com/csp0924/csplib/issues/83)) ([928fd64](https://github.com/csp0924/csplib/commit/928fd646a18e533b429d6528bb188382be149959))
* **ci:** release.yml 支援 dispatch 舊 tag（救 v0.8.4 情境） ([#86](https://github.com/csp0924/csplib/issues/86)) ([9f622ff](https://github.com/csp0924/csplib/commit/9f622ff36bc140a791d32f5312c34c11777051ee))


### Changed

* **equipment:** GroupReader/ValidatedWriter 支援 per-group/per-point unit_id ([#91](https://github.com/csp0924/csplib/issues/91)) ([db84529](https://github.com/csp0924/csplib/commit/db8452940e965236fafc30348fdc4d07c32b5ac4))
* **integration:** Operator Pattern merge 前收尾（BoundSpec 瘦身 + ReconcilerMixin） ([#88](https://github.com/csp0924/csplib/issues/88)) ([6cf5ce4](https://github.com/csp0924/csplib/commit/6cf5ce4ac6511a0b17e88366c24ec98cfb00c590))

## [0.8.4](https://github.com/csp0924/csplib/compare/v0.8.3...v0.8.4) (2026-04-19)


### Fixed

* **ci:** commitlint 放行 dependabot（deps-dev scope + bot bypass） ([#77](https://github.com/csp0924/csplib/issues/77)) ([f5d1d2e](https://github.com/csp0924/csplib/commit/f5d1d2e7f9cdacde366315bf702e17c2ff65dee8))
* **ci:** release-please 改用 separate-pull-requests ([#65](https://github.com/csp0924/csplib/issues/65)) ([dac984e](https://github.com/csp0924/csplib/commit/dac984effcc980d3e834faad4b992d0a23c77b82))
* **modbus:** 區分 pymodbus 未安裝與版本不相容的錯誤訊息 ([#81](https://github.com/csp0924/csplib/issues/81)) ([fc6837e](https://github.com/csp0924/csplib/commit/fc6837e868bc6ad1793d6b6585c09908774cdf6a))
* **tests:** test_worker_timeout_triggers_circuit_breaker 改用 wait_for_condition 消除 CB 狀態 race ([#78](https://github.com/csp0924/csplib/issues/78)) ([fd88849](https://github.com/csp0924/csplib/commit/fd88849a4f51ed7ea1bcfe7ef3cd4c16cdcbaba6))


### Dependencies

* **deps-dev:** update aiosqlite requirement ([#72](https://github.com/csp0924/csplib/issues/72)) ([0748755](https://github.com/csp0924/csplib/commit/0748755a6a1e4b71b486a2c220c42eab2b3d657f))
* **deps-dev:** update fastapi requirement ([#76](https://github.com/csp0924/csplib/issues/76)) ([08aab0d](https://github.com/csp0924/csplib/commit/08aab0dc863a6073986a3701c1237509aca4acee))
* **deps-dev:** update protobuf requirement ([#73](https://github.com/csp0924/csplib/issues/73)) ([837af14](https://github.com/csp0924/csplib/commit/837af14a54f4591cf55818adef0fcabb9673ba31))
* **deps-dev:** update uvicorn requirement ([#75](https://github.com/csp0924/csplib/issues/75)) ([162f451](https://github.com/csp0924/csplib/commit/162f451f9831a47e1e32a08661edb0a83186396c))
* **deps:** bump actions/cache from 4.2.0 to 5.0.5 ([#71](https://github.com/csp0924/csplib/issues/71)) ([e1af877](https://github.com/csp0924/csplib/commit/e1af87704809bf85302978ef3a85695eaad1c20c))
* **deps:** bump actions/download-artifact from 4.1.8 to 8.0.1 ([#68](https://github.com/csp0924/csplib/issues/68)) ([5865f67](https://github.com/csp0924/csplib/commit/5865f6751fa8fe6fdf0fd1265f05b565493af81e))
* **deps:** bump actions/setup-python from 5.3.0 to 6.2.0 ([#70](https://github.com/csp0924/csplib/issues/70)) ([0966bfd](https://github.com/csp0924/csplib/commit/0966bfd6977133433c243217757ac06e7db17de6))
* **deps:** bump astral-sh/setup-uv from 6.3.1 to 8.1.0 ([#67](https://github.com/csp0924/csplib/issues/67)) ([ab9382c](https://github.com/csp0924/csplib/commit/ab9382c2b95cd4014d583ad8295b960793be75ac))
* **deps:** bump pypa/gh-action-pypi-publish from 1.12.4 to 1.14.0 ([#69](https://github.com/csp0924/csplib/issues/69)) ([f8b4133](https://github.com/csp0924/csplib/commit/f8b41338c6f3b517b917dabadde88260b7c92671))

## [0.8.3](https://github.com/csp0924/csplib/compare/v0.8.2...v0.8.3) (2026-04-18)


### Fixed

* **ci:** last-release-sha 要放 root level 而非 package 內 ([#62](https://github.com/csp0924/csplib/issues/62)) ([f8833bf](https://github.com/csp0924/csplib/commit/f8833bf1168b1f43d406d72870424d21f354e0bb))
* **ci:** release-please boundary + README 動態 PyPI badge ([#60](https://github.com/csp0924/csplib/issues/60)) ([4bf7815](https://github.com/csp0924/csplib/commit/4bf7815cf55b40b0f89bfcff5adc210084527d63))
* **ci:** release-please tag format 改用 v{version} 對上既有 tag ([#58](https://github.com/csp0924/csplib/issues/58)) ([bcebe99](https://github.com/csp0924/csplib/commit/bcebe99de26271771ec880f036e87d34ab9ecdf1))
* **ci:** release-please 全量覆蓋 bump_version.py 的所有版本位置 ([#55](https://github.com/csp0924/csplib/issues/55)) ([0767fe3](https://github.com/csp0924/csplib/commit/0767fe37faeec2f21a98e1ba6cfa0760f7338dd5))
* **ci:** 為 release-please 指定 last-release-sha 作為 boundary ([#57](https://github.com/csp0924/csplib/issues/57)) ([08f0df5](https://github.com/csp0924/csplib/commit/08f0df549d1cf48ae22074598a0cd727158551e2))

## [Unreleased]

## [0.8.2] - 2026-04-17

### Fixed

- **`MongoBatchUploader` 高頻 enqueue 導致資料靜默遺失（WI-MB-01/02）**：修復 `enqueue()` 大量堆積時 `BatchQueue.popleft()` 丟棄最舊資料的 bug。新增內部 `_threshold_event: asyncio.Event` 通知機制：`enqueue()` 達到 `batch_size_threshold` 時立即 set；`_flush_loop` 改以 `asyncio.wait()` 同時監聽 `_stop_event` / `_threshold_event` / `flush_interval` timeout 三路觸發，閾值達標立即 flush 對應 collection；停止時正確 cancel 並 await 未完成 waiter task，避免 asyncio task leak。既有 public API signature 與行為語義**未變更**。

### Added

- **`MongoBatchUploader.write_immediate(collection_name, document) -> WriteResult`（WI-MB-03）**：繞過 batch queue 的即時寫入出口，適用告警記錄、命令記錄等必須即時持久化的場景。不做自動重試；回傳 `csp_lib.mongo.WriteResult`（非 `csp_lib.equipment.transport.WriteResult`）。詳見 [[MongoBatchUploader]]。
- **`MongoBatchUploader.writer` read-only property**：回傳內部 `MongoWriter` 實例，供 `LocalBufferedUploader` replay 路徑使用 `write_batch(ordered=False)` 細粒度介面。
- **`MongoWriter.write_batch(..., ordered: bool = True)` 新增 `ordered` keyword-only 參數**：`ordered=False` 時捕捉 `pymongo.errors.BulkWriteError` 並將 code=11000（重複鍵）與其他錯誤分離計數；若所有錯誤均為重複鍵，`success` 仍回 `True`（支援 idempotent replay 判定）；既有呼叫者預設 `ordered=True`，零修改相容。
- **`WriteResult.duplicate_key_count: int = 0` 新增欄位**：dataclass default 欄位，記錄 `ordered=False` 批次寫入中的重複鍵錯誤數量，供 `LocalBufferedUploader` replay 成功判定使用；向後相容（既有建構呼叫無需修改）。
- **`csp_lib.mongo.local_buffer` 新模組（WI-MB-LB-01/02）**：提供 SQLite WAL 本地緩衝 + 非同步 replay 的 MongoDB 上傳層，確保 WAN/MongoDB 斷線期間資料不遺失。詳見 [[LocalBufferedUploader]]。
  - **`LocalBufferedUploader(AsyncLifecycleMixin)`**：`async with` 生命週期管理；實作 `BatchUploader` Protocol，可無痛注入 `DataUploadManager.uploader`。Public API：`register_collection()`、`enqueue()`、`write_immediate()`、`ensure_indexes()`、`health_check()`、`get_pending_count()`、`get_sync_cursor()`。背景以 `_replay_loop` / `_cleanup_loop` 兩個 asyncio.Task 執行；replay 以 `ordered=False` 批次寫入下游 `MongoBatchUploader.writer`；`success OR (inserted + duplicates >= len(docs))` 視為全數 mark synced；retention 到期的 synced row 由 cleanup loop 移除。
  - **`LocalBufferConfig`** frozen dataclass：欄位 `db_path`（預設 `"./csp_lib_buffer.db"`）、`replay_interval=5.0`、`replay_batch_size=500`、`cleanup_interval=3600.0`、`retention_seconds=604800.0`（7 天）、`max_retry_count=100`；`__post_init__` 對所有正數欄位做 `ValueError` 驗證。
  - **Idempotency key**：文件含 `_idempotency_key` 時優先使用，否則生成 `{collection}:{sha1(json)[:40]}:{uuid4.hex}`；replay 寫入 MongoDB 時依賴 `_idempotency_key` unique sparse index 達成冪等。`ensure_indexes()` 冪等建立最小必要 index。
  - 依賴 `aiosqlite>=0.19.0`（需手動加入 `pyproject.toml` 的 `[project.optional-dependencies] mongo`）；未安裝時 `from csp_lib.mongo.local_buffer import LocalBufferedUploader` 拋 `ImportError` 提示訊息，`csp_lib.mongo` 頂層 import 不受影響。
- **`DataUploadManager.__init__(buffered_uploader=None)` 新增 keyword-only 參數**：opt-in 以 `LocalBufferedUploader` 取代底層 uploader；提供時所有 enqueue 改走本地 SQLite buffer；`None` 時行為與 v0.8.1 完全一致（零 breaking）。詳見 [[DataUploadManager]]。
- **`AlarmPersistenceManager.__init__(buffered_uploader=None)` 新增 keyword-only 參數**（放在 `config` 之後，保 positional 相容）：提供時，`_create_alarm` / `_resolve_alarm` 成功後額外以 `write_immediate` 寫告警快照到 `config.history_collection`；寫入失敗僅 log warning，不影響主流程。詳見 [[AlarmPersistenceManager]]。
- **`AlarmPersistenceConfig.history_collection: str = "alarm_history"` 新增欄位**：frozen dataclass default；供 `buffered_uploader` 知道寫入哪個 collection；`__post_init__` 驗證非空字串；向後相容（既有建構無需修改）。
- **Strategy 動態參數化（`DroopStrategy` / `QVStrategy` / `FPStrategy`）**：三個策略 `__init__` 新增 keyword-only 參數 `params: RuntimeParameters | None`、`param_keys: Mapping[str, str] | None`（邏輯欄位 → RuntimeParameters key 映射）、`enabled_key: str | None`（falsy 時跳過策略計算）。`params=None` 時行為 100% 等同舊版（frozen config 路徑保留）；`param_keys` 僅列需動態化的欄位，未列者 fallback config default；`params.get(key)` 回 None 時 fallback config（不拋錯）；`params` 與 `param_keys` 不對稱時 raise `ValueError`。`DroopStrategy` 額外新增 `droop_scale: float = 1.0`（droop 欄位倍率縮放，如 EMS 傳百分比需 × 0.01）與 `schedule_p_key: str | None`（enabled_key 為 0 時仍輸出 schedule_p）。詳見 [[DroopStrategy]] / [[QVStrategy]] / [[FPStrategy]]。
- **`RegistryAggregatingSource`** (`csp_lib.modbus_gateway`)：`DataSyncSource` 實作，每 `interval` 秒輪詢 `DeviceRegistry.get_devices_by_trait(trait)` 並對 `latest_values[point]` 執行聚合（`AggregateFunc.AVERAGE/SUM/MIN/MAX` 或自訂 `AggregateCallable`），結果寫入 Gateway register。全設備離線時支援 `offline_fallback` 回退值（None 則本週期跳過）；注入 `params` 時支援 `writable_param` 回寫 `RuntimeParameters`，讓 strategy 即時反映聚合值。詳見 [[RegistryAggregatingSource]]。
- **`RegisterAggregateMapping`** frozen dataclass（`csp_lib.modbus_gateway`）：`RegistryAggregatingSource` 的單一 register 聚合映射定義，欄位：`register`、`trait`、`point`、`aggregate`（預設 `AggregateFunc.AVERAGE`）、`offline_fallback`、`writable_param`。
- **`AggregateFunc`** enum（`csp_lib.modbus_gateway`）：內建聚合函式列舉，值：`AVERAGE`、`SUM`、`MIN`、`MAX`。
- **`AggregateCallable`** 型別別名（`csp_lib.modbus_gateway`）：`Callable[[list[float]], float]`，自訂聚合函式的型別簽名。
- **`RuntimeParameters.__getattr__` / `__setattr__`**：支援 attribute-style 存取（`params.soc_max`、`params.soc_max = 90.0`），等價於 `.get()` / `.set()`，觀察者正常觸發。不存在的 key 拋 `AttributeError`（非 `None`），底線開頭屬性走 `__slots__` 原生路徑。
- **`DeviceRegistry.StatusChangeCallback` 型別別名** (`Callable[[str, bool], None]`)：設備回應狀態變化通知的回呼簽名，用於 `on_status_change()` / `remove_status_observer()`。
- **`DeviceRegistry.on_status_change(callback)`**：註冊設備 `is_responsive` 變化觀察者；首次 `notify_status` 僅建立 baseline、不觸發（避免啟動期噪訊）；callback 在鎖外執行，例外隔離（warning log）。
- **`DeviceRegistry.remove_status_observer(callback)`**：移除已註冊的狀態變化觀察者，未找到時靜默忽略。
- **`DeviceRegistry.notify_status(device_id)`**：由呼叫方（`DeviceManager` / 輪詢迴圈）主動觸發狀態偵測；未註冊的 device_id 靜默忽略。
- **`SOCBalancingDistributor.SOCSource` 型別別名** (`Callable[[DeviceSnapshot], float | None]`)：自訂 SOC 取值函式簽名，供 `soc_source` 參數使用。
- **`SOCBalancingDistributor(soc_source=None)` 建構參數**：注入自訂 SOC 取值函式，適用於 SOC 不在 capability slot、而在 `latest_values` / `metadata` / 外部來源的場景；`None` 時走原路徑（100% 向後相容）；`soc_source` 拋例外**不攔截**，直接傳播給呼叫方（避免 silent corruption）。
- **`csp_lib.alarm` 新模組（L8 Additional）**（WI-AL-01/02）：提供 in-process 多來源告警聚合與 Redis pub/sub 橋接。
  - **`AlarmAggregator`**（`csp_lib.alarm.aggregator`）：多 source OR 聚合器；`bind_device(device, *, name=None)` 訂閱設備 `alarm_triggered` / `alarm_cleared` 事件、`bind_watchdog(watchdog, *, name)` 透過 `WatchdogProtocol` 綁定 watchdog timeout/recover、`unbind(name)` 解除並重算旗標、`mark_source(name, active)` 外部直接注入狀態；observer API：`on_change(cb)` / `remove_observer(cb)`；properties：`active: bool`、`active_sources: set[str]`；使用 `threading.Lock` 保護、callback 在 lock 外以快照呼叫（避免重入死鎖）。
  - **`WatchdogProtocol`**（`csp_lib.alarm.protocols`）：`@runtime_checkable` 結構化協定，要求 `on_timeout(cb)` / `on_recover(cb)`，相容 `CommunicationWatchdog` 及任何自訂 watchdog，避免 alarm 層直接依賴上層模組。
  - **`AlarmChangeCallback`**（`csp_lib.alarm.protocols`）：`Callable[[bool], None]` 型別別名。
  - **`RedisAlarmPublisher`** / **`RedisAlarmSource`**（`csp_lib.alarm.redis_adapter`，需 `csp_lib[redis]` extra）：繼承 `AsyncLifecycleMixin`；Publisher 採 `asyncio.create_task` 排程 async publish，publish 失敗僅 log warning；預設 payload schema：`{"type": "aggregated_alarm", "active": bool, "sources": [...], "timestamp": iso}`，相容日本 demo；Source 支援自訂 `event_parser: Callable[[dict], bool]`；停止時呼叫 `aggregator.unbind(name)` 清除遠端 source 狀態。
- **`PVSmoothStrategy` 動態參數化**（WI-ST-01）：`__init__` 新增 keyword-only `params: RuntimeParameters | None`、`param_keys: Mapping[str, str] | None`、`enabled_key: str | None`；可動態覆蓋欄位：`capacity`、`ramp_rate`、`pv_loss`、`min_history`；`enabled_key` falsy 時輸出 `Command(0, 0)`（PV 離線即停語義）；舊版 ctor 100% 相容。
- **`LoadSheddingStrategy` 動態參數化**（WI-ST-02）：同上新增 `params` / `param_keys` / `enabled_key`；可動態覆蓋欄位：`evaluation_interval`、`restore_delay`、`auto_restore_on_deactivate`（`stages` 不動態化）；`enabled_key` falsy 時回傳 `context.last_command`（保守，不強制變 0）。
- **`RampStopStrategy` 動態參數化**（WI-ST-03）：同上新增 `params` / `param_keys` / `enabled_key`；內部引入私有 `_RampStopRuntimeConfig` frozen dataclass；可動態覆蓋欄位：`rated_power`、`ramp_rate_pct`；`enabled_key` falsy 時回傳 `context.last_command`。
- **`MongoBufferStore`** (`csp_lib.mongo.local_buffer`)：`LocalBufferStore` Protocol 的第二個官方實作，以本地 mongod 作為 buffer backend。ctor：`MongoBufferStore(client, *, database="csp_local_buffer", collection="pending_documents")`（`client` 為 `AsyncIOMotorClient`，lifecycle 由使用者管理）。`open()` 時 ensure 3 個 index：`idempotency_key` unique、`(synced, _id)` compound（加速 `fetch_pending`）、`(synced, synced_at)` compound（加速 `delete_synced_before`）；index 建立失敗僅 log warning，不 raise。`close()` 為 no-op（不關閉 motor client）。`row_id` 以 `str(ObjectId)` 回傳（天然單調遞增）。`health_check()` 以 `admin.command("ping")` 實作。依賴 `csp_lib[mongo]` extra（motor），無需額外安裝。對應「本地 mongod → 遠端 mongod store-and-forward」雙 MongoDB 部署模式。詳見 [[MongoBufferStore]]。

### Changed

- **`LocalBufferedUploader` 重構為 backend-agnostic**（v0.8.2 開發期調整，未對外發佈）：
  - 新增 `LocalBufferStore` Protocol（`@runtime_checkable`）與 `BufferedRow` frozen dataclass（`csp_lib.mongo.local_buffer`），定義 backend 可插拔的純 CRUD 介面（`open/close/append/fetch_pending/mark_synced/bump_retry/delete_synced_before/count_pending/max_synced_sequence/health_check`）。
  - `SqliteBufferStore`（aiosqlite 實作）獨立為 `csp_lib.mongo.local_buffer.sqlite_store`，ctor 接受 `db_path`、`wal_mode=True`、`synchronous="NORMAL"`。
  - **Breaking**：`LocalBufferedUploader.__init__` 新增必填參數 `store: LocalBufferStore`；`LocalBufferConfig` 移除 `db_path` 欄位（移至 `SqliteBufferStore.__init__`）。新用法：`LocalBufferedUploader(downstream, store=SqliteBufferStore("./buf.db"), config=LocalBufferConfig())`。
  - Import 路徑保持向後相容：`from csp_lib.mongo import LocalBufferedUploader, LocalBufferConfig` 仍有效；新公開 API `LocalBufferStore`、`BufferedRow`、`SqliteBufferStore`、`MongoBufferStore` 亦從同一路徑可 import。
  - **Optional extras 重劃分**（需手動更新 `pyproject.toml`）：
    - `csp_lib[mongo]` 瘦身為純 `motor>=3.3.0`（純 Mongo client，含 `MongoBufferStore`）
    - 新增獨立 `csp_lib[local-buffer]`（`aiosqlite>=0.19.0,<0.21`）— 僅使用 `SqliteBufferStore` 時需要
    - `csp_lib[all]` 保留含兩者
    - `SqliteBufferStore` `ImportError` 訊息指向 `csp_lib[local-buffer]`
- **`BufferedRow.row_id` 與 `LocalBufferStore` Protocol 方法型別鬆綁為 `int | str`**（v0.8.2 開發期調整，未對外發佈）：為支援 `MongoBufferStore`（`row_id` 為 `str(ObjectId)`）與未來其他 backend，`BufferedRow.row_id`、`append()` 回傳、`mark_synced()` / `bump_retry()` 參數、`max_synced_sequence()` 回傳均改為 `int | str`。`SqliteBufferStore` 行為不變（繼續回 `int`），`int` 為 `int | str` 子集，向後相容。
- **`LocalBufferedUploader._synced_cursor`**：`_replay_once` 改為「記錄最後一筆成功同步的 row_id」（`fetch_pending` ASC 排序下即 `ids[-1]`）；因 ObjectId 字串的 `max()` 語義不明確（字典序 ≠ 時序），改為直接保留最新值；`_synced_cursor` 型別擴寬為 `int | str`，僅作監控用途，Uploader 不做 `>` 比較。

## [0.8.1] - 2026-04-17

### Added

- **`CommandRefreshService(AsyncLifecycleMixin)`** (WI-REFRESH-001/003): Kubernetes-style reconciler，每隔 `interval` 秒把 `CommandRouter._last_written`（desired state）重新推回設備（actual state），解決三類問題：(A) 寫入失敗黑洞、(B) PCS 業務 watchdog 自動歸零、(C) EMS/SCADA 透過 ModbusGatewayServer 繞過策略直接改 register。採 `next_tick_delay` 絕對時間錨定；單次失敗不中止服務；NO_CHANGE 軸不污染 desired state。
- **`CommandRefreshConfig` frozen dataclass** (WI-REFRESH-003): `CommandRefreshService` 的結構化配置，欄位：`refresh_interval: float = 1.0`、`enabled: bool = False`、`device_filter: frozenset[str] | None = None`。由 `SystemControllerConfig.command_refresh` 持有。
- **`CommandRouter.try_write_single(device_id, point_name, value) -> bool`** (WI-REFRESH-002): 公開單設備寫入 API（舊 `_write_single` 現在是 alias）。成功後更新 `_last_written` desired-state 表；protected / unresponsive / 設備不存在 / 寫入失敗皆回傳 `False`。
- **`CommandRouter.get_last_written(device_id) -> dict[str, Any]`** (WI-REFRESH-002): 回傳指定設備目前追蹤的 desired state snapshot（`point_name → value`）；設備未追蹤時回傳空 dict。
- **`CommandRouter.get_tracked_device_ids() -> frozenset[str]`** (WI-REFRESH-002): 回傳所有已有 desired-state 記錄的 device_id 集合。
- **`SystemControllerConfigBuilder.command_refresh(interval_seconds, enabled, devices)` 方法** (WI-REFRESH-003): Fluent API 啟用命令刷新服務；`devices=None` 代表全部被控設備。
- **`SystemController` 生命週期整合 `CommandRefreshService`** (WI-REFRESH-004): `_on_start` 啟動順序：executor → command_refresh → heartbeat；`_on_stop` 反向停止，確保 reconciler 在設備寫入能力存在期間才執行。
- **`HeartbeatValueGenerator` Protocol** (WI-HB-001): `@runtime_checkable` 協定，要求實作 `next(key: str) -> int` 與 `reset(key: str | None) -> None`。`key` 為多設備共用同一 generator instance 時的狀態隔離鍵。
- **`ToggleGenerator`** (WI-HB-001): 每個 `key` 在 0/1 之間交替的心跳值產生器；第一次呼叫回傳 1，與舊版 `HeartbeatMode.TOGGLE` 行為一致。
- **`IncrementGenerator(max_value=65535)`** (WI-HB-001): 遞增計數的心跳值產生器；到達 `max_value` 後歸零，合法範圍 `1 ≤ max_value ≤ 65535`。
- **`ConstantGenerator(value=1)`** (WI-HB-001): 常數值心跳值產生器；任何 `next(key)` 皆回傳固定值，合法範圍 `0 ≤ value ≤ 65535`。
- **`HeartbeatTarget` Protocol** (WI-HB-002): `@runtime_checkable` 協定，要求實作 `async write(value: int) -> None` 與 `identity: str` 屬性，抽象化「心跳值要寫到哪裡」。
- **`DeviceHeartbeatTarget(device, point_name)`** (WI-HB-002): `HeartbeatTarget` 的預設實作，對 `AsyncModbusDevice` 的單一點位寫入；`DeviceError` 僅 log warning（fire-and-forget）。
- **`GatewayRegisterHeartbeatTarget(gateway, register_name)`** (WI-HB-002): `HeartbeatTarget` 的 Modbus Gateway 實作，將心跳值寫入 `ModbusGatewayServer` 的指定 register；位於 `csp_lib.modbus_gateway`，避免 integration 層反向 import。
- **`HeartbeatMapping.value_generator: HeartbeatValueGenerator | None = None`** (WI-HB-003): 新欄位，用 Protocol 取代 `mode` enum；與 `mode` 欄位互斥（`__post_init__` 驗證，新舊混用時 raise `ValueError`）。
- **`HeartbeatMapping.target: HeartbeatTarget | None = None`** (WI-HB-003): 新欄位，用 Protocol 取代 `(device_id, point_name)` 硬編碼；與 `device_id` 欄位互斥（`__post_init__` 驗證）。
- **`HeartbeatConfig` frozen dataclass** (WI-HB-004): 將舊 6 個 `heartbeat_*` 欄位收攏為結構化 config，新增 `targets: list[HeartbeatTarget] = []` 欄位支援 Protocol 委派目標列表。
- **`HeartbeatService` `targets` kwarg** (WI-HB-005): `__init__` 新增 `targets: list[HeartbeatTarget] | None = None`；啟動時對每個 target 呼叫其 `write(value)`，value 來自 per-target generator（`_resolve_generator` per-mapping cache）。
- **`SystemControllerConfigBuilder.heartbeat(HeartbeatConfig(...))` positional 語法** (WI-HB-006): 傳入 `HeartbeatConfig` 實例時走新路徑，忽略其他 kwargs；舊版 `heartbeat(mappings=[...], interval=...)` 語法完全保留。
- **`csp_lib.integration` / `csp_lib.modbus_gateway` `__init__` exports 更新** (WI-HB-007): `integration` 新增 `CommandRefreshService`、`CommandRefreshConfig`、`HeartbeatConfig`、`HeartbeatValueGenerator`、`ToggleGenerator`、`IncrementGenerator`、`ConstantGenerator`、`HeartbeatTarget`、`DeviceHeartbeatTarget`；`modbus_gateway` 新增 `GatewayRegisterHeartbeatTarget`。

### Changed

- **`CommandRouter._safe_write` 回傳型別 `None → bool`**: 內部 static method，現在回傳是否成功（供 `try_write_single` 判斷是否更新 `_last_written`）；所有呼叫點均為 `CommandRouter` 內部，無 public API breaking 影響。

### Deprecated

- **`HeartbeatMapping.mode`、`HeartbeatMapping.constant_value`、`HeartbeatMapping.increment_max`**: 舊版 enum-based 欄位保留，僅在新舊混用（同時設定 `value_generator` 或 `target`）時於建構期 raise `ValueError`；legacy-only 路徑**不** emit `DeprecationWarning`（靜默相容策略，避免既有測試 noise）。計畫於 v1.0.0 移除。
- **`SystemControllerConfig.heartbeat_*` 六個欄位**（`heartbeat_mappings`、`heartbeat_interval`、`use_heartbeat_capability`、`heartbeat_capability_mode`、`heartbeat_capability_constant_value`、`heartbeat_capability_increment_max`）: 同上靜默相容策略；新代碼應改用 `SystemControllerConfig.heartbeat: HeartbeatConfig`。計畫於 v1.0.0 移除。
- **`HeartbeatMode` enum**: 隨舊欄位一併保留至 v1.0.0。完整 deprecation 清單已登錄至 BACKLOG.md v1.0.0 section（WI-HB-008）。

## [0.8.0] - 2026-04-17

### Added

- **`NoChange` 型別、`NO_CHANGE` sentinel、`is_no_change()` TypeGuard** (WI-V080-004): 策略可對不需管控的軸回傳 `NO_CHANGE`（如 QV 策略只管 Q、FP 策略只管 P），`CommandRouter.route()` 偵測到 NO_CHANGE 時跳過對應軸的設備寫入（記錄 TRACE log）。`NO_CHANGE` 為全域單例，比較應使用 `value is NO_CHANGE`；`is_no_change()` TypeGuard 供型別安全分支使用。Hierarchical wire format（transport/status）：NO_CHANGE 與 JSON null 雙向 round-trip；GUI API（`modes.py`）：NO_CHANGE 軸在 JSON response 輸出 null。
- **`Command.effective_p(fallback=0.0) -> float` / `effective_q(fallback=0.0) -> float`** (WI-V080-004): 輔助方法，將 NO_CHANGE 轉為具體浮點數，供級聯累加、積分補償器狀態更新等消費點使用，避免散落各處的 `is NO_CHANGE` 守衛。
- **`Command.p_target` / `q_target` 型別擴寬為 `float | NoChange`** (WI-V080-004): 既有 `Command(p_target=0.0)` 建構完全不變；fallback 路徑 `Command(0.0, 0.0, is_fallback=True)` 刻意使用 float（安全停機語義，不保留舊值）。
- **`ReadPoint.reject_non_finite: bool = False`** (WI-V080-001): 設為 `True` 時，`AsyncModbusDevice` 讀到 NaN/+Inf/-Inf 保留 `_latest_values[name]` 舊值、發 WARNING log、不觸發 `value_change` 事件、不將非有限值送進告警評估或 `EVENT_READ_COMPLETE` payload。預設 `False` 維持 IEEE 754 sentinel 行為（向後相容）。
- **`ContextMapping.param_key: str | None = None`** (WI-V080-003): v0.8.0 新增第三種來源模式。從 `RuntimeParameters.get(param_key)` 直接注入 context 欄位，不需手動搬入 extra dict。與 `device_id` / `trait` 互斥（三擇一）；`transform` 與 `default` 在 param_key 模式下仍生效；`ContextBuilder` 若未提供 `runtime_params` 則 log warning 並回退至 `default`。`__post_init__` 驗證改為 `_validate_context_source`（三擇一錯誤訊息）。
- **`SystemControllerConfigBuilder.map_context(..., param_key=...)` kwarg** (WI-V080-003): Builder 的 `map_context()` 接受 `param_key` 關鍵字參數，建立 `ContextMapping(param_key=...)` 實例。
- **`SystemControllerConfig.trigger_on_read_device_ids: list[str]`** (WI-V080-005): 宣告式配置欄位，`SystemController._on_start` 自動對這些 device_id 呼叫 `attach_read_trigger()`，`_on_stop` 入口先 detach 再停 executor。
- **`SystemController.attach_read_trigger(device_id) -> Callable[[], None]`** (WI-V080-005): 執行期 API，將指定設備的 `EVENT_READ_COMPLETE` 綁定為 `StrategyExecutor.trigger()` 的呼叫源。重複 attach 同 device_id 拋 `ValueError`（fail-fast 冪等保護）；未在 registry 的 device_id 拋 `ValueError`；回傳 wrapped detacher 供手動解除。
- **`SystemControllerConfigBuilder.trigger_on_read_complete(device_id)`** (WI-V080-005): 對應 Builder 宣告式 API，鏈式呼叫將 device_id 加入 `trigger_on_read_device_ids`。

### Changed

- **`ExecutionConfig.interval_seconds: int → float`** (WI-V080-002): 型別放寬為 float，支援 sub-second 策略執行（如 DReg 0.3 s）。向後相容，既有 int 值可直接賦值。同步移除 `DroopStrategy` / `FFCalibrationStrategy` 中 `max(1, int(self._config.interval))` workaround，直接傳 float。
- **`LoadSheddingConfig.evaluation_interval: int = 5 → float = 5.0`** (WI-V080-002): 型別隨 `interval_seconds` 統一改為 float。
- **`PVSmoothStrategy.__init__(interval_seconds: int) → float`** (WI-V080-002): 型別統一改為 float。
- **`StrategyExecutor.run()` PERIODIC/HYBRID 首次執行改為立即（work-first）** (WI-V080-006): 舊實作先等 `interval_seconds` 再執行第一次；新實作啟動後**立即**執行一次，再以 `next_tick_delay()` 絕對時間錨定排程後續週期。HYBRID 模式提前觸發後重設 anchor，下次 tick 從觸發點起算完整 interval；策略切換時重設 anchor + cycle counter。TRIGGERED 模式維持 v0.7.x 語義（不使用 anchor）。若依賴「啟動後先等一個 interval」的舊語義，需調整。
- **`ContextMapping.__post_init__` 驗證函式更名為 `_validate_context_source`** (WI-V080-003): 驗證邏輯由二擇一（device_id / trait）擴充為三擇一（device_id / trait / param_key），錯誤訊息對應更新。

### Fixed

- **(WI-V080-006 / WI-TD-105) `StrategyExecutor` PERIODIC/HYBRID 週期漂移**: 舊實作以 `asyncio.wait(timeout=interval_seconds)` 相對等待，不計入 `_execute_strategy()` 耗時（典型 exec=50 ms、interval=0.3 s → 16.7% 漂移 / 小時 360 s 偏移）。新實作採用 `csp_lib.core._time_anchor.next_tick_delay()` 絕對時間錨定，與 CAN/PeriodicSender/Modbus read_loop 同一機制，10 個 cycle 總耗時 drift < 10%（tests 驗證）。

## [0.7.3] - 2026-04-16

### Added

- **`PowerCompensator.update_ff_bin(bin_idx, ff_ratio, *, persist=False)`** (BUG-007): Public API to update a single FF table bin with validation chain (clamp to `[ff_min, ff_max]`, rejects NaN/Inf/negative, raises `TypeError`/`ValueError` for invalid inputs). Replaces direct `_ff_table` access anti-pattern. Optionally persists after update.
- **`PowerCompensator.persist_ff_table()`** (BUG-007): Public API to persist the current FF table via the configured `FFTableRepository`. No-op if no repository is configured; preserves existing log-swallow semantics.
- **`Command.is_fallback: bool = False`** (BUG-011): New field on the `Command` frozen dataclass. `StrategyExecutor` sets `is_fallback=True` on the zero-command returned when strategy execution raises an exception, allowing callers (monitoring, cluster status) to distinguish a normal zero-command from an error fallback. `with_p()` / `with_q()` propagate this flag automatically via `dataclasses.replace`.
- **`GatewayRegisterDef.writable: bool = False`** (SEC-006): Per-register EMS write permission flag. `WritePipeline` checks this before the validator chain; registers with `writable=False` are logged with a WARNING (carrying a `RegisterNotWritableError` message) and skipped. The error is **not raised** and **no Modbus exception is returned to the client** — the client observes the register retain its old value. Defaults to `False` (secure-by-default). Only applies to HOLDING registers — INPUT registers are always read-only at the protocol level.
- **`RegisterNotWritableError(WriteRejectedError)`** (SEC-006): New exception class used as the log/audit payload when EMS attempts to write a HOLDING register whose `writable` flag is `False`. **Not raised** by `WritePipeline` — if Modbus-level rejection is required, wire it at the DataBlock/pipeline layer. Carries `register_name` and `address` attributes. Exported from `csp_lib.modbus_gateway`.

### Fixed

- **`FFCalibrationStrategy._finish()` private API access** (BUG-007): Refactored to call `compensator.update_ff_bin()` and `compensator.persist_ff_table()` instead of directly accessing `_ff_table` and `_save_ff_table`. No behavioral change.
- **`ClusterStateSubscriber` silent JSON parse failure** (BUG-008): `except (json.JSONDecodeError, TypeError): pass` blocks replaced with `logger.warning(...)`. Corrupt Redis data is now surfaced in logs instead of silently ignored.
- **`BitExtractTransform.__post_init__()` missing upper bound validation** (BUG-009): Added `bit_offset + bit_length <= 64` check; raises `ValueError` for out-of-range bit fields instead of silently returning 0.
- **`CoilToBitmaskAggregator.coil_names` mutable list** (BUG-010): Field type changed from `list[str]` to `tuple[str, ...]`; `__post_init__` automatically converts a plain list to tuple, preventing external mutation.
- **`StrategyExecutor` exception fallback reuses last command** (BUG-011): On strategy execution exception, the executor now returns `Command(p_target=0.0, q_target=0.0, is_fallback=True)` instead of `self._last_command`. `_last_command` is not updated on the fallback path, so the next cycle's `context.last_command` remains the last successfully computed command.
- **`SinkManager._poll_remote_level` timing drift** (WI-TD-104): Replaced fixed `asyncio.sleep(poll_interval)` with `next_tick_delay` absolute time anchoring, eliminating cumulative drift from HTTP/Redis request latency.
- **`DeviceGroup._sequential_loop` timing drift** (WI-TD-106): Replaced fixed per-step sleep with `next_tick_delay` anchoring; device group step intervals now compensate for `read_once` execution time.
- **`CommunicationWatchdog._check_loop` timing drift** (WI-TD-107): Fixed-sleep replaced with `next_tick_delay`; 24-hour drift at 1 s interval reduced from ~432 s to negligible.
- **`SystemMonitor._run_loop` timing drift** (WI-TD-108): Fixed-sleep replaced with `next_tick_delay`; metrics collection + Redis publish latency (100–500 ms) no longer accumulates as drift.
- **`ClusterStateSubscriber._parse_float_field` rejected JSON-encoded floats** (BUG-012, Copilot review): Publisher writes values via `json.dumps(...)`; Redis `hgetall` returns `str` (under `decode_responses=True`) or `bytes`, both of which `safe_float` rejected → `p_target`/`q_target`/`command_timestamp` silently fell back to `0.0` every poll. Now converts `str`/`bytes` to `float` before the finite check. Non-finite and malformed values still fall back to default and log a WARNING.
- **`SystemController._on_start` partial-startup resource leak** (BUG-013, Copilot review): `_on_start` had no rollback path; if `processor.async_init()` or `heartbeat.start()` raised after `data_feed.attach()`, the event listener would leak because PEP 492 skips `__aexit__` when `__aenter__` raises. Wrapped in `try/except Exception` that invokes `_on_stop()` (already None-safe for partial state) before re-raising; `BaseException` intentionally excluded so cancellation/interrupt signals propagate without running another `await`. Added `test_on_start_rollback_on_heartbeat_failure` and `test_on_start_rollback_via_async_with`.

### Changed

- **`ModbusGatewayServer` sync source HOLDING register write banned** (SEC-018): `_update_register_callback` now raises `PermissionError` if a sync source attempts to write a HOLDING register. Sync sources (e.g. `RedisSubscriptionSource`, `PollingCallbackSource`) are restricted to INPUT registers only. Attempting to write a HOLDING register logs an error and raises to prevent a poisoned Redis channel from injecting arbitrary setpoints.
- **`examples/11_modbus_gateway.py`**: Three HOLDING registers (`p_command`, `q_command`, `mode`) updated with `writable=True` to reflect the new SEC-006 default.

### Refactored (internal)

- **`ClusterStateSubscriber._poll_all` 去重**：5 個重複的 `try/except json.loads` 區塊與 3 個 `try/except float()` 區塊抽出為 `_parse_json_field` / `_parse_float_field` 兩個 static helpers；float 解析改用 `csp_lib.core._numeric.safe_float`，減少 ~20 行樣板。
- **`PowerCompensator._learn_if_steady` / `_learn_from_saturation` clamp 統一**：將 `max(lo, min(hi, x))` 模式改為既有 `csp_lib.core._numeric.clamp()`，與新公開的 `update_ff_bin()` 保持一致。
- **`PowerCompensator.update_ff_bin` 清理**：移除 `ff_ratio is None` 的不可達檢查（型別標註已排除 `None`）。
- **`RedisSubscriptionSource._handle_message` 與 `PollingCallbackSource._poll_loop` 去重**：三個 single/list/kv 分支共用的 `try/except KeyError/PermissionError` 抽出為 `_dispatch(name, value)` helper；未知 register 與 HOLDING 拒絕的處理邏輯統一。
- **`DeviceGroup._sequential_loop` catch-up 路徑 yield**：`next_tick_delay` 回傳 `delay==0`（嚴重漂移重設）時顯式 `await asyncio.sleep(0)`，確保 `_stop_event.set()` 在每個 tick 邊界都能被 scheduler 感知。
- **`CommunicationWatchdog._check_loop` anchor 走 `self._clock`** (Copilot review)：原本 `anchor = time.monotonic()` 繞過建構時注入的 `clock` 參數，與同 loop 其他時間取得不一致。改為 `anchor = self._clock()`，注入時鐘的覆蓋更完整。
- **`SinkManager._poll_remote` 改為 sleep-first** (Copilot review)：`attach_remote_source` 已於啟動時 fetch 一次；原 work-first 版本在啟動時會立刻再 fetch 一次，造成 startup double-fetch。改為先 `next_tick_delay` 再 fetch，保留原絕對時間錨定語意。
- **`CoilToBitmaskAggregator.coil_names` 型別標註改為 `Sequence[str]`** (Copilot review)：`__post_init__` 本就接受 list/tuple 再轉為 tuple，但原 `tuple[str, ...]` 標註讓 mypy 拒絕傳入 list。改用 `Sequence[str]` 反映實際可接受的輸入型別。

### Tests

- **`test_watchdog.py` 4 個 timing-sensitive 測試改 fake `asyncio.sleep`**：`TestWatchdogTimeout` / `TestWatchdogRecovery` / `TestWatchdogCallbackExceptions` 原本依賴真實 `asyncio.sleep(0.01s)` 推進 `_check_loop`，在 Windows scheduler 精度不足或 pytest-xdist 多 worker 搶 CPU 時可能把 10ms sleep 延遲到秒級，造成 CI 偶發 `TimeoutError`（v0.7.3 首次 release 因此失敗）。改用 `patch("csp_lib.modbus_gateway.watchdog.asyncio.sleep", _yield_sleep)` 讓 `_check_loop` 只 yield event loop 不實際等待；因 `asyncio` 是 singleton module，patch 會全域生效，fake 內部透過 module-load 時保存的 `_REAL_SLEEP` reference 避免遞迴。

### Security

- **(SEC-006) `GatewayRegisterDef.writable` defaults to `False`**: All HOLDING registers are now write-protected by default. EMS can only write registers explicitly marked `writable=True`. See migration note below.
- **(SEC-011) `GatewayServerConfig.host` defaults to `"127.0.0.1"`**: Gateway no longer binds to all interfaces by default. Deployments that need external EMS access must explicitly set `host="0.0.0.0"` or a specific interface address. A `WARNING` is logged whenever `host="0.0.0.0"` is used at runtime.
- **(SEC-018) Sync sources cannot write HOLDING registers**: Prevents a compromised Redis channel or polling callback from overwriting EMS-controlled setpoint registers via the gateway's sync source path.

#### ⚠️ Behavior Changes (Migration Required)

**GatewayRegisterDef.writable defaults to False (SEC-006)**
Previously, every HOLDING register was implicitly writable by EMS. Starting in v0.7.3, you MUST explicitly set `writable=True` on registers intended for EMS write access.

```python
# Before v0.7.3 — HOLDING register was writable by default
GatewayRegisterDef("p_command", 0, Int32(), RegisterType.HOLDING)

# v0.7.3+ — must opt in
GatewayRegisterDef("p_command", 0, Int32(), RegisterType.HOLDING, writable=True)
```

**GatewayServerConfig.host defaults to "127.0.0.1" (SEC-011)**
Previously defaulted to `"0.0.0.0"` (all interfaces). If your gateway needs to accept connections from other hosts, explicitly set `host="0.0.0.0"` or a specific interface address.

```python
# Before v0.7.3 — bound to all interfaces implicitly
GatewayServerConfig(port=502)

# v0.7.3+ — must opt in for external access
GatewayServerConfig(host="0.0.0.0", port=502)
```

**Sync sources restricted to INPUT registers (SEC-018)**
If you previously used `PollingCallbackSource` or `RedisSubscriptionSource` to push values into HOLDING registers, those writes will now raise `PermissionError`. Move HOLDING register updates to `server.set_register()` or the write pipeline.

## [0.7.2] - 2026-04-16

### Added

- **`PowerCompensatorConfig.saturation_learn_min_cycles`**（預設 `2`）：連續飽和達到 N 個週期後才觸發飽和學習，避免單次瞬態飽和即更新 FF 表
- **`PowerCompensatorConfig.saturation_learn_alpha`**（預設 `0.5`）：飽和學習的 EMA 平滑係數（0 = 完全保留舊值，1 = 完全採用物理推算值）
- **`PowerCompensatorConfig.saturation_learn_max_step`**（預設 `0.03`）：單次飽和學習 FF 最大變動量，限制單步衝擊
- **`PowerCompensator._learn_from_saturation()`**：連續飽和期間以 `output / measurement`（放電）或 `measurement / output`（充電）物理比值直接推算 FF 係數，經 EMA 平滑與 max_step clamp 後更新 FF 表
- **`csp_lib.core._numeric`**（internal helper，不對外 export）：`is_non_finite_float()` / `safe_float()` / `clamp()` 集中處理 NaN/Inf 偵測與值域 clamp，供 SEC-013a/SEC-004/BUG-005 共用
- **`csp_lib.core._time_anchor`**（internal helper，不對外 export）：`next_tick_delay()` 提供絕對時間錨定（absolute time anchoring）的睡眠 delay 計算，含「嚴重落後重設 anchor 避免 burst catch-up」邏輯，供 WI-TD-101/102/103 共用

### Fixed

- **`PowerCompensator` Asymmetric anti-windup (BUG-012)**：修復飽和時無條件清零 integral 導致 FF 表過高 bin 永久鎖死的現場 bug。現在依飽和方向與誤差方向判斷：高飽和 + error < -deadband（量測超標）→ 允許累積負 integral 拉回；低飽和 + error > +deadband → 允許累積正 integral；飽和同向 → 凍結 integral（避免 windup）。現場症狀：setpoint=1993kW 但 PCS 持續輸出 2200kW（rel_err 9.4% 不自修正）
- **`PowerCompensator._learn_if_steady` setpoint=0 除以零 (BUG-002)**：修復 `deadband=0` 時 guard 失效，`setpoint=0` 在 `filtered_error / setpoint` 行 crash 的問題。改用 `abs(setpoint) < max(cfg.deadband, 1e-6)` 確保零 setpoint 一定被攔截
- **`assemble_from_registers()` / `split_to_registers()` LOW_FIRST 忽略 register order (BUG-001)**：`csp_lib/modbus/types/_register_helpers.py` 中 register_count ≠ 2/4 的 fallback 路徑遺漏 `LOW_FIRST` reverse，導致 `DynamicInt(96)` 等大型資料型別解碼錯誤。統一所有長度走同一條 reverse 邏輯
- **`DynamicSOCProtection` 反轉配置 (BUG-003)**：`soc_max < soc_min` 時改為直接拋 `ValueError`（原本未驗證會同時禁止充放電造成 BESS 癱瘓）。配置錯誤需明確拋錯，不靜默運作
- **`CANField.__post_init__` resolution=0 除以零 (BUG-004)**：`csp_lib/equipment/processing/can_parser.py` `CANField` 加 `__post_init__` 驗證 `resolution != 0`，避免 encoder 在執行階段除零 crash
- **`StatisticsEngine.process_read` NaN/Inf 污染 power_sum (BUG-005)**：以 `math.isfinite()` 過濾 power 與 energy tracking 兩條路徑的非有限 float，NaN/Inf 不寫入也不覆寫上次有效值
- **`PymodbusTcpClient.connect()` 重複連線保護 (BUG-006)**：以 `asyncio.Lock` 序列化併發呼叫 + lock 內以 `client.connected` 真實狀態判斷是否需 connect，避免重複呼叫底層 `AsyncModbusTcpClient.connect`。網路掉線（`client.connected` 自動翻為 False）後仍可正常重連，不會被 sticky flag 卡死

### Security

- **NaN/Inf 分層防禦：L4/L6 fail-safe (SEC-013a)**：Modbus `Float32/64.decode()` 維持 IEEE 754 permissive（尊重合法 NaN/Inf sentinel，如電表 fault 信號），但於上層 fail-safe：
  - **L6 `ContextBuilder._set_context_field`**：非有限 float → 寫入 `None`（不留 stale value），下游欄位型別本就是 `float | None`，沿用既有 None 處理路徑
  - **L4 `PowerCompensator.process()`**：measurement 非有限 → 整體 bypass compensate（不更新 `_integral` / `_last_output` / `_filtered_error` / FF table），避免 EMA / integral 永久污染
  - **L4 Protection rules**（`DynamicSOCProtection` / `SOCProtection` / `ReversePowerProtection` / `GridLimitProtection`）：context 值非有限 → passthrough command 沿用上次 `_is_triggered`（不強制觸發避免 NaN 閃爍掉電，也不重置避免上層誤判）
  - **L4 `DynamicSOCProtection._resolve_limits()` 額外防禦**：`soc_max` / `soc_min` 在 clamp 前先驗證 `is_non_finite_float()`，避免 NaN 通過 clamp 後 `<` 比較永遠 False 而無聲繞過 BUG-003 反轉檢查與 SOC 保護
- **`RuntimeParameters` 值域 clamp (SEC-004)**：`DynamicSOCProtection._resolve_limits()` 對 `soc_max` / `soc_min` clamp 到 `[0, 100]`；`GridLimitProtection.evaluate()` 對 `grid_limit_pct` clamp 到 `[0, 100]`。防止 EMS/Modbus 寫入無物理意義的值（如 `soc_max=200` 讓 SOC 上限保護永不觸發）
- **`GroupReader.read_many()` partial failure 不再吞掉成功結果 (SEC-016)**：並行模式 `asyncio.gather()` 加 `return_exceptions=True` + 逐結果檢查；只對 `Exception` 子類別 log warning + continue，其他 `BaseException`（`CancelledError` / `SystemExit` / `KeyboardInterrupt`）正常 re-raise，避免吞掉 lifecycle 停機與系統中斷信號（舊行為：整批 `latest_values` 不更新，控制策略基於陳舊資料決策）

### Performance

- **`AsyncCANDevice._snapshot_loop` 絕對時間錨定 (WI-TD-101)**：改採 work-first 絕對時間錨定，sleep delay 補償 work 耗時，消除累積時序漂移（修復前 interval=0.1s, work=0.02s → 1 小時漂移 720s）。落後超過一個 interval 時自動重設 anchor 避免 burst catch-up
- **`PeriodicSendScheduler._send_loop` 絕對時間錨定 (WI-TD-102)**：每個 CAN ID 獨立錨定，sleep delay 補償 send_callback 耗時。Exception 路徑保留固定 `sleep(interval)` 並重新錨定避免緊迴圈
- **`AsyncModbusDevice._read_loop` 絕對時間錨定 (WI-TD-103)**：取代原 elapsed-subtraction 模式。Reconnect 成功後重設 anchor 避免重連瞬間 burst catch-up 壓垮設備
- **三個迴圈共用 `next_tick_delay()` helper**：CAN snapshot / PeriodicSender / Modbus read_loop 統一呼叫 `csp_lib.core._time_anchor.next_tick_delay()`，移除三處重複的 inline 錨定邏輯，避免後續維護分叉

## [0.7.1] - 2026-04-06

### Added
- **`BackgroundFlushMixin`** (`csp_lib.core.flush_mixin`): 背景定期 flush 迴圈的共用 Mixin（internal，不公開匯出），提供 `_start_flush_loop()` / `_stop_flush_loop()` / `_flush_once()` hook 骨架 (UL-H1)
- **`DeviceEventType`** (`csp_lib.equipment.device.events`): 設備事件類型 StrEnum（internal，不公開匯出），與現有 `EVENT_xxx` 字串常數共存且完全相等 (UL-E)
- **`CTX_*` 常數** (`csp_lib.controller.core.constants`): `StrategyContext.extra` 常用 key 常數化（internal），包含 `CTX_FREQUENCY`、`CTX_VOLTAGE`、`CTX_METER_POWER` 等 7 個 (UL-A)
- **`UnifiedConfig.batch_uploader`** 欄位: 新增 `batch_uploader: BatchUploader | None = None`，作為 `mongo_uploader` 的推薦替代 (TD-001)
- **`ClampPriority`** enum (`csp_lib.controller.system`): CascadingStrategy 的限幅優先級，`P_FIRST`（保 P 削 Q）或 `Q_FIRST`（保 Q 削 P）
- **CAN exception error context**: `CANError` 新增 `can_id: int | None` 和 `bus_index: int | None` keyword-only 參數，自動格式化為 `[bus=N, can_id=0xNNN]` 前綴；子類別自動繼承

### Changed
- **QVStrategy `p_target=0.0`**: QV 策略只控制 Q，P 不再從 `last_command` 帶入（改為 `0.0`）；混合 P+Q 控制請用 cascade/mode switch。v0.8.0 將引入 `Command.NO_CHANGE` sentinel 完整方案
- **CascadingStrategy 重寫為加法式**: 每層策略輸出「貢獻量」（非總量），逐層相加後依 `ClampPriority` 限幅；新增 `ClampPriority` enum（`P_FIRST` 保 P 削 Q、`Q_FIRST` 保 Q 削 P）；取代舊的 delta-based clamping
- **Config frozen 對齊**: 12 個 Config dataclass 加 `frozen=True, slots=True`：`DroopConfig`、`FPConfig`、`IslandModeConfig`、`LoadSheddingConfig`、`PQModeConfig`、`PVSmoothConfig`、`QVConfig`、`FFCalibrationConfig`、`PowerCompensatorConfig`、`UnifiedConfig`、`SystemControllerConfig`、`GridControlLoopConfig`
- **全庫 leaf frozen dataclass 補 `slots=True`**: 約 80 個無繼承關係的 `@dataclass(frozen=True)` 類別加上 `slots=True`，減少記憶體使用（`PointDefinition` 繼承鏈推遲到 v0.8.0）(TD-021)
- **型別標註現代化**: `from typing import Type` → `type[T]` (TD-008)；`Optional[X]` → `X | None` 於 controller/services、controller/strategies、mongo 層共 20 處 (TD-011)
- **`Any` 型別收窄**: `SystemControllerConfig.runtime_params` 從 `Any` 收窄為 `RuntimeParameters | None`；`orchestrator._execute_device_action` device 參數從 `Any` 收窄為 `AsyncModbusDevice`
- **`__all__` 補齊**: `command.py`、`context.py`、`execution.py`、`strategy.py`、`base.py` 等 5 個高優先檔案
- **`modbus/clients/base.py`**: `__aexit__` 補齊完整型別標註，移除 `# type: ignore`

### Fixed
- **`_build_device_snapshots` 過濾無 capability 設備**: `SystemController._build_device_snapshots()` 現在只納入具備至少一個 `capability_command_mappings` 中 capability 的設備，避免 meter 等非被控設備灌入 `PowerDistributor` 分母導致分配比例錯誤（如 `EqualDistributor` 200/3=66.67 → 200/2=100）
- **`TransportAdapter` docstring**: 移除不存在的 `send_override()` 方法說明 (TD-010)
- **`modbus_server/server.py`**: `_PymodbusDataBlock` / `_EmptyBlock` 6 個方法補齊 return type (TD-018)
- **Import 防護統一**: `cluster`、`grpc`、`redis`、`gui`、`monitor` 模組加入 `try/except ImportError` 防護，未安裝 optional dependency 時給出清楚安裝提示 (TD-013, TD-015, TD-025, TD-026, TD-027)

### Examples
- **全面重整**: 19 個舊範例重整為 14 個新範例 + README.md 學習指南
- **全部可執行**: 所有範例使用 SimulationServer，`python examples/XX_xxx.py` 即可運行，無需真實硬體
- **4 級學習路徑**: Beginner(01-02) → Intermediate(03-05) → Advanced(06-09) → Expert(10-14)
- **移除 deprecated API**: SOCProtection→DynamicSOCProtection, mongo_uploader→batch_uploader
- **新增範例**: 日誌系統(13)、運行時參數(14)、微電網模擬(12)、ModbusGateway(10)

### Documentation
- **Guide: ModbusGateway 設定** (`docs/13-Guides/ModbusGateway Setup.md`): 完整設定指南（GatewayConfig、RegisterMap、資料同步、寫入驗證、Watchdog）(DOC-060)
- **Guide: Capability-driven 部署驗證** (`docs/13-Guides/Capability-driven Deployment.md`): CapabilityRequirement + preflight_check 流程 (DOC-061)
- **Guide: 自訂資料庫後端** (`docs/13-Guides/Custom Database Backend.md`): BatchUploader Protocol + non-MongoDB 實作範例 (DOC-062)
- **Architecture 圖更新**: System Diagrams 加入 ModbusGateway 整合架構圖 (DOC-063)
- **Data Flow 更新**: 加入 CommandProcessor pipeline + PowerCompensator FF+I 閉環流程圖 (DOC-064)

### CI/CD
- **macOS CI**: 測試矩陣新增 `macos-latest`，覆蓋 Ubuntu + Windows + macOS 三平台
- **Coverage threshold**: CI 中強制 `--fail-under=80`（目前 88%），僅在 Ubuntu runner 檢查

### Tests
- **Pipeline 整合測試**: 新增 `test_pipeline_integration.py`，18 個測試覆蓋 Strategy→Protection→Compensator→Router 端到端流程
- **Flaky sleep 修復**: `test_queue`(18處)、`test_device_group`(8處)、`test_watchdog`(5處) 的硬編碼 `asyncio.sleep` 改為 `wait_for_condition()` 輪詢同步
- **Missing return type**: 補齊 4 處缺少的 return type annotation

### Deprecated
- **`UnifiedConfig.mongo_uploader`**: 改用 `batch_uploader`，使用 `mongo_uploader` 時會觸發 `DeprecationWarning`，將於 v1.0.0 移除 (TD-001)

## [0.7.0] - 2026-04-05
### Added
- **`LogFilter`** (`csp_lib.core`): 模組等級過濾器，以最長前綴匹配決定每條 log record 是否輸出；可直接作為 loguru `filter` 參數使用；取代舊有重複的 `_filter` closure，統一放入 `csp_lib/core/logging/filter.py`
- **`SinkManager`** (`csp_lib.core`): 全域 Sink 生命週期管理單例；提供 `add_sink()` / `remove_sink()` / `remove_sink_by_name()` / `list_sinks()` / `get_sink()` / `remove_all()` / `set_level()` 操作；整合 `LogFilter` 進行模組等級控制
- **`SinkInfo`** (`csp_lib.core`): Sink 資訊 frozen dataclass，記錄 `sink_id`、`name`、`sink_type`、`level`、`is_active`
- **`FileSinkConfig`** (`csp_lib.core`): 檔案 Sink 配置 frozen dataclass，封裝 loguru file sink 所有參數（`path`、`rotation`、`retention`、`compression`、`level`、`format`、`enqueue`、`serialize`、`encoding`、`name`）；對齊 `@dataclass(frozen=True, slots=True)` 慣例
- **`LogContext`** (`csp_lib.core`): 結構化日誌上下文管理器；使用 `contextvars.ContextVar` 實現 async-safe correlation ID 綁定；支援同步 / 非同步 context manager 與 decorator 三種使用方式；`current()` / `bind()` / `unbind()` 靜態方法供快速操作
- **`LogCapture`** (`csp_lib.core`): 測試用日誌捕獲器；以 context manager 攔截 loguru 輸出；提供 `contains()` / `filter()` / `clear()` / `text` / `records` 等查詢 API
- **`CapturedRecord`** (`csp_lib.core`): 單筆捕獲 log 記錄 dataclass，含 `level`、`message`、`module`、`extra`、`time` 欄位
- **`RemoteLevelSource`** (`csp_lib.core`): 遠端 log 等級來源 `@runtime_checkable` Protocol，定義 `fetch_levels()` 與 `subscribe()` 介面，供 Redis / HTTP 等後端實作
- **`AsyncSinkAdapter`** (`csp_lib.core`): 非同步 Sink 轉接器；將 async handler 包裝為 loguru 可接受的同步 `write` 介面；內部以 thread-safe queue + asyncio drain task 橋接；佇列滿時靜默丟棄，避免阻塞 logger
- **`RedisLogLevelSource`** (`csp_lib.redis`): `RemoteLevelSource` 的 Redis 實作；透過 Redis Hash 儲存模組等級設定，Pub/Sub channel 提供即時變更通知；訊息格式 `"module:level"`
- **`SinkManager.add_file_sink(config)`**: 透過 `FileSinkConfig` 新增檔案 sink 的便利方法
- **`SinkManager.add_async_sink(handler)`**: 透過 `AsyncSinkAdapter` 新增非同步 sink 的便利方法，可指定 `max_queue_size`
- **`SinkManager.add_stderr_sink()`**: 新增 stderr sink 的便利方法
- **`SinkManager.attach_remote_source(source, poll_interval)`**: 連接遠端等級來源，立即拉取設定並啟動背景輪詢 task
- **`SinkManager.detach_remote_source()`**: 中斷遠端等級來源連線，取消輪詢 task
- **`add_file_sink(config)`** (`csp_lib.core`): 模組層便利函式，委派給全域 `SinkManager.add_file_sink()`
- **`DEFAULT_FORMAT`** (`csp_lib.core`): 帶 ANSI 色彩的預設 loguru 格式字串常數
- **環境變數覆蓋支援**: `configure_logging(env_prefix="CSP")` 可讀取 `CSP_LOG_LEVEL` / `CSP_LOG_FORMAT` / `CSP_LOG_ENQUEUE` / `CSP_LOG_JSON` / `CSP_LOG_DIAGNOSE` 覆蓋配置

### Changed
- **`configure_logging()` 新增 keyword-only 參數**: 新增 `enqueue`（預設 `False`）、`json_output`（預設 `False`）、`diagnose`（預設 `False`）、`env_prefix`（預設 `None`）；現在委派給 `SinkManager` 管理 sink 生命週期
- **`configure_logging()` 改為委派 `SinkManager`**: 函式現在透過 `SinkManager` 管理 sink；如需 manager 實例，可透過 `SinkManager.get_instance()` 取得
- **`diagnose=False` 為生產預設**: `configure_logging()` 與 `SinkManager.add_sink()` 預設 `diagnose=False`，防止 exception traceback 洩漏 Modbus 位址、Redis 密碼等敏感資訊（行為變更，非 breaking）
- **`set_level()` 不再 remove/re-add sink**: 改為委派給 `LogFilter.default_level` 或 `LogFilter.set_module_level()`，更新 dict 即生效，不需要重建所有 sink
- **`csp_lib/core/logging/` 子模組**: 原 `core/__init__.py` 中的日誌邏輯拆分至 `csp_lib/core/logging/` 子套件，含 `filter.py`、`sink_manager.py`、`file_config.py`、`context.py`、`capture.py`、`remote.py`、`async_sink.py`；`csp_lib.core` 頂層 `__all__` 保持向後相容

## [0.6.2] - 2026-04-05
### Added
- **`DeviceLinkConfig`** (`csp_lib.modbus_server`): frozen dataclass，宣告設備（PCS/Solar/Load/Generator）到電表的功率路由，支援 `loss_factor` 損耗因子
- **`MeterAggregationConfig`** (`csp_lib.modbus_server`): frozen dataclass，宣告多個子電表功率累加到父電表，支援任意深度聚合樹
- **`MicrogridSimulator.add_meter()`**: 支援多電表場景，第一個註冊的電表自動成為 default；`set_meter()` 與 `.meter` 屬性完整向後相容
- **`MicrogridSimulator.get_meter()`**: 依 ID 取得已註冊電表，不存在時拋 `KeyError`
- **`MicrogridSimulator.meters`**: 屬性，回傳所有已註冊電表的唯讀字典副本
- **`MicrogridSimulator.add_device_link()`**: 新增設備到電表的功率路由；驗證設備與電表已註冊，防止重複連結
- **`MicrogridSimulator.add_meter_aggregation()`**: 新增電表聚合，立即執行 Kahn 拓撲排序 + 循環偵測，失敗時自動回滾
- **`PowerMeterSimulator.reset_linked_power()`**: 重置每 tick 的功率累加器，由 `MicrogridSimulator.update()` 呼叫
- **`PowerMeterSimulator.add_linked_power()`**: 累加來自連結設備的功率，同一 tick 可多次呼叫
- **`PowerMeterSimulator.finalize_linked_reading()`**: 累加完畢後寫入 V/F 並計算衍生值（視在功率、功率因數、電流）
- **`PowerMeterSimulator.set_partial_reading()`**: 僅更新 P/Q 不覆蓋 V/F，供聚合電表在 Step 8 使用
- **`BMSSimConfig`** (`csp_lib.modbus_server`): frozen dataclass，BMS 模擬器配置，含 `capacity_kwh`、`initial_soc`、`cells_in_series`、`charge_efficiency` 等 11 個欄位
- **`BMSSimulator`** (`csp_lib.modbus_server`): 電池管理系統模擬器，追蹤 SOC（含充電效率）、pack 電壓（SOC 線性插值）、電流、電芯電壓與 5 位元告警 register；`soc` 和 `temperature` 為 writable 點位供 debug 測試
- **`MicrogridSimulator.add_bms()`**: 註冊 BMS 模擬器
- **`MicrogridSimulator.link_pcs_bms()`**: 連結 PCS 與 BMS，BMS 接管 SOC 計算；有 BMS 時 SOC 應從 BMS 讀取
- **`MicrogridSimulator.set_grid_voltage()` / `set_grid_frequency()`**: 電網 V/F override，傳 `None` 恢復 config 預設值
- **`MicrogridSimulator.set_voltage_curve()` / `set_frequency_curve()`**: 簡便 tuple API 設定 V/F 曲線，支援 step `(v, dur)`、ramp `(v, dur, end_v)`、rate `(v, dur, None, rate)` 三種格式
- **`MicrogridSimulator.set_voltage_behavior()` / `set_frequency_behavior()`**: 進階 API，直接傳入自訂 `CurveBehavior` 實例
- **`CurvePoint.end_value`**: 線性 ramp 終點值，`CurveBehavior` 在播放時自動線性插值
- **`CurvePoint.rate`**: 每秒變化率（如 `-0.01` Hz/s），`__post_init__` 自動計算 `end_value = value + rate × duration`；與 `end_value` 互斥
- **`CurvePoint.interpolate(progress)`**: 根據進度 (0~1) 計算 step/ramp 當前值
- **`examples/20_multi_meter_simulation.py`**: SimulationServer + 多電表 + BMS + 設備聯動 + V/F 曲線，支援 `--curve` 參數（`qv_ramp` / `fp_ramp` / `fp_step` / `voltage_sag`）

### Changed
- **`modbus_server` 所有 config dataclass 加入 `slots=True`**：對齊 library 慣例
- **`modbus_server` config 驗證改用 `ConfigurationError`**：從 `ValueError` 改為 `ConfigurationError`，對齊錯誤階層
- **`BMSSimulator` 溫度模型簡化**：移除功率溫升，僅保留自然散熱；`temperature` 為 writable 點位，透過 Modbus 寫入 >55°C 觸發過溫告警
- **`CurveBehavior.update()` 支援線性插值**：當 `CurvePoint.end_value` 有值時，根據已播放時間自動在 start→end 間線性插值

### Fixed
- **電表聚合符號 bug**：`MicrogridSimulator.update()` Step 8 電表聚合改用 `_raw_net_p`（原始物理淨功率）而非 `active_power`（已套用 `power_sign`），修正混合符號電表（不同 `power_sign` 值）聚合結果錯誤

## [0.6.1] - 2026-04-04
### Added
- **`NullBatchUploader`** (`csp_lib.manager.in_memory_uploader`): no-op `BatchUploader` 實作，靜默丟棄所有資料，用於不需要持久化的場景
- **`InMemoryBatchUploader`** (`csp_lib.manager.in_memory_uploader`): dict-based `BatchUploader` 實作，儲存於記憶體，適合測試與零外部依賴部署
- **`InMemoryAlarmRepository`** (`csp_lib.manager.alarm.in_memory`): dict-based `AlarmRepository` Protocol 實作，支援告警 CRUD、resolve、list_active
- **`InMemoryCommandRepository`** (`csp_lib.manager.command.in_memory`): dict-based `CommandRepository` Protocol 實作，支援指令紀錄與查詢
- **`InMemoryScheduleRepository`** (`csp_lib.manager.schedule.in_memory`): dict-based `ScheduleRepository` Protocol 實作，包含從 `MongoScheduleRepository` 提取的時間匹配邏輯（`matcher.py`）
- **`DeviceRegistry.get_capability_map()`** (`csp_lib.integration`): 回傳 capability → device_ids 結構化快照，供 dashboard 與策略層查詢
- **`DeviceRegistry.get_capability_map_text()`**: 人類可讀文字表格格式，供 CLI log 輸出能力分布
- **`DeviceRegistry.capability_health(cap)`**: 回傳指定能力的總設備數、響應中設備數與各設備狀態，供 `SystemController.health()` 整合
- **`DeviceRegistry.refresh_capability_traits(device_id)`**: 設備 reconfigure 後重新掃描 capabilities 並更新 trait index
- **`CapabilityBinding.metadata`** (`csp_lib.equipment.device`): frozen dataclass 上的 per-capability 元資料欄位（如 `step_kw`、`response_ms`、`rated_kw`）
- **`EVENT_CAPABILITY_ADDED` / `EVENT_CAPABILITY_REMOVED`** (`csp_lib.equipment.device`): 能力變更事件，`add_capability()` / `remove_capability()` 時發射
- **GUI `GET /capabilities`**: 序列化 capability map 為 JSON，供前端 dashboard 顯示能力分布
- **GUI `GET /capabilities/{name}/health`**: 回傳指定能力的健康狀態 JSON，含 total/responsive/device_statuses
- **`examples/19_custom_database.py`**: InMemory 全套（`NullBatchUploader` + `InMemoryAlarmRepository` + `InMemoryCommandRepository` + `UnifiedDeviceManager`）零外部依賴示範
- **文件元資料基礎設施**: 全部 153 個 docs 注入 `updated:` 和 `version:` frontmatter 欄位；`Tag Taxonomy.md` 新增 `status/stale` tag 和 Metadata Fields section；Templates 加入 Quick Example section
- **17 個新文件頁面**:
  - `02-Core/RuntimeParameters.md` — Thread-safe 即時參數容器
  - `04-Equipment/DOActions.md` — DOMode、DOActionConfig、Actionable Protocol
  - `05-Controller/DroopStrategy.md` — 下垂一次頻率響應策略
  - `05-Controller/PowerCompensator.md` — FF + I 閉環功率補償器
  - `05-Controller/FFCalibrationStrategy.md` — FF Table 步階校準策略
  - `05-Controller/FFTableRepository.md` — FF Table 持久化 Protocol
  - `05-Controller/RampStopStrategy.md` — 斜坡降功率策略
  - `05-Controller/DynamicSOCProtection.md` — 動態 SOC 保護
  - `05-Controller/GridLimitProtection.md` — 外部功率限制保護
  - `05-Controller/CommandProcessor.md` — Post-Protection 命令處理器 Protocol
  - `06-Integration/CapabilityRequirement.md` — 能力需求 + 聚合品質
  - `07-Manager/BatchUploader.md` — BatchUploader Protocol
  - `16-ModbusGateway/` — 6 頁完整模組文件（MOC、Server、RegisterMap、WriteValidation、SyncSources、Config）
- **Version History 補齊**: v0.5.0、v0.5.1、v0.5.2、v0.6.0 版本歷史條目
- **Reference 索引更新**: All Classes、All Config Classes、All Enums、Import Paths、UML Diagrams 補齊 v0.5.0~v0.6.0 新增項目

### Changed
- **152 個既有文件全面審查**: 逐檔比對 source code 確認 API 正確性，補充 Quick Example
- **13 個重點檔案 API 更新**: SystemController（preflight_check/builder）、DeviceRegistry（validate_capabilities）、AsyncModbusDevice（DO action）、StrategyContext（params）、RedisClient（Sentinel TLS）、Error Hierarchy（3 新 Error）、DataUploadManager/UnifiedDeviceManager（BatchUploader 型別）、AlarmPersistenceManager（timestamp 更名）等
- **SOCProtection 加入 deprecated callout** 指向 DynamicSOCProtection
- **Architecture/Guides 文件修正**: Design Patterns 和 Full System Integration 中 Builder API 方法名修正

## [0.6.0] - 2026-04-03

### Added
- **`BatchUploader` Protocol** (`csp_lib.manager.base`): `@runtime_checkable` Protocol，提供 `register_collection()` + `enqueue()` 介面，解耦 `DataUploadManager` 與 `StatisticsManager` 對具體 `MongoBatchUploader` 的直接依賴
- **`DOMode` 列舉** (`csp_lib.equipment.device.action`): `PULSE`、`SUSTAINED`、`TOGGLE` — 三種離散輸出動作模式
- **`DOActionConfig` frozen dataclass** (`csp_lib.equipment.device.action`): 宣告式 DO 動作配置，含 `point_name`、`label`、`mode`、`pulse_duration`、`on_value`、`off_value`
- **`Actionable` Protocol** (`csp_lib.equipment.device.action`): `@runtime_checkable` Protocol，公開 `available_do_actions` + `execute_do_action(label)` — 統一 ET7050/ET7051 與 PCS/BMS 設備的 DO 控制介面
- **`AsyncModbusDevice.configure_do_actions()`**: 載入 `list[DOActionConfig]` 以啟用宣告式 PULSE/SUSTAINED/TOGGLE 執行
- **`AsyncModbusDevice.execute_do_action(label)`**: 執行指定 DO 動作；PULSE 模式在 `pulse_duration` 後自動取消
- **`AsyncModbusDevice.available_do_actions`**: 屬性，回傳目前已配置的 `list[DOActionConfig]`
- **`AsyncModbusDevice.cancel_pending_pulses()`**: 取消所有排程中的 pulse-off 任務（設備關機時自動呼叫）
- **`CapabilityRequirement` dataclass** (`csp_lib.integration.schema`): `capability`、`min_count`、`trait_filter` — 供 preflight validation 使用
- **`AggregationResult` dataclass** (`csp_lib.integration.schema`): `value`、`device_count`、`expected_count`、`quality_ratio` — 聚合品質元資料，供策略層判斷資料可信度
- **`CapabilityContextMapping.min_device_ratio`**: 可選比例門檻；當響應設備少於此比例時，聚合回傳 `default` 並發出警告
- **`DeviceRegistry.validate_capabilities(requirements)`**: 回傳未滿足 `CapabilityRequirement` 的可讀訊息列表
- **`SystemControllerConfig.capability_requirements`**: `CapabilityRequirement` 列表，在 `preflight_check()` 時驗證
- **`SystemControllerConfig.strict_capability_check`**: 設為 `True` 時，`SystemController.preflight_check()` 在需求未滿足時 raise `ConfigurationError`
- **`SystemController.preflight_check()`**: 執行 `validate_capabilities` 驗證已註冊的能力需求；可在 `async with` 前呼叫，提前發現部署不匹配
- **`SystemControllerConfigBuilder.require_capability(requirement)`**: fluent 方法，新增 `CapabilityRequirement`
- **`SystemControllerConfigBuilder.strict_capability(enabled?)`**: fluent 方法，設定 `strict_capability_check`
- **Repository Protocol 拆分**: `AlarmRepository`、`CommandRepository`、`ScheduleRepository` Protocol 現在無需安裝 `motor` 即可匯入 — 具體 `MongoXxxRepository` 實作透過 `TYPE_CHECKING` 延遲匯入 motor

### Changed
- **`AlarmRecord.occurred_at` → `timestamp`**: 統一時間戳欄位命名，與 `DataUploadManager`、`StateSyncManager` 的 document 一致
- **`AlarmRecord.resolved_at` → `resolved_timestamp`**: 對稱重新命名
- **`WriteCommand.created_at` → `timestamp`**: 統一所有指令類型的時間戳欄位命名
- **`ActionCommand.created_at` → `timestamp`**: 與 WriteCommand 一致
- **`CommandRecord.created_at` → `timestamp`**: 與告警 schema 統一
- **`MongoAlarmRepository` 索引**: `ensure_indexes()` 改為索引 `timestamp` 和 `resolved_timestamp`（取代 `occurred_at`/`resolved_at`）
- **`MongoCommandRepository` 索引與排序**: `list_by_device()` 改依 `timestamp` 排序；`ensure_indexes()` 改索引 `timestamp`
- **`DataUploadManager` 建構子型別**: 接受 `BatchUploader`（Protocol）取代 `MongoBatchUploader` — 既有使用 `MongoBatchUploader` 的程式碼透過結構子型別繼續運作
- **`StatisticsManager` 建構子型別**: 同 `DataUploadManager` 變更
- **`UnifiedConfig.mongo_uploader`**: 型別從 `MongoBatchUploader` 放寬為 `BatchUploader` — 接受任何實作 BatchUploader Protocol 的上傳器

### Fixed
- **靜默低容量聚合**: 設定 `min_device_ratio` 的 `CapabilityContextMapping` 現在會在響應設備不足時發出警告並回傳 `default`，而非靜默計算不完整的聚合結果

## [0.5.2] - 2026-04-02

### Added
- **DroopStrategy 測試** (`tests/controller/test_droop_strategy.py`): 38 test cases 涵蓋正常執行、死區、邊界、無頻率資料 fail-safe、config 驗證
- **RampStopStrategy 測試** (`tests/controller/test_ramp_stop_strategy.py`): 11 test cases 涵蓋斜坡降功率、到零停止、中途恢復、lifecycle
- **CommandProcessor pipeline 測試**: 3 test cases 驗證 pipeline 串接、多 processor 順序、空 pipeline
- **SystemControllerConfigBuilder 測試** (`tests/integration/test_config_builder.py`): 11 test cases 涵蓋 fluent chain、互斥驗證、完整 build
- **WriteRule (Gateway) 測試** (`tests/modbus_gateway/test_write_rule.py`): 15 test cases 涵蓋 clamp/reject 模式、部分邊界、驗證
- **FFTableRepository 測試** (`tests/controller/test_ff_table_repository.py`): 17 test cases 涵蓋 JSON 讀寫、MongoDB async、空表處理、Protocol 一致性
- **PowerCompensator 補充測試**: 10 test cases 新增 transient gate (hold_cycles)、EMA 濾波、飽和重設、FF 繼承
- **Root conftest.py 共用 fixture**: `make_mock_device`、`mock_strategy`、`mock_registry` 跨模組共用
- **pytest markers 補齊**: `integration`、`flaky`、`requires_external` 標記定義
- **Slow test 標記**: 6 個慢速測試標記 `@pytest.mark.slow`，支援 `pytest -m "not slow"` 快速開發
- **pytest-xdist 平行測試**: 啟用 `addopts = "-n auto"`，測試執行時間從 120s 降至 ~48s

### Fixed
- **AlarmRecord.alarm_code 未寫入 MongoDB** (`csp_lib.manager.alarm.persistence`): `_on_alarm_triggered` 和 `_on_disconnected` 建立 AlarmRecord 時漏設 `alarm_code`，導致 MongoDB 中 alarm_code 欄位為空字串

### Changed
- **DeviceStateSubscriber log 等級修正** (`csp_lib.integration.distributed.subscriber`): Redis 讀取失敗 log 從 `debug` 升至 `warning`（3 處：state / online / alarms）
- **DeprecationWarning 過濾收窄** (`pyproject.toml`): 從全局忽略改為只過濾已知第三方（pymodbus、motor、redis），自身 deprecation 警告正常顯示

## [0.5.1] - 2026-04-01
### Changed
- **錯誤階層擴充**: 新增 `StrategyExecutionError`、`ProtectionError`、`DeviceRegistryError` 結構化例外，取代裸 `RuntimeError` / `ValueError`
- **ModbusError 上下文**: `ModbusError` 子類別攜帶 `address`、`unit_id`、`function_code` 欄位，方便上層快速分類
- **Modbus 連線生命週期 log**: connect / disconnect / reconnect 事件統一以 INFO 等級記錄，含連線參數與耗時
- **Writer log 等級修正**: `ValidatedWriter` 寫入成功 log 從 DEBUG 降至 TRACE，減少正常運行時的 log 雜訊
- **靜默失敗修復**: `aggregator`、`base`、`scheduler` 捕獲例外後改為 `logger.error()` 並重新拋出或回傳預設值，不再靜默吞掉錯誤
- **Logger 命名統一**: 29 個檔案的 `get_logger()` 呼叫統一使用 `__name__`，確保 log 層級控制與過濾一致
- **WriteRejectedError 結構化 log** (`csp_lib.modbus_gateway.pipeline`): Validator 與 WriteRule 拒絕寫入時改用 `WriteRejectedError` 格式化訊息，log 等級從 DEBUG 升至 WARNING
- **Strategy Executor 錯誤上下文**: 策略執行失敗時 log 含 strategy name、SOC、context extra keys，修復潛在 UnboundLocalError
- **Device 事件處理 log**: `_process_values()` 和 alarm 評估例外不再靜默，加 warning log 含 device_id 和 point 上下文
- **ContextBuilder 映射失敗上下文**: transform/aggregate 失敗 log 含 mapping source、point_name、target field
- **Alarm Evaluator log**: `evaluator.py` 新增 logger，告警觸發/解除以 DEBUG 記錄；`mixins.py` 寫入成功 INFO → DEBUG
- **Cluster 例外鏈**: `sync.py`、`election.py` 所有 `except Exception` 加 `as e` 捕獲 + 重試/狀態上下文
- **loguru exception() 審計**: 可恢復錯誤從 `logger.exception()`（ERROR）改為 `logger.opt(exception=True).warning()`
- **DeviceRegistry 並發安全** (`csp_lib.integration.registry`): 加 `threading.Lock` 保護所有讀寫操作，防止並發修改崩潰
- **DeviceEventEmitter 優雅關閉** (`csp_lib.equipment.device.events`): stop() 改為 drain queue + handler 完成等待；emit() 未啟動時不入隊；handler 迭代前 copy 防並發修改
- **Device 重複註冊檢查** (`csp_lib.manager.device.manager`): register() 和 register_group() 檢查 duplicate device_id
- **DeviceConfig 驗證加強**: `reconnect_interval <= 0` 拒絕（防止 tight loop）
- **WriteRule 驗證加強**: `min_value > max_value` 拒絕
- **Redis Sentinel disconnect**: `disconnect()` 時釋放 `_sentinel` 引用，防止 Sentinel 連線洩漏
- **NotificationBatcher flush retry**: `_on_stop()` flush 失敗時重試一次，記錄 dropped notification 數量
- **CircuitBreaker 指數退避**: 加 `max_cooldown`、`backoff_factor` 參數，故障恢復時加 jitter 防止 thundering herd
- **ModbusRequestQueue 清理 log**: `stop()` 加 cancelled/done futures summary log
- **Device 狀態 asyncio.Lock** (`csp_lib.equipment.device.base`): `_status_lock` 保護 responsive/failure 狀態更新，防止並發競態
- **UnifiedDeviceManager 註冊 threading.Lock**: `_register_lock` 防止並發註冊重複訂閱
- **StatisticsEngine 去重**: `register_power_sum_devices()` 去重防止累計值翻倍
- **DataFeed attach 回滾**: `attach()` 部分失敗時回滾已訂閱的 handler，防止洩漏
- **Heartbeat point 驗證**: `_on_start()` 時驗證 heartbeat point 在目標設備上是否存在

### Added
- **WeakRef event listener** (`csp_lib.equipment.device.events`): `on(event, handler, weak=True)` 支援弱引用 handler，GC 後自動清理

## [0.5.0] - 2026-03-31
### Added
- **RuntimeParameters** (`csp_lib.core.runtime_params`): Thread-safe 即時參數容器
  - 支援 `get` / `set` / `update` / `snapshot` / `delete` / `setdefault` 操作
  - Observer pattern：`on_change(callback)` 在值變更時觸發通知（在鎖外同步呼叫）
  - 以 `threading.Lock` 保護，Modbus hook thread 與 asyncio event loop 之間安全存取
  - 適用於需從外部系統（EMS / Modbus / Redis）即時推送的參數（如 SOC 上下限、功率限制）
- **CommandProcessor Protocol** (`csp_lib.controller.core.processor`): Post-Protection 命令處理器
  - `@runtime_checkable Protocol`，定義 `async def process(command, context) -> Command` 介面
  - 插入於 `ProtectionGuard` 與 `CommandRouter` 之間，支援功率補償、命令日誌、審計追蹤
  - `SystemControllerConfig` 新增 `post_protection_processors` 欄位以組合多個處理器
- **DroopStrategy** (`csp_lib.controller.strategies.droop_strategy`): 標準下垂一次頻率響應策略
  - 根據頻率偏差透過下垂公式計算功率：`gain = 100 / (f_base × droop)`
  - `DroopConfig` 可配置下垂係數、死區寬度、基準頻率、最大 AFC 功率與執行週期
  - 支援 `schedule_p + dreg_power` 疊加，自動 clamp 於額定功率範圍
  - `context.extra` 無頻率資料時維持上一次命令（fail-safe hold）
- **PowerCompensator** (`csp_lib.controller.compensator`): 前饋 + 積分閉環功率補償器
  - 實作 `CommandProcessor` Protocol，可直接加入 `post_protection_processors`
  - 前饋表（FF table）按功率區間查表，補償 PCS 非線性與輔電損耗
  - 積分修正含 deadband、anti-windup、rate limiting
  - 穩態自動學習：I 項貢獻吸收進 FF 表，長期自適應
  - 暫態閘門：setpoint 變更後等 PCS 到位才啟動積分
  - FF 表持久化支援 `FFTableRepository` Protocol（可注入 JSON / MongoDB 等後端）
  - `PowerCompensator.async_init()` 支援 async repository（如 MongoDB）啟動後載入
  - `SystemController._on_start()` 自動呼叫 processors 的 `async_init()`
- **動態保護規則** (`csp_lib.controller.system.dynamic_protection`): 從 RuntimeParameters 讀取動態參數
  - `DynamicSOCProtection`：每次 `evaluate()` 從 `RuntimeParameters` 讀取 `soc_max` / `soc_min`，支援 EMS 即時更新
  - `GridLimitProtection`：外部功率限制保護（電力公司 / 排程上限）
  - `RampStopProtection`：故障 / 告警時斜坡降功率至 0（graceful ramp-down）；已標記 deprecated，建議改用 `RampStopStrategy`
- **RampStopStrategy** (`csp_lib.controller.strategies.ramp_stop`): 斜坡降功率策略
  - 替代 `RampStopProtection`，本質上是「接管控制」而非「修改數值」，更適合作為 Strategy
  - 使用實際 dt（monotonic clock）計算每步降幅，不依賴固定 interval
  - 搭配 `EventDrivenOverride` + `ModeManager(PROTECTION)` 使用
  - 不同停止原因可觸發不同策略：通訊中斷 → `RampStopStrategy`，告警 → `StopStrategy`
- **FFCalibrationStrategy** (`csp_lib.controller.calibration`): FF Table 步階校準策略
  - 維護型一次性操作（類似 SOC 校正），自動遍歷各功率 bin 量測 FF ratio
  - 狀態機：IDLE → STEPPING → DONE，完成後寫入 `PowerCompensator` FF Table
  - 支援 `on_complete` callback，可配合 `RuntimeParameters` 或 Redis 觸發
  - `FFCalibrationConfig` 可配置步幅、穩態門檻、settle wait 等
- **FFTableRepository Protocol** (`csp_lib.controller.compensator`): FF Table 持久化介面
  - `JsonFFTableRepository`：JSON 檔案持久化（預設，向後相容）
  - `MongoFFTableRepository`：MongoDB 持久化（async save + async_load）
  - `PowerCompensator` 新增 `repository` 參數，可注入任意後端
  - `PowerCompensator.load_ff_table(table)` 方法供外部校準或 async load 使用
- **StrategyContext.params** (`csp_lib.controller.core.context`): 系統參數直接引用
  - 新增 `params: RuntimeParameters | None` 欄位，區隔系統參數（EMS 指令）與設備讀值（extra）
  - `SystemControllerConfig` 新增 `runtime_params` 欄位，`ContextBuilder` 自動注入
  - 向後相容：`params=None` 為預設值，不影響現有使用 extra 的程式碼
- **ModbusGatewayServer** (`csp_lib.modbus_gateway`): 完整 Modbus TCP Gateway Server 模組
  - 宣告式暫存器映射（`GatewayRegisterDef`），支援 HR（Holding）/ IR（Input）分區
  - Write validation chain：`AddressWhitelistValidator`、composable `WriteRule` Protocol（見下方）
  - Write hooks：`RedisPublishHook`、`CallbackHook`、`StatePersistHook`
  - 資料同步來源：`RedisSubscriptionSource`、`PollingCallbackSource`
  - 通訊 watchdog：含 timeout / recovery 回呼（`CommunicationWatchdog`）
  - Thread-safe pymodbus 整合，含 asyncio bridge
  - `ModbusGatewayServer` 實作 `AsyncLifecycleMixin`，透過 `async with` 管理完整生命週期
- **WriteRule Protocol** (`csp_lib.modbus_gateway.protocol`): 可組合寫入規則介面
  - `apply(register_name, value) -> (value, rejected)` 簽名，支援值轉換與拒絕
  - **RangeRule**: 連續範圍驗證，支援 clamp / reject 模式（取代原 `WriteRule` dataclass）
  - **AllowedValuesRule**: 離散值白名單（如模式暫存器只接受 `{0, 1, 3, 7}`）
  - **StepRule**: 步進量化（如 `step=0.5` 對齊 0.5 kW 解析度），永不拒絕
  - **CompositeRule**: 串接多個 rule 依序套用，任一拒絕即短路
- **SystemControllerConfigBuilder** (`csp_lib.integration.system_controller`): Fluent builder
  - `SystemControllerConfig.builder()` 回傳 builder 物件，支援鏈式呼叫
  - `.map_context()` / `.map_command()` / `.protect()` / `.processor()` / `.params()` 等方法
  - 不破壞現有 dataclass 直接建構方式（純加法）

### Changed
- **DRegStrategy → DroopStrategy** (`csp_lib.controller.strategies.droop_strategy`): 重新命名
  - `DRegConfig` → `DroopConfig`，`DRegStrategy` → `DroopStrategy`
  - `max_dreg_power` → `max_droop_power`，檔案 `dreg_strategy.py` → `droop_strategy.py`
- **StrategyContext** (`csp_lib.controller.core.context`): 新增 `params` 欄位（`RuntimeParameters | None`）
  - 系統參數與設備讀值分離：`params` 放 EMS 指令/保護設定，`extra` 放頻率/功率等設備讀值
  - `ContextBuilder` 新增 `runtime_params` 參數，build 時自動注入
- **SOCBalancingDistributor** (`csp_lib.integration.distributor`): 新增個別設備功率上限參數
  - `per_device_max_p` 與 `per_device_max_q`：對各設備的輸出做硬體 clamp
  - 四次算法：clamp → 溢出重分配 → 再次 clamp → 二次溢出按剩餘 headroom 分配，確保總容量足夠時不會少分配
- **RedisClient** (`csp_lib.redis.client`): 功能擴充
  - `TLSConfig.ca_certs` 改為 Optional（`cert_reqs="none"` 時可不提供 CA 憑證）
  - 新增 `pubsub()` 方法，回傳 redis-py PubSub 實例以供 Pub/Sub 操作
  - 新增 `scan()` 方法，支援增量 key 掃描（cursor-based iteration）
- **WritePipeline** (`csp_lib.modbus_gateway.pipeline`): 寫入規則改用 `WriteRule` Protocol
  - `_apply_rule` 簡化為委派 `rule.apply()`，不再內建 min/max/clamp 邏輯
  - `write_rules` 參數型別從 `Sequence[WriteRule]` 改為 `Mapping[str, WriteRule]`（name → rule 映射）

### Fixed
- **SOCBalancingDistributor** (`csp_lib.integration.distributor`): 修復 clamp 溢出重分配後二次溢出被丟棄的問題
  - 當 Pass 2 重分配導致新設備超限時，Pass 3 re-clamp 產生的溢出未被分配，造成總功率不足
  - 新增 Pass 4：二次溢出按剩餘 headroom 分配給未飽和設備，確保總容量足夠時功率守恆

### Deprecated
- **RampStopProtection** (`csp_lib.controller.system.dynamic_protection`): 建議改用 `RampStopStrategy` + `EventDrivenOverride`
  - RampStop 本質上是「接管控制」而非「修改數值」，更適合作為 Strategy
  - `RampStopProtection` 保留但不再建議使用

## [0.4.3] - 2026-03-16

* fix: hot fix cluster dependency problem.

* feat: add wheel installation with extras and import verification

## [0.4.2] - 2026-03-13

### Changed
- **Build**: 移除 Cython build pipeline，改為純 Python 發佈 (#25)
- **CI/CD**: 新增版本自動化、品質門檻、release workflow (#22)
- **CI/CD**: 新增 pytest-xdist 平行測試執行與 asyncio auto mode (#24)

### Fixed
- **Modbus Request Queue**: 修復 worker 信號遺失（clear 後 re-check total_size）和 submit TOCTOU（size 檢查移入 lock 內）(#19, #20)
- **StrategyExecutor**: 修復 PopOverride bypass 後 executor 卡在 triggered mode 無法恢復的問題 (#18)
- **Type Safety**: 修復 11 個檔案共 45 個 mypy type errors (#23)

## [0.4.1] - 2026-03-10

### Fixed
- **Installation**: 修復安裝失敗問題 (#15)

## [0.4.0] - 2026-03-09

### Added
- **動態點位管理** (`csp_lib.equipment.device`):
  - `ReconfigureSpec`: frozen dataclass，指定要替換的組件（`always_points`、`rotating_points`、`write_points`、`alarm_evaluators`、`capability_bindings`），`None` 表示保持不變
  - `AsyncModbusDevice.reconfigure(spec)`: 執行期動態重新配置點位，自動停止/恢復讀取迴圈，透過 `AlarmStateManager.export_states()` / `import_states()` 保留告警狀態，發出 `reconfigured` 事件
  - `AsyncModbusDevice.restart()`: 重啟讀取迴圈（stop + start），發出 `restarted` 事件
  - 點位開關 API：`disable_point(name)`、`enable_point(name)`、`is_point_enabled(name)`、`disabled_points` property（`frozenset`）
  - 點位查詢 API：`read_points`、`rotating_read_points`、`write_point_names`、`all_point_names`、`get_point_info()` → `list[PointInfo]`
  - `PointInfo`: frozen dataclass，點位詳細資訊（name、address、data_type、direction、enabled、read_group、metadata）
- **新事件** (`csp_lib.equipment.device.events`):
  - `EVENT_RECONFIGURED` / `ReconfiguredPayload(device_id, changed_sections)`: 動態重新配置完成
  - `EVENT_RESTARTED` / `RestartedPayload(device_id)`: 讀取迴圈重啟
  - `EVENT_POINT_TOGGLED` / `PointToggledPayload(device_id, point_name, enabled)`: 點位啟用/停用
- **ReadScheduler 動態更新** (`csp_lib.equipment.transport`):
  - `ReadScheduler.update_groups(always_groups, rotating_groups)`: 動態更新分組，`None` 表示保持不變，更新 `rotating_groups` 時自動重置輪替索引
- **AlarmStateManager 狀態遷移** (`csp_lib.equipment.alarm`):
  - `AlarmStateManager.export_states()`: 匯出所有告警狀態的 shallow copy
  - `AlarmStateManager.import_states(states)`: 匯入告警狀態，對已存在的代碼覆蓋計數與時間欄位
- **Hierarchical Control Protocols** (`csp_lib.integration.hierarchical`):
  - `SubExecutorAgent`: runtime_checkable Protocol for remote sub-executor coordination (SCADA -> Area -> Site -> Device)
  - `TransportAdapter`: runtime_checkable Protocol for pluggable transport backends (Redis / gRPC / HTTP)
  - `DispatchCommand`: frozen dataclass for hierarchical command dispatch with priority, timestamp, and source tracing
  - `ExecutorStatus` / `StatusReport`: frozen dataclasses for upward status reporting
  - `DispatchPriority`: IntEnum for command priority levels (NORMAL / SCHEDULE / MANUAL / PROTECTION)
- **gRPC Service Definitions** (`csp_lib/grpc/control.proto`):
  - `ControlDispatchService`: command dispatch, override management, health check
  - `StatusReportService`: status reporting and streaming subscription
- **Demo**: `examples/11_cascading_strategy.py` — CascadingStrategy deep dive showing delta-based clamping, multi-layer allocation, capacity constraints, edge cases, and hierarchical control preview
- **Demo**: `examples/demo_full_system.py` — full end-to-end system integration demo covering device creation, registry, control loop, mode switching, and protection
- **Architecture Doc**: `docs/architecture/hierarchical-control.md` — Mermaid diagrams, protocol reference, extension point mapping
- +49 new tests: 動態點位管理（`test_scheduler_update.py` 9 tests、`test_point_toggle.py` 17 tests、`test_device_reconfigure.py` 23 tests）
- +258 new tests: frozen dataclass configs, ReadScheduler, DeviceEventSubscriber, NaN/Inf propagation, Modbus exception handling, Protocol runtime checks
- +50 new tests: SubExecutorAgent Protocol compliance, TransportAdapter Protocol compliance, CascadingStrategy extended scenarios (delta clamping, context propagation, hierarchical integration, edge cases)

### Fixed
- **Integration re-exports**: Promoted `_apply_builtin_aggregate` to public API (`apply_builtin_aggregate`), added missing re-exports (`ComputeOffloader`, `ActionCommand`, `CommandResult`, `create_system_alarm_evaluators`), wrapped statistics import in try/except for optional dependency safety
- **Safety (fail-safe)**: Protection chain now outputs fail-safe (P=0, Q=0) instead of fail-open when a rule raises an exception
- **Safety (resource cleanup)**: `AsyncModbusDevice.__aexit__` and `SystemController._on_stop` now use try/finally to guarantee cleanup on error

## [0.3.3] - 2026-02-16

### Added
- **GroupControllerManager** (`csp_lib.integration`): 多群組控制器管理
  - GroupDefinition: 群組定義（ID、設備列表、配置）
  - GroupControllerManager: 管理多個獨立 SystemController 實例，每組擁有獨立的模式管理、保護機制與策略執行
- **integration 模組** (`csp_lib.integration`): Equipment-Controller 整合層
  - DeviceRegistry: Trait-based 設備查詢索引
  - ContextBuilder: 設備值 → StrategyContext 映射（支援多設備聚合）
  - CommandRouter: Command → 設備寫入路由（支援廣播寫入）
  - DeviceDataFeed: 設備 read_complete 事件 → PVDataService 餵入
  - GridControlLoop: 完整控制迴圈編排器（AsyncLifecycleMixin）
  - AggregateFunc / ContextMapping / CommandMapping / DataFeedMapping 宣告式映射 schema
- AsyncLifecycleMixin (`csp_lib.core`): 通用 async 生命週期管理
- DeviceEventSubscriber (`csp_lib.manager`): 設備事件訂閱基底類別
- 新增 GroupControllerManager 測試（26 個測試：驗證、查詢、模式管理、獨立性、生命週期、健康檢查）
- 新增 integration 模組測試（94 個測試）
- 新增 AsyncLifecycleMixin 單元測試
- 新增 core transform 綜合測試

### Changed
- 重構管理器使用新基底類別（AlarmPersistenceManager、DataUploadManager、
  StateSyncManager → DeviceEventSubscriber；DeviceManager、UnifiedDeviceManager、
  RedisCommandAdapter → AsyncLifecycleMixin）

## [0.3.2] - 2026-01-18

（版本號碼遞增，無功能變更）

## [0.3.1] - 2026-01-18

### Added
- **manager 模組** (`csp_lib.manager`): 系統整合管理層
  - AlarmPersistenceManager / MongoAlarmRepository
  - DeviceManager / DeviceGroup
  - DataUploadManager
  - WriteCommandManager / MongoCommandRepository
  - StateSyncManager
  - UnifiedDeviceManager / UnifiedConfig
- **redis 模組** (`csp_lib.redis`): Async Redis 客戶端（含 TLS / Sentinel）
- Equipment 增強: PowerFactorTransform、read_once、自動重連、GroupReader 並行讀取、
  CAN frame 解析器、高階 action 支援、模擬模組
- Controller 增強: GridController protocol、新控制策略、ActionCommand schema

### Changed
- Modbus: unit_id 從連線設定移至請求方法
- 全面使用 UTC 時區感知 datetime
- 策略生命週期 hooks 改為 async

### Fixed
- PointGrouper 狀態重置問題
- AlarmLevel 使用修正

## [0.3.0] - 2026-01-13

### Added
- **equipment 模組** (`csp_lib.equipment`): 設備抽象層
  - 資料轉換: ScaleTransform、RoundTransform、EnumMapTransform、ClampTransform、
    BoolTransform、InverseTransform、BitExtractTransform、ByteExtractTransform、
    MultiFieldExtractTransform
  - ProcessingPipeline: 轉換鏈管線
  - ReadPoint / WritePoint 定義
  - 告警系統: AlarmDefinition、BitMaskEvaluator、ThresholdEvaluator、TableEvaluator、
    AlarmStateManager（含遲滯邏輯）
  - 傳輸層: PointGrouper、GroupReader、ReadScheduler、ValidatedWriter
  - AsyncModbusDevice: 核心設備類別（週期讀取、連線管理、事件、告警）
  - DeviceConfig / DeviceEventEmitter
- CI/CD: trusted publishing + attestations

## [0.2.1] - 2026-01-11

### Fixed
- Modbus 共用客戶端資源引用計數修正（防止 connect() 重複呼叫時的計數錯誤）

## [0.2.0] - 2026-01-11

### Added
- **modbus 模組** (`csp_lib.modbus`): Modbus 通訊層
  - 資料型別: Int16/UInt16/Int32/UInt32/Int64/UInt64/Float32/Float64/ModbusString
  - ModbusCodec: 編解碼 API（支援 byte order / register order）
  - Async 客戶端: AsyncModbusTcpClient、AsyncModbusRtuClient、SharedPymodbusTcpClient
  - ModbusTcpConfig / ModbusRtuConfig
  - 自訂例外階層

## [0.1.1] - 2026-01-10

### Added
- Cython 編譯模組的 .pyi stub 自動產生
- GitHub Release 產物附加
- 二進位發佈的程式碼保護

## [0.1.0] - 2026-01-10

### Added
- **core 模組** (`csp_lib.core`): loguru 集中式 logging（get_logger / set_level / configure_logging）
- **mongo 模組** (`csp_lib.mongo`): Async MongoDB 批次上傳（MongoConfig / 批次佇列 / 上傳器）
- **controller 模組** (`csp_lib.controller`): 控制策略框架（Strategy / StrategyExecutor / PVDataService）
- CI/CD: GitHub Actions（PR lint+test / tag build+publish）
- Cython 二進位 wheel 建置（build_wheel.py）
- 套件更名為 csp0924_lib
