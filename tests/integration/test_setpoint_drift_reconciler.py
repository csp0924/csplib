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
