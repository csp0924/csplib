"""
Example 15: Runtime Parameters — 運行時參數與斷路器

學習目標:
  - RuntimeParameters: Thread-safe 即時參數容器
  - 動態修改參數（EMS 設定值注入）
  - WeakRef 事件處理: on_change() 變更通知
  - CircuitBreaker: 斷路器模式（CLOSED/OPEN/HALF_OPEN）
  - RetryPolicy: 重試策略配置

架構:
  EMS / SCADA
    ↓ (寫入 RuntimeParameters)
  RuntimeParameters (Thread-safe)
    ├─ ProtectionRule 讀取動態 SOC 限制
    ├─ Strategy 讀取功率限制
    └─ on_change() → 觀察者通知

  CircuitBreaker
    CLOSED ──(失敗達閾值)──→ OPEN ──(冷卻)──→ HALF_OPEN
      ↑──────(成功)────────────────────────────────↓

Run: uv run python examples/14_runtime_parameters.py
預計時間: 15 min
"""

import asyncio
import sys
import weakref

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from csp_lib.core import (
    CircuitBreaker,
    RetryPolicy,
    RuntimeParameters,
)

# ============================================================
# Step 1: RuntimeParameters 建立與基本操作
# ============================================================


def demo_basic_usage() -> None:
    """展示 RuntimeParameters 基本操作"""
    print("\n=== Step 1: RuntimeParameters 基本操作 ===")

    # 建立參數容器（初始值）
    params = RuntimeParameters(
        soc_max=95.0,
        soc_min=5.0,
        p_limit=500.0,
        q_limit=200.0,
        grid_limit_pct=100,
        mode="pq",
    )
    print(f"  建立: {params}")
    print(f"  參數數: {len(params)}")

    # 讀取
    soc_max = params.get("soc_max")
    print(f"\n  get('soc_max'): {soc_max}")
    print(f"  get('nonexistent'): {params.get('nonexistent')}")
    print(f"  get('nonexistent', 0): {params.get('nonexistent', 0)}")

    # 包含檢查
    print(f"\n  'soc_max' in params: {'soc_max' in params}")
    print(f"  'unknown' in params: {'unknown' in params}")

    # 原子性快照（防禦性拷貝）
    snap = params.snapshot()
    print(f"\n  snapshot(): {snap}")

    # keys()
    print(f"  keys(): {params.keys()}")


# ============================================================
# Step 2: 動態修改參數
# ============================================================


def demo_dynamic_update() -> None:
    """展示動態修改參數（模擬 EMS 注入）"""
    print("\n=== Step 2: 動態修改參數 (EMS 注入) ===")

    params = RuntimeParameters(
        soc_max=95.0,
        soc_min=5.0,
        p_limit=500.0,
    )

    # 單一設定
    print("  --- set() 單一設定 ---")
    params.set("soc_max", 90.0)
    print(f"  set('soc_max', 90.0) → {params.get('soc_max')}")

    # 批次更新
    print("\n  --- update() 批次更新 ---")
    params.update(
        {
            "soc_max": 85.0,
            "soc_min": 10.0,
            "p_limit": 300.0,
        }
    )
    print(f"  更新後: {params.snapshot()}")

    # setdefault（key 不存在才設定）
    print("\n  --- setdefault() ---")
    result = params.setdefault("q_limit", 200.0)
    print(f"  setdefault('q_limit', 200.0): {result} (新 key)")
    result = params.setdefault("soc_max", 99.0)
    print(f"  setdefault('soc_max', 99.0): {result} (已存在，不覆蓋)")

    # 刪除
    print("\n  --- delete() ---")
    params.delete("q_limit")
    print(f"  delete('q_limit') → 'q_limit' in params: {'q_limit' in params}")
    params.delete("nonexistent")  # 不存在時靜默忽略
    print("  delete('nonexistent'): 靜默忽略")


# ============================================================
# Step 3: on_change() 變更通知
# ============================================================


def demo_observers() -> None:
    """展示 on_change() 觀察者模式"""
    print("\n=== Step 3: on_change() 變更通知 ===")

    params = RuntimeParameters(p_limit=500.0, mode="pq")

    # 事件記錄
    events: list[tuple[str, object, object]] = []

    def on_param_change(key: str, old_value: object, new_value: object) -> None:
        events.append((key, old_value, new_value))
        print(f"    [callback] {key}: {old_value} → {new_value}")

    # 註冊觀察者
    params.on_change(on_param_change)
    print("  已註冊 on_change 觀察者")

    # 觸發變更
    print("\n  --- 觸發 set() ---")
    params.set("p_limit", 300.0)  # 值變更 → 觸發
    params.set("p_limit", 300.0)  # 相同值 → 不觸發
    print("  set('p_limit', 300.0) 再次: 相同值不觸發")

    # 批次更新觸發多次回呼
    print("\n  --- 觸發 update() ---")
    params.update({"p_limit": 200.0, "mode": "qv"})

    # delete 也會觸發
    print("\n  --- 觸發 delete() ---")
    params.delete("mode")

    print(f"\n  事件總數: {len(events)}")

    # 移除觀察者
    params.remove_observer(on_param_change)
    params.set("p_limit", 999.0)
    print(f"  移除觀察者後 set(): 事件總數不變 = {len(events)}")


