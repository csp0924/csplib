# =============== SetpointDriftReconciler Tests ===============
#
# 驗證 SetpointDriftReconciler：
#   - DriftTolerance absolute/relative 負值 → ConfigurationError
#   - per_device_tolerance 負值 → ConfigurationError
#   - _is_drift: numeric（int/float）用 absolute / relative 判斷
#   - _is_drift: bool 不被誤判為 int（True != False，但 True == 1 不視為相等 drift
#     的 numeric 比對） — bool 先 short-circuit 用 !=
#   - _is_drift: 非 numeric → 直接 !=
#   - reconcile_once：無 drift / 有 drift / device unresponsive / latest_values 缺
#     / router 拋例外（不對外 raise）
#   - per-device-tolerance override 生效
#   - reconcile_once 不得 raise（契約）

from __future__ import annotations

from typing import Any

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.integration.setpoint_drift_reconciler import (
    DriftTolerance,
    SetpointDriftReconciler,
)

# ─────────────── Test Doubles ───────────────


class FakeDevice:
    """最小 drift test 用 device。"""

    def __init__(
        self,
        device_id: str,
        *,
        is_responsive: bool = True,
        latest_values: dict[str, Any] | None = None,
    ) -> None:
        self.device_id = device_id
        self.is_responsive = is_responsive
        self.latest_values: dict[str, Any] = latest_values or {}


class FakeRegistry:
    """支援 get_device 的 registry mock。"""

    def __init__(self) -> None:
        self._devices: dict[str, FakeDevice] = {}

    def add(self, dev: FakeDevice) -> None:
        self._devices[dev.device_id] = dev

    def get_device(self, device_id: str) -> FakeDevice | None:
        return self._devices.get(device_id)


class FakeRouter:
    """模擬 CommandRouter 的 desired-state 查詢 + try_write_single。"""

    def __init__(
        self,
        last_written: dict[str, dict[str, Any]] | None = None,
        *,
        write_raises: bool = False,
        write_returns: bool = True,
    ) -> None:
        self._last_written = last_written or {}
        self.write_calls: list[tuple[str, str, Any]] = []
        self._write_raises = write_raises
        self._write_returns = write_returns

    def get_tracked_device_ids(self) -> frozenset[str]:
        return frozenset(self._last_written.keys())

    def get_last_written(self, device_id: str) -> dict[str, Any]:
        return dict(self._last_written.get(device_id, {}))

    async def try_write_single(self, device_id: str, point_name: str, value: Any) -> bool:
        if self._write_raises:
            raise RuntimeError("simulated write failure")
        self.write_calls.append((device_id, point_name, value))
        return self._write_returns


# ─────────────── DriftTolerance 負值驗證 ───────────────


class TestDriftToleranceNegativeValues:
    def test_negative_absolute_raises(self):
        reg = FakeRegistry()
        router = FakeRouter()
        with pytest.raises(ConfigurationError):
            SetpointDriftReconciler(
                router=router,  # type: ignore[arg-type]
                registry=reg,  # type: ignore[arg-type]
                tolerance=DriftTolerance(absolute=-0.1, relative=0.0),
            )

    def test_negative_relative_raises(self):
        reg = FakeRegistry()
        router = FakeRouter()
        with pytest.raises(ConfigurationError):
            SetpointDriftReconciler(
                router=router,  # type: ignore[arg-type]
                registry=reg,  # type: ignore[arg-type]
                tolerance=DriftTolerance(absolute=0.0, relative=-0.01),
            )

    def test_zero_tolerance_ok(self):
        """absolute=0, relative=0 是合法（純 == 比對）。"""
        reg = FakeRegistry()
        router = FakeRouter()
        # 不應 raise
        SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.0, relative=0.0),
        )

    def test_per_device_negative_absolute_raises(self):
        reg = FakeRegistry()
        router = FakeRouter()
        with pytest.raises(ConfigurationError, match="per_device_tolerance"):
            SetpointDriftReconciler(
                router=router,  # type: ignore[arg-type]
                registry=reg,  # type: ignore[arg-type]
                per_device_tolerance={"dev1": DriftTolerance(absolute=-1.0)},
            )

    def test_per_device_negative_relative_raises(self):
        reg = FakeRegistry()
        router = FakeRouter()
        with pytest.raises(ConfigurationError, match="per_device_tolerance"):
            SetpointDriftReconciler(
                router=router,  # type: ignore[arg-type]
                registry=reg,  # type: ignore[arg-type]
                per_device_tolerance={"dev1": DriftTolerance(relative=-0.1)},
            )


