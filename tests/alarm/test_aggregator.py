# =============== AlarmAggregator Tests (v0.8.2 B3) ===============
#
# 測試 AlarmAggregator 多來源 OR 聚合、on_change 去重、observer 生命週期、
# bind_device / bind_watchdog / unbind、以及 thread safety。

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import MagicMock

import pytest

from csp_lib.alarm import AlarmAggregator, WatchdogProtocol

# ---------- 共用 helper ----------


class _MockDevice:
    """模擬 AsyncModbusDevice.on() 介面：註冊並回傳 unbinder。

    測試可直接呼叫 ``trigger(event, payload)`` 同步驅動 handler（不走 asyncio）。
    """

    def __init__(self, device_id: str = "dev_a") -> None:
        self.device_id = device_id
        self._handlers: dict[str, list[Any]] = {}

    def on(self, event: str, handler: Any) -> Any:
        self._handlers.setdefault(event, []).append(handler)

        def _unbind() -> None:
            if handler in self._handlers.get(event, []):
                self._handlers[event].remove(handler)

        return _unbind

    def trigger(self, event: str, payload: Any = None) -> None:
        """同步呼叫所有 handlers（async handler 僅取 coroutine 並關閉）。"""
        import asyncio

        for h in list(self._handlers.get(event, [])):
            coro = h(payload)
            # aggregator._on_triggered 是 async，coroutine 會立即執行 mark_source
            # 用 asyncio.run 跑單一 coroutine（aggregator callback 為純同步內部操作）
            if asyncio.iscoroutine(coro):
                try:
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(coro)
                    finally:
                        loop.close()
                except Exception:
                    coro.close()


class _MockWatchdog:
    """模擬 WatchdogProtocol：紀錄 on_timeout / on_recover 的 callback。"""

    def __init__(self) -> None:
        self._timeout_cbs: list[Any] = []
        self._recover_cbs: list[Any] = []

    def on_timeout(self, callback: Any) -> None:
        self._timeout_cbs.append(callback)

    def on_recover(self, callback: Any) -> None:
        self._recover_cbs.append(callback)

    def fire_timeout(self) -> None:
        import asyncio

        for cb in list(self._timeout_cbs):
            coro = cb()
            if asyncio.iscoroutine(coro):
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(coro)
                finally:
                    loop.close()

    def fire_recover(self) -> None:
        import asyncio

        for cb in list(self._recover_cbs):
            coro = cb()
            if asyncio.iscoroutine(coro):
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(coro)
                finally:
                    loop.close()


# ---------- 1. 空 aggregator / 單 source 基本語義 ----------


class TestBasicSemantics:
    def test_empty_aggregator_inactive(self):
        agg = AlarmAggregator()
        assert agg.active is False
        assert agg.active_sources == set()

    def test_single_source_active_inactive_cycle(self):
        agg = AlarmAggregator()
        agg.mark_source("a", True)
        assert agg.active is True
        assert agg.active_sources == {"a"}

        agg.mark_source("a", False)
        assert agg.active is False
        assert agg.active_sources == set()

    def test_active_sources_returns_copy(self):
        """外部修改回傳的 set 不應影響內部狀態。"""
        agg = AlarmAggregator()
        agg.mark_source("a", True)
        snapshot = agg.active_sources
        snapshot.add("b")  # 不影響內部
        assert agg.active_sources == {"a"}


# ---------- 2. on_change 去重 ----------


class TestOnChangeDedup:
    def test_duplicate_true_not_triggered_twice(self):
        """重複設同一 source True 僅觸發一次 on_change(True)。"""
        agg = AlarmAggregator()
        events: list[bool] = []
        agg.on_change(events.append)
        agg.mark_source("a", True)
        agg.mark_source("a", True)  # 重複 True
        assert events == [True]

    def test_duplicate_false_not_triggered(self):
        """source 從未 active 就設 False → 不觸發（聚合旗標無變化）。"""
        agg = AlarmAggregator()
        events: list[bool] = []
        agg.on_change(events.append)
        agg.mark_source("a", False)
        agg.mark_source("a", False)
        assert events == []

    def test_aggregate_transition_false_to_true_to_false(self):
        agg = AlarmAggregator()
        events: list[bool] = []
        agg.on_change(events.append)
        agg.mark_source("a", True)
        agg.mark_source("a", False)
        assert events == [True, False]