# ============================================================
# Step 4: WeakRef 事件處理
# ============================================================


def demo_weakref_pattern() -> None:
    """展示 WeakRef 模式避免記憶體洩漏"""
    print("\n=== Step 4: WeakRef 事件處理 ===")

    params = RuntimeParameters(threshold=50.0)

    class ProtectionRule:
        """模擬保護規則，透過 WeakRef 訂閱參數變更"""

        def __init__(self, name: str, params_ref: RuntimeParameters) -> None:
            self.name = name
            self._threshold = params_ref.get("threshold", 50.0)

            # 使用 WeakRef 包裝回呼，避免 params 持有 self 的強引用
            weak_self = weakref.ref(self)

            def _on_change(key: str, old: object, new: object) -> None:
                obj = weak_self()
                if obj is not None:
                    obj._handle_change(key, old, new)

            self._callback = _on_change
            params_ref.on_change(_on_change)

        def _handle_change(self, key: str, old: object, new: object) -> None:
            if key == "threshold":
                self._threshold = float(new)  # type: ignore[arg-type]
                print(f"    [{self.name}] threshold 更新: {old} → {new}")

        @property
        def threshold(self) -> float:
            return self._threshold

    # 建立規則
    rule = ProtectionRule("SOC_Protection", params)
    print(f"  建立 ProtectionRule: threshold={rule.threshold}")

    # 從外部更新參數
    print("\n  --- 外部更新 threshold ---")
    params.set("threshold", 80.0)
    print(f"  rule.threshold: {rule.threshold}")

    # 刪除規則後，回呼變成 no-op（WeakRef 返回 None）
    print("\n  --- 刪除規則物件 ---")
    del rule
    params.set("threshold", 60.0)  # 回呼仍被呼叫但 weak_self() 返回 None
    print("  回呼安全忽略（WeakRef 已失效）")


# ============================================================
# Step 5: CircuitBreaker 斷路器模式
# ============================================================


def demo_circuit_breaker() -> None:
    """展示 CircuitBreaker 狀態轉換"""
    print("\n=== Step 5: CircuitBreaker 斷路器模式 ===")

    # 建立斷路器: 3 次失敗觸發，2 秒冷卻
    cb = CircuitBreaker(threshold=3, cooldown=2.0)
    print(f"  初始狀態: {cb.state.value}")
    print(f"  允許請求: {cb.allows_request()}")

    # 模擬正常操作
    print("\n  --- 正常操作 ---")
    cb.record_success()
    print(f"  record_success(): state={cb.state.value}, failures={cb.failure_count}")

    # 模擬連續失敗 → OPEN
    print("\n  --- 連續失敗 (threshold=3) ---")
    for i in range(3):
        cb.record_failure()
        print(f"  failure #{i + 1}: state={cb.state.value}, failures={cb.failure_count}, allows={cb.allows_request()}")

    print(f"\n  斷路器已開啟: state={cb.state.value}")
    print(f"  允許請求: {cb.allows_request()} (所有請求被擋)")

    # 等待冷卻 → HALF_OPEN
    print("\n  --- 等待冷卻 (模擬) ---")
    # 手動重置以示範（正常使用時等待 cooldown 過後自動轉 HALF_OPEN）
    cb.reset()
    print(f"  reset(): state={cb.state.value}, failures={cb.failure_count}")
    print(f"  允許請求: {cb.allows_request()}")

    # 示範帶指數退避
    print("\n  --- 指數退避 ---")
    cb2 = CircuitBreaker(threshold=2, cooldown=1.0, max_cooldown=60.0, backoff_factor=2.0)
    for round_num in range(3):
        for _ in range(2):
            cb2.record_failure()
        print(f"  round {round_num + 1}: state={cb2.state.value} (冷卻時間會指數增長)")
        cb2.reset()


# ============================================================
# Step 6: RetryPolicy
# ============================================================