# ─────────────── _is_drift 邏輯 ───────────────


class TestIsDriftNumeric:
    """int / float 的 absolute / relative 邊界判斷。"""

    def test_numeric_within_absolute_not_drift(self):
        tol = DriftTolerance(absolute=0.5, relative=0.0)
        assert SetpointDriftReconciler._is_drift(100.0, 100.3, tol) is False
        # 邊界值 diff == absolute 視為未漂移（<=）
        assert SetpointDriftReconciler._is_drift(100.0, 100.5, tol) is False

    def test_numeric_beyond_absolute_is_drift(self):
        tol = DriftTolerance(absolute=0.5, relative=0.0)
        assert SetpointDriftReconciler._is_drift(100.0, 100.6, tol) is True

    def test_numeric_within_relative_not_drift(self):
        tol = DriftTolerance(absolute=0.0, relative=0.01)
        # 0.5% 偏差 < 1% 相對容忍 → 未漂移
        assert SetpointDriftReconciler._is_drift(100.0, 100.5, tol) is False
        # 1% 整數恰好 = relative
        assert SetpointDriftReconciler._is_drift(100.0, 101.0, tol) is False

    def test_numeric_beyond_relative_is_drift(self):
        tol = DriftTolerance(absolute=0.0, relative=0.01)
        # 1.5% 偏差 > 1%
        assert SetpointDriftReconciler._is_drift(100.0, 101.5, tol) is True

    def test_numeric_zero_desired_relative_skipped(self):
        """desired=0 時 relative 判斷會 divide-by-zero；實作應 skip relative。"""
        tol = DriftTolerance(absolute=0.0, relative=0.5)
        # desired=0, actual=0.1，absolute=0 → beyond absolute
        # relative 段因 abs(desired)==0 被 skip → 應視為 drift
        assert SetpointDriftReconciler._is_drift(0.0, 0.1, tol) is True
        # 完全相等 → 未漂移
        assert SetpointDriftReconciler._is_drift(0.0, 0.0, tol) is False

    def test_or_semantics_absolute_or_relative_passes(self):
        """absolute 與 relative 是 OR：任一滿足即視為未漂移。"""
        tol = DriftTolerance(absolute=0.5, relative=0.01)
        # diff=2，超過 absolute=0.5
        # 但 2/1000 = 0.002 < relative 0.01 → relative 滿足 → 未漂移
        assert SetpointDriftReconciler._is_drift(1000.0, 1002.0, tol) is False

    def test_int_and_float_cross_type(self):
        tol = DriftTolerance(absolute=0.0, relative=0.0)
        assert SetpointDriftReconciler._is_drift(100, 100.0, tol) is False
        assert SetpointDriftReconciler._is_drift(100, 101, tol) is True


