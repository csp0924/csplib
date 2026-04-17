# Changelog

本專案的所有重要變更皆記錄於此檔案。

格式基於 [Keep a Changelog](https://keepachangelog.com/)，版本號遵循 [Semantic Versioning](https://semver.org/)。

## [Unreleased]

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