def demo_retry_policy() -> None:
    """展示 RetryPolicy 重試策略配置"""
    print("\n=== Step 6: RetryPolicy 重試策略 ===")

    policy = RetryPolicy(max_retries=5, base_delay=0.5, exponential_base=2.0)
    print(f"  max_retries: {policy.max_retries}")
    print(f"  base_delay: {policy.base_delay}s")
    print(f"  exponential_base: {policy.exponential_base}")

    print("\n  延遲時間表:")
    for attempt in range(policy.max_retries):
        delay = policy.get_delay(attempt)
        print(f"    attempt {attempt}: {delay:.1f}s")


# ============================================================
# Step 7: 整合場景 — 動態 SOC 限制
# ============================================================


async def demo_integration() -> None:
    """整合展示: RuntimeParameters + CircuitBreaker"""
    print("\n=== Step 7: 整合場景 — 動態 SOC 保護 + 斷路器 ===")

    # 模擬 EMS 參數
    ems_params = RuntimeParameters(
        soc_max=95.0,
        soc_min=5.0,
        p_limit=500.0,
        operation_mode="discharge",
    )

    # 通訊斷路器
    comm_cb = CircuitBreaker(threshold=3, cooldown=5.0)

    # 觀察者: 記錄 EMS 參數變更
    def on_ems_update(key: str, old: object, new: object) -> None:
        print(f"    [EMS] {key}: {old} → {new}")

    ems_params.on_change(on_ems_update)

    # 模擬運行循環
    print("  --- 模擬控制循環 ---")
    simulated_soc = 80.0

    for cycle in range(5):
        print(f"\n  [Cycle {cycle + 1}]")

        # 檢查斷路器
        if not comm_cb.allows_request():
            print(f"    通訊斷路器開啟 (state={comm_cb.state.value}), 跳過")
            continue

        # 讀取動態參數
        soc_max = float(ems_params.get("soc_max", 95.0))
        soc_min = float(ems_params.get("soc_min", 5.0))
        p_limit = float(ems_params.get("p_limit", 500.0))
        mode = ems_params.get("operation_mode", "idle")

        # SOC 保護檢查
        if simulated_soc >= soc_max:
            print(f"    SOC={simulated_soc:.1f}% >= max={soc_max}%, 停止放電")
        elif simulated_soc <= soc_min:
            print(f"    SOC={simulated_soc:.1f}% <= min={soc_min}%, 停止充電")
        else:
            print(f"    SOC={simulated_soc:.1f}% 在範圍內 [{soc_min}, {soc_max}]")
            print(f"    P_limit={p_limit}kW, mode={mode}")

        # 模擬通訊（cycle 3 失敗）
        if cycle == 2:
            print("    模擬通訊失敗 (3 次)")
            for _ in range(3):
                comm_cb.record_failure()
            print(f"    斷路器: state={comm_cb.state.value}")
        else:
            comm_cb.record_success()

        # 模擬 EMS 更新參數
        if cycle == 1:
            print("    EMS 更新 SOC 限制和功率")
            ems_params.update(
                {
                    "soc_max": 90.0,
                    "soc_min": 10.0,
                    "p_limit": 300.0,
                }
            )

        if cycle == 3:
            print("    EMS 切換模式到充電")
            ems_params.set("operation_mode", "charge")

        simulated_soc -= 2.0  # 模擬 SOC 下降
        await asyncio.sleep(0.1)

    # 最終狀態
    print("\n  --- 最終狀態 ---")
    print(f"  參數: {ems_params.snapshot()}")
    print(f"  斷路器: state={comm_cb.state.value}, failures={comm_cb.failure_count}")


# ============================================================
# 主程式
# ============================================================


async def main() -> None:
    print("=" * 60)
    print("  Example 15: Runtime Parameters — 運行時參數與斷路器")
    print("=" * 60)

    demo_basic_usage()
    demo_dynamic_update()
    demo_observers()
    demo_weakref_pattern()
    demo_circuit_breaker()
    demo_retry_policy()
    await demo_integration()

    print("\n--- 完成 ---")
    print("\n要點回顧:")
    print("  1. RuntimeParameters: Thread-safe 即時參數容器（threading.Lock）")
    print("  2. set/update/delete: 值變更時自動觸發 on_change 觀察者")
    print("  3. snapshot(): 原子性淺拷貝，安全跨執行緒讀取")
    print("  4. WeakRef 模式: 避免觀察者導致的記憶體洩漏")
    print("  5. CircuitBreaker: CLOSED→OPEN→HALF_OPEN 狀態機")
    print("  6. RetryPolicy: 指數退避重試策略")
    print("  7. 整合: EMS 動態注入參數 + 通訊斷路器保護")


if __name__ == "__main__":
    asyncio.run(main())