class TestIsDriftBool:
    """bool 是 int 子類，但 drift 判斷應 short-circuit 用 !=，避免 True==1 被視為相等。"""

    def test_true_vs_false_is_drift(self):
        tol = DriftTolerance(absolute=10.0, relative=10.0)
        # 即便 absolute 很大，bool 也該用 != 比較
        assert SetpointDriftReconciler._is_drift(True, False, tol) is True
        assert SetpointDriftReconciler._is_drift(False, True, tol) is True

    def test_same_bool_not_drift(self):
        tol = DriftTolerance(absolute=0.0, relative=0.0)
        assert SetpointDriftReconciler._is_drift(True, True, tol) is False
        assert SetpointDriftReconciler._is_drift(False, False, tol) is False

    def test_bool_vs_int_uses_not_equal(self):
        """True 與 1 在 Python 中相等，但實作該 short-circuit 用 !=。
        True != 1 是 False（Python 語義），因此回傳 False（未漂移）。
        關鍵點：此 branch 不進 numeric 計算，不會因 absolute=0 而誤判。"""
        tol = DriftTolerance(absolute=0.0, relative=0.0)
        # bool != int 的 != 走 Python 相等規則
        # True == 1 → True，so `True != 1` is False → 未 drift
        assert SetpointDriftReconciler._is_drift(True, 1, tol) is False
        # True != 2 → True → 視為 drift
        assert SetpointDriftReconciler._is_drift(True, 2, tol) is True


class TestIsDriftNonNumeric:
    """非 numeric 型別（str 等）直接用 !=。"""

    def test_str_equal_not_drift(self):
        tol = DriftTolerance(absolute=0.0, relative=0.0)
        assert SetpointDriftReconciler._is_drift("on", "on", tol) is False

    def test_str_different_is_drift(self):
        tol = DriftTolerance(absolute=1.0, relative=1.0)
        # 無視 tolerance（非 numeric）
        assert SetpointDriftReconciler._is_drift("on", "off", tol) is True


# ─────────────── reconcile_once 行為 ───────────────


class TestReconcileOnceNoDrift:
    async def test_no_tracked_devices(self):
        """router 無追蹤設備 → drift_count=0, devices_fixed=(), healthy=True。"""
        reg = FakeRegistry()
        router = FakeRouter(last_written={})
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(),
        )
        status = await svc.reconcile_once()
        assert status.detail["drift_count"] == 0
        assert status.detail["devices_fixed"] == ()
        assert status.healthy is True
        assert status.run_count == 1
        assert status.last_error is None

    async def test_actual_equals_desired_no_drift(self):
        """actual == desired → 未漂移，不寫。"""
        dev = FakeDevice("pcs1", latest_values={"p_set": 100.0})
        reg = FakeRegistry()
        reg.add(dev)
        router = FakeRouter(last_written={"pcs1": {"p_set": 100.0}})
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.0, relative=0.0),
        )
        status = await svc.reconcile_once()
        assert status.detail["drift_count"] == 0
        assert router.write_calls == []


class TestReconcileOnceWithDrift:
    async def test_drift_triggers_rewrite(self):
        """actual 偏離 desired 超過 tolerance → 呼叫 router.try_write_single。"""
        dev = FakeDevice("pcs1", latest_values={"p_set": 95.0})
        reg = FakeRegistry()
        reg.add(dev)
        router = FakeRouter(last_written={"pcs1": {"p_set": 100.0}})
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5, relative=0.0),
        )
        status = await svc.reconcile_once()
        assert status.detail["drift_count"] == 1
        assert status.detail["devices_fixed"] == ("pcs1.p_set",)
        assert router.write_calls == [("pcs1", "p_set", 100.0)]
        assert status.healthy is True

    async def test_multiple_drifts_all_rewritten(self):
        """多個 device / 多個 point 均有漂移 → 逐個寫入。"""
        dev1 = FakeDevice("pcs1", latest_values={"p_set": 80.0, "q_set": 40.0})
        dev2 = FakeDevice("pcs2", latest_values={"p_set": 60.0})
        reg = FakeRegistry()
        reg.add(dev1)
        reg.add(dev2)
        router = FakeRouter(
            last_written={
                "pcs1": {"p_set": 100.0, "q_set": 50.0},
                "pcs2": {"p_set": 50.0},
            },
        )
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.1, relative=0.0),
        )
        status = await svc.reconcile_once()
        assert status.detail["drift_count"] == 3
        assert len(router.write_calls) == 3
        fixed = set(status.detail["devices_fixed"])
        assert fixed == {"pcs1.p_set", "pcs1.q_set", "pcs2.p_set"}