# ---------- 3. 多 source OR 語義 ----------


class TestOrSemantics:
    def test_two_sources_both_active_one_cleared_stays_active(self):
        agg = AlarmAggregator()
        events: list[bool] = []
        agg.on_change(events.append)

        agg.mark_source("a", True)  # False → True
        agg.mark_source("b", True)  # 仍 True，聚合旗標不變 → 不通知
        assert events == [True]

        agg.mark_source("a", False)  # b 還在 → 仍 True
        assert agg.active is True
        assert events == [True]

        agg.mark_source("b", False)  # 全部 cleared → False
        assert events == [True, False]
        assert agg.active is False


# ---------- 4. Observer 管理 ----------


class TestObserverLifecycle:
    def test_observer_exception_does_not_affect_others(self):
        agg = AlarmAggregator()
        received: list[bool] = []

        def bad_observer(_active: bool) -> None:
            raise RuntimeError("boom")

        agg.on_change(bad_observer)
        agg.on_change(received.append)

        agg.mark_source("a", True)
        assert received == [True]

    def test_remove_observer_stops_notifications(self):
        agg = AlarmAggregator()
        events: list[bool] = []
        agg.on_change(events.append)
        agg.mark_source("a", True)
        assert events == [True]

        agg.remove_observer(events.append)
        # 注意：events.append 每次呼叫是新 bound method，
        # 故上面 remove 其實無效 — 改用具名 callback 驗證
        records: list[bool] = []

        def cb(v: bool) -> None:
            records.append(v)

        agg.on_change(cb)
        agg.mark_source("a", False)  # True → False
        assert records == [False]

        agg.remove_observer(cb)
        agg.mark_source("a", True)  # False → True
        assert records == [False]  # cb 已移除

    def test_remove_observer_not_registered_silent(self):
        """移除不存在的 observer 不應拋例外。"""
        agg = AlarmAggregator()

        def cb(_v: bool) -> None:
            pass

        agg.remove_observer(cb)  # 靜默


# ---------- 5. unbind ----------


class TestUnbind:
    def test_unbind_active_source_triggers_on_change_false(self):
        agg = AlarmAggregator()
        events: list[bool] = []
        agg.on_change(events.append)

        dev = _MockDevice("dev_a")
        agg.bind_device(dev)
        dev.trigger("alarm_triggered")  # source active
        assert events == [True]

        agg.unbind("dev_a")
        assert events == [True, False]
        assert agg.active is False

    def test_unbind_inactive_source_no_event(self):
        agg = AlarmAggregator()
        events: list[bool] = []
        agg.on_change(events.append)

        dev = _MockDevice("dev_a")
        agg.bind_device(dev)
        # source 從未 active
        agg.unbind("dev_a")
        assert events == []

    def test_unbind_one_of_two_active_stays_active(self):
        agg = AlarmAggregator()
        events: list[bool] = []
        agg.on_change(events.append)
        agg.mark_source("a", True)
        agg.mark_source("b", True)

        # a 以 mark_source 註冊，但沒有 unbinder — unbind 僅清 active
        agg.unbind("a")
        assert agg.active is True
        assert events == [True]  # 不觸發


# ---------- 6. bind_device ----------