class TestReconcileOnceSkipBehavior:
    async def test_unresponsive_device_skipped(self):
        dev = FakeDevice("pcs1", is_responsive=False, latest_values={"p_set": 95.0})
        reg = FakeRegistry()
        reg.add(dev)
        router = FakeRouter(last_written={"pcs1": {"p_set": 100.0}})
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5),
        )
        status = await svc.reconcile_once()
        assert status.detail["drift_count"] == 0
        assert router.write_calls == []

    async def test_device_not_in_registry_skipped(self):
        """router 追蹤的 device_id 在 registry 找不到 → skip。"""
        reg = FakeRegistry()  # 完全沒 device
        router = FakeRouter(last_written={"ghost": {"p_set": 100.0}})
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5),
        )
        status = await svc.reconcile_once()
        assert status.detail["drift_count"] == 0
        assert router.write_calls == []
        # 契約：不 raise
        assert status.last_error is None

    async def test_latest_values_missing_point_skipped(self):
        """desired 紀錄了 point_name，但 device.latest_values 還沒讀到該點 → skip。"""
        dev = FakeDevice("pcs1", latest_values={})  # 沒有 p_set
        reg = FakeRegistry()
        reg.add(dev)
        router = FakeRouter(last_written={"pcs1": {"p_set": 100.0}})
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.0),
        )
        status = await svc.reconcile_once()
        assert status.detail["drift_count"] == 0
        assert router.write_calls == []

    async def test_empty_last_written_snapshot_skipped(self):
        """desired snapshot 為空 → 不進 inner loop。"""
        dev = FakeDevice("pcs1", latest_values={"p_set": 50})
        reg = FakeRegistry()
        reg.add(dev)
        # last_written 有此 device 但 mapping 為空（例如 tracked_device_ids 有但值空）
        router = FakeRouter(last_written={"pcs1": {}})
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(),
        )
        status = await svc.reconcile_once()
        assert status.detail["drift_count"] == 0


# ─────────────── reconcile_once 不得 raise 契約 ───────────────


class TestReconcileOnceExceptionContract:
    """reconcile_once 遇例外必須：
    - 不對外 raise
    - status.last_error 有值
    - status.healthy=False
    """

    async def test_write_exception_captured_in_status(self):
        dev = FakeDevice("pcs1", latest_values={"p_set": 80.0})
        reg = FakeRegistry()
        reg.add(dev)
        router = FakeRouter(
            last_written={"pcs1": {"p_set": 100.0}},
            write_raises=True,
        )
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.1),
        )
        # 關鍵：不該 raise
        status = await svc.reconcile_once()
        assert status.last_error is not None
        assert "simulated" in status.last_error.lower() or "runtimeerror" in status.last_error.lower()
        assert status.healthy is False

    async def test_get_tracked_raises_captured(self):
        """router.get_tracked_device_ids 拋例外 → status.last_error 有值。"""

        class BadRouter(FakeRouter):
            def get_tracked_device_ids(self) -> frozenset[str]:
                raise RuntimeError("get_tracked boom")

        reg = FakeRegistry()
        router = BadRouter()
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(),
        )
        status = await svc.reconcile_once()
        assert status.last_error is not None
        assert status.healthy is False

    async def test_run_count_increments_even_on_error(self):
        """run_count 不因例外而不增加（確保計數可靠）。"""

        class BadRouter(FakeRouter):
            def get_tracked_device_ids(self) -> frozenset[str]:
                raise RuntimeError("fail")

        reg = FakeRegistry()
        router = BadRouter()
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
        )
        s1 = await svc.reconcile_once()
        s2 = await svc.reconcile_once()
        assert s1.run_count == 1
        assert s2.run_count == 2


# ─────────────── per-device tolerance override ───────────────


class TestPerDeviceToleranceOverride:
    async def test_per_device_override_applied(self):
        """per_device_tolerance[dev_id] 比預設 tolerance 寬鬆 → 該設備不 drift。"""
        dev = FakeDevice("pcs1", latest_values={"p_set": 90.0})
        reg = FakeRegistry()
        reg.add(dev)
        router = FakeRouter(last_written={"pcs1": {"p_set": 100.0}})

        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5),  # 預設嚴格
            per_device_tolerance={"pcs1": DriftTolerance(absolute=50.0)},  # pcs1 寬鬆
        )
        status = await svc.reconcile_once()
        # pcs1 用寬鬆 tolerance，|100-90|=10 <= 50，未漂移
        assert status.detail["drift_count"] == 0

    async def test_per_device_override_stricter(self):
        """per_device_tolerance 比預設嚴格 → 該設備 drift 被偵測。"""
        dev = FakeDevice("pcs1", latest_values={"p_set": 99.0})
        reg = FakeRegistry()
        reg.add(dev)
        router = FakeRouter(last_written={"pcs1": {"p_set": 100.0}})

        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=10.0),  # 預設寬鬆
            per_device_tolerance={"pcs1": DriftTolerance(absolute=0.1)},  # 嚴格
        )
        status = await svc.reconcile_once()
        assert status.detail["drift_count"] == 1
        assert router.write_calls == [("pcs1", "p_set", 100.0)]

    async def test_devices_not_in_per_device_use_default(self):
        """不在 per_device_tolerance map 的設備仍用預設 tolerance。"""
        dev1 = FakeDevice("pcs1", latest_values={"p_set": 99.0})
        dev2 = FakeDevice("pcs2", latest_values={"p_set": 99.0})
        reg = FakeRegistry()
        reg.add(dev1)
        reg.add(dev2)
        router = FakeRouter(
            last_written={
                "pcs1": {"p_set": 100.0},
                "pcs2": {"p_set": 100.0},
            }
        )
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.1),  # 嚴格
            per_device_tolerance={"pcs2": DriftTolerance(absolute=5.0)},  # pcs2 寬鬆
        )
        status = await svc.reconcile_once()
        # pcs1 走預設 嚴格 → drift；pcs2 走寬鬆 → 未 drift
        assert status.detail["drift_count"] == 1
        assert router.write_calls == [("pcs1", "p_set", 100.0)]


# ─────────────── LeaderGate 守門 ───────────────


class _FakeLeaderGate:
    """最小 LeaderGate 測試替身。"""

    def __init__(self, is_leader: bool) -> None:
        self._is_leader = is_leader

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    def set_leader(self, value: bool) -> None:
        self._is_leader = value

    async def wait_until_leader(self) -> None:
        return None