class TestBindDevice:
    def test_bind_device_alarm_triggered_and_cleared(self):
        agg = AlarmAggregator()
        events: list[bool] = []
        agg.on_change(events.append)

        dev = _MockDevice("bess_01")
        agg.bind_device(dev)

        dev.trigger("alarm_triggered", {"code": "OV"})
        assert agg.active is True
        assert "bess_01" in agg.active_sources

        dev.trigger("alarm_cleared", {"code": "OV"})
        assert agg.active is False
        assert events == [True, False]

    def test_bind_device_without_device_id_raises(self):
        agg = AlarmAggregator()
        dev = MagicMock(spec=["on"])  # 無 device_id
        # spec=["on"] 使 getattr(device, "device_id", None) → None
        with pytest.raises(ValueError, match="bind_device"):
            agg.bind_device(dev)

    def test_bind_same_name_twice_replaces_old(self):
        """重綁同名 → 舊的應被 unbind；只有新的會反應事件。"""
        agg = AlarmAggregator()
        dev_old = _MockDevice("dev_a")
        dev_new = _MockDevice("dev_a")

        agg.bind_device(dev_old)
        agg.bind_device(dev_new)  # 同名重綁

        # 舊 device trigger 不應影響 aggregator（已 unbind）
        dev_old.trigger("alarm_triggered")
        assert agg.active is False

        dev_new.trigger("alarm_triggered")
        assert agg.active is True

    def test_bind_device_with_explicit_name(self):
        agg = AlarmAggregator()
        dev = _MockDevice("dev_x")
        agg.bind_device(dev, name="custom_name")
        dev.trigger("alarm_triggered")
        assert "custom_name" in agg.active_sources


# ---------- 7. bind_watchdog ----------


class TestBindWatchdog:
    def test_bind_watchdog_timeout_triggers_active(self):
        agg = AlarmAggregator()
        events: list[bool] = []
        agg.on_change(events.append)

        wd = _MockWatchdog()
        # 驗證符合 WatchdogProtocol 結構（runtime_checkable）
        assert isinstance(wd, WatchdogProtocol)
        agg.bind_watchdog(wd, name="gw_wd")

        wd.fire_timeout()
        assert agg.active is True
        assert "gw_wd" in agg.active_sources

        wd.fire_recover()
        assert agg.active is False
        assert events == [True, False]

    def test_bind_watchdog_empty_name_raises(self):
        agg = AlarmAggregator()
        wd = _MockWatchdog()
        with pytest.raises(ValueError, match="bind_watchdog"):
            agg.bind_watchdog(wd, name="")

    def test_unbind_watchdog_soft_cancel(self):
        """unbind watchdog 後，timeout callback 仍被呼叫但 aggregator 狀態不變。"""
        agg = AlarmAggregator()
        wd = _MockWatchdog()
        agg.bind_watchdog(wd, name="gw_wd")
        agg.unbind("gw_wd")

        # fire_timeout 後不應讓 aggregator active
        wd.fire_timeout()
        assert agg.active is False


# ---------- 8. Thread safety ----------


class TestThreadSafety:
    def test_concurrent_mark_source_final_state_consistent(self):
        """多 thread 同時 mark_source，最終狀態可預測。"""
        agg = AlarmAggregator()
        # 每個 source 最後都 set 成 True
        N_SOURCES = 20
        N_THREADS = 10

        def worker(idx: int) -> None:
            for i in range(N_SOURCES):
                # 最後一次操作固定為 True，確保可預測
                agg.mark_source(f"s_{i}", idx % 2 == 0)
                agg.mark_source(f"s_{i}", True)

        with ThreadPoolExecutor(max_workers=N_THREADS) as pool:
            list(pool.map(worker, range(N_THREADS)))

        # 最後所有 source 應為 active
        assert agg.active is True
        assert agg.active_sources == {f"s_{i}" for i in range(N_SOURCES)}

    def test_concurrent_on_change_observer_not_crash(self):
        """多 thread 訂閱 + 觸發，不應崩潰。"""
        agg = AlarmAggregator()
        counter = {"n": 0}
        lock = threading.Lock()

        def cb(_v: bool) -> None:
            with lock:
                counter["n"] += 1

        agg.on_change(cb)

        def worker(idx: int) -> None:
            agg.mark_source(f"s_{idx}", True)
            agg.mark_source(f"s_{idx}", False)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, range(30)))

        # 聚合旗標變化次數 >= 2（首次 True + 最後 False），具體次數取決於時序
        assert counter["n"] >= 2
        assert agg.active is False