class TestLeaderGate:
    """注入 leader_gate 時，follower 節點不得對設備發出寫入。

    背景：sandbox/manager_reconciler_race_leader_bypass_demo.py 量化 — HA dual-node
    場景下 CommandRouter.try_write_single 無 leader_gate 守門，follower 節點的
    reconciler 仍會發出寫入，破壞 single-writer invariant。修法：在 reconciler 入口
    早退（不動 CommandRouter，保留 strategy path 的 follower-callable 性質）。
    """

    async def test_follower_does_not_write(self):
        """leader_gate.is_leader=False → reconcile_once 早退，router.try_write_single 零呼叫。"""
        dev = FakeDevice("pcs1", latest_values={"p_set": 95.0})
        reg = FakeRegistry()
        reg.add(dev)
        router = FakeRouter(last_written={"pcs1": {"p_set": 100.0}})
        gate = _FakeLeaderGate(is_leader=False)
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5, relative=0.0),
            leader_gate=gate,  # type: ignore[arg-type]
        )
        status = await svc.reconcile_once()
        # 關鍵斷言：follower 不寫
        assert router.write_calls == []
        assert status.detail.get("paused") == "not_leader"
        # 不視為 unhealthy（被 gate 擋是正常運作）
        assert status.last_error is None
        assert status.healthy is True

    async def test_leader_writes_normally(self):
        """leader_gate.is_leader=True → 正常 drift 修正流程不受影響。"""
        dev = FakeDevice("pcs1", latest_values={"p_set": 95.0})
        reg = FakeRegistry()
        reg.add(dev)
        router = FakeRouter(last_written={"pcs1": {"p_set": 100.0}})
        gate = _FakeLeaderGate(is_leader=True)
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5, relative=0.0),
            leader_gate=gate,  # type: ignore[arg-type]
        )
        status = await svc.reconcile_once()
        assert router.write_calls == [("pcs1", "p_set", 100.0)]
        assert status.detail["drift_count"] == 1
        assert "paused" not in status.detail

    async def test_no_leader_gate_backward_compatible(self):
        """未注入 leader_gate（None）→ 維持單節點原有行為（向後相容）。"""
        dev = FakeDevice("pcs1", latest_values={"p_set": 95.0})
        reg = FakeRegistry()
        reg.add(dev)
        router = FakeRouter(last_written={"pcs1": {"p_set": 100.0}})
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5, relative=0.0),
        )
        status = await svc.reconcile_once()
        # 沒注入 gate → 走原行為（會寫）
        assert router.write_calls == [("pcs1", "p_set", 100.0)]
        assert "paused" not in status.detail

    async def test_promote_to_leader_resumes_writes(self):
        """中途升格為 leader → 下一輪 reconcile 開始寫入。"""
        dev = FakeDevice("pcs1", latest_values={"p_set": 95.0})
        reg = FakeRegistry()
        reg.add(dev)
        router = FakeRouter(last_written={"pcs1": {"p_set": 100.0}})
        gate = _FakeLeaderGate(is_leader=False)
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5, relative=0.0),
            leader_gate=gate,  # type: ignore[arg-type]
        )
        # 第一輪：follower → 不寫
        await svc.reconcile_once()
        assert router.write_calls == []
        # 升格
        gate.set_leader(True)
        # 第二輪：leader → 寫
        status = await svc.reconcile_once()
        assert router.write_calls == [("pcs1", "p_set", 100.0)]
        assert status.detail["drift_count"] == 1


# ─────────────── name / status initial ───────────────


class TestNameAndInitialStatus:
    def test_default_name(self):
        reg = FakeRegistry()
        router = FakeRouter()
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
        )
        assert svc.name == "setpoint_drift"

    def test_custom_name(self):
        reg = FakeRegistry()
        router = FakeRouter()
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            name="custom-drift",
        )
        assert svc.name == "custom-drift"

    def test_initial_status(self):
        reg = FakeRegistry()
        router = FakeRouter()
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            name="n",
        )
        status = svc.status
        assert status.name == "n"
        assert status.run_count == 0
        assert status.last_run_at is None
        assert status.healthy is True


# ─────────────── min_rewrite_interval_seconds（per-(device,point) cooldown）───────────────


class TestMinRewriteInterval:
    """v0.10.x+：min_rewrite_interval_seconds 加 per-(device, point) time-based cooldown
    防 audit log spam（同一個持續 drift 在 ReadScheduler 把新 actual 讀回前不重複 log/write）。

    背景：sandbox/drift_reconciler_read_lag_storm_demo.py 量化 — read interval >> reconcile
    interval 場景下，原版會對同一個 drift event 重複 try_write + log ~ T_read/T_reconcile 次，
    破壞 reconciler 的 audit-trail 設計意圖。
    """

    def test_negative_interval_raises(self):
        reg = FakeRegistry()
        router = FakeRouter()
        with pytest.raises(ConfigurationError):
            SetpointDriftReconciler(
                router=router,  # type: ignore[arg-type]
                registry=reg,  # type: ignore[arg-type]
                min_rewrite_interval_seconds=-1.0,
            )

    async def test_zero_keeps_legacy_behaviour(self):
        """min_rewrite_interval_seconds=0（預設）→ 每次 drift 都寫 + log（向後相容）。"""
        reg = FakeRegistry()
        reg.add(FakeDevice("D1", latest_values={"sp": 80.0}))
        router = FakeRouter(last_written={"D1": {"sp": 100.0}})
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5),
        )
        for _ in range(5):
            await svc.reconcile_once()
        assert len(router.write_calls) == 5
        # cooldown disabled → detail 不該出現 skipped_by_cooldown key（避免外部誤讀「有 cooldown 在運作」）
        assert "skipped_by_cooldown" not in svc.status.detail

    async def test_positive_interval_blocks_rewrite_within_window(self):
        """設了 min_rewrite_interval_seconds 後，持續 drift 在 cooldown 視窗內只寫一次。"""
        reg = FakeRegistry()
        reg.add(FakeDevice("D1", latest_values={"sp": 80.0}))
        router = FakeRouter(last_written={"D1": {"sp": 100.0}})
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5),
            min_rewrite_interval_seconds=10.0,  # 遠大於 test duration
        )
        for _ in range(5):
            await svc.reconcile_once()
        assert len(router.write_calls) == 1, "持續 drift 在 cooldown 內應該只寫一次"
        # detail 是「本次 reconcile」的 per-run 計數（非累積）：最後一次 reconcile
        # 仍偵測到 drift 但被 cooldown 擋下 → drift_count=1, skipped_by_cooldown=1
        assert svc.status.detail["drift_count"] == 1
        assert svc.status.detail["skipped_by_cooldown"] == 1

    async def test_write_failure_does_not_start_cooldown(self):
        """write 失敗（router 回 False）不該啟動 cooldown，下次 reconcile 該重試。

        關鍵 invariant：cooldown 是「成功 log audit event」的去抖，不是「最近一次嘗試」的去抖。
        若 write 失敗也起 cooldown → transient modbus error 期間 reconciler 卡死，actual 永不修。
        """
        reg = FakeRegistry()
        reg.add(FakeDevice("D1", latest_values={"sp": 80.0}))
        # 預設 write_returns=False → router 永遠回 False（模擬持續 fail）
        router = FakeRouter(last_written={"D1": {"sp": 100.0}}, write_returns=False)
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5),
            min_rewrite_interval_seconds=10.0,
        )
        for _ in range(5):
            await svc.reconcile_once()
        # write 都失敗 → cooldown 從未啟動 → 5 次 reconcile 都該嘗試
        assert len(router.write_calls) == 5, "write fail 不該啟動 cooldown，每次都該 retry"

    async def test_per_point_cooldown_independent(self):
        """同 device 不同 point 各自獨立 cooldown，不互相影響。"""
        reg = FakeRegistry()
        reg.add(FakeDevice("D1", latest_values={"sp": 80.0, "limit": 50.0}))
        router = FakeRouter(last_written={"D1": {"sp": 100.0, "limit": 90.0}})
        svc = SetpointDriftReconciler(
            router=router,  # type: ignore[arg-type]
            registry=reg,  # type: ignore[arg-type]
            tolerance=DriftTolerance(absolute=0.5),
            min_rewrite_interval_seconds=10.0,
        )
        await svc.reconcile_once()
        # 第一次：兩個 point 都 drift → 各寫一次
        assert len(router.write_calls) == 2
        await svc.reconcile_once()
        # 第二次：兩個 point 都在自己的 cooldown 內 → 不再寫
        assert len(router.write_calls) == 2
