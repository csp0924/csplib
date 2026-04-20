# =============== Reconciler Protocol Tests ===============
#
# 驗證 Operator Pattern 基礎 Protocol（K8s 風）：
#   - ReconcilerStatus frozen dataclass 合約
#   - Reconciler Protocol @runtime_checkable 行為
#   - 既有實作（CommandRefreshService / HeartbeatService /
#     SetpointDriftReconciler）isinstance check
#
# 注意：Reconciler Protocol 對 @runtime_checkable 只看屬性「存在性」，
# 不檢查簽名或返回型別。以下 DummyReconciler 必須同時有 name 與 status
# 屬性以及 reconcile_once 方法，才會被 isinstance 認可。

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.integration.command_refresh import CommandRefreshService
from csp_lib.integration.command_router import CommandRouter
from csp_lib.integration.heartbeat import HeartbeatService
from csp_lib.integration.reconciler import Reconciler, ReconcilerStatus
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.setpoint_drift_reconciler import DriftTolerance, SetpointDriftReconciler

# ─────────────── ReconcilerStatus frozen / empty ───────────────


class TestReconcilerStatusFrozen:
    """ReconcilerStatus 必須為 frozen dataclass，禁止 mutate。"""

    def test_frozen_forbids_mutation(self):
        """對 frozen dataclass 的欄位賦值應 raise FrozenInstanceError。"""
        status = ReconcilerStatus(name="demo")
        with pytest.raises(FrozenInstanceError):
            status.name = "changed"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            status.run_count = 99  # type: ignore[misc]

    def test_empty_initial_values(self):
        """ReconcilerStatus.empty(name) 給出合理的初始狀態。"""
        status = ReconcilerStatus.empty("svc-a")
        assert status.name == "svc-a"
        assert status.last_run_at is None
        assert status.last_error is None
        assert status.run_count == 0
        assert status.healthy is True
        assert dict(status.detail) == {}

    def test_detail_default_is_readonly_mapping(self):
        """detail 預設為唯讀（MappingProxyType），不允許新增 key。"""
        status = ReconcilerStatus.empty("svc-a")
        # MappingProxyType 不支援 __setitem__
        with pytest.raises(TypeError):
            status.detail["extra"] = 1  # type: ignore[index]


# ─────────────── Reconciler Protocol @runtime_checkable ───────────────


class DummyReconciler:
    """最小 Reconciler Protocol 實作（用於 isinstance 驗證）。"""

    def __init__(self, name: str = "dummy") -> None:
        self._name = name
        self._status = ReconcilerStatus.empty(name)

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> ReconcilerStatus:
        return self._status

    async def reconcile_once(self) -> ReconcilerStatus:
        return self._status


class PartialReconciler:
    """缺少 reconcile_once 方法的偽實作，不應通過 isinstance。"""

    @property
    def name(self) -> str:
        return "partial"

    @property
    def status(self) -> ReconcilerStatus:
        return ReconcilerStatus.empty("partial")


class TestReconcilerProtocol:
    """Reconciler Protocol 是 @runtime_checkable，可用 isinstance。"""

    def test_dummy_reconciler_is_instance(self):
        """自製 DummyReconciler 具備 name/status/reconcile_once → isinstance True。"""
        assert isinstance(DummyReconciler(), Reconciler)

    def test_partial_implementation_is_not_instance(self):
        """缺少 reconcile_once 的類別 → isinstance False。"""
        assert not isinstance(PartialReconciler(), Reconciler)

    def test_plain_object_is_not_instance(self):
        """無關物件 isinstance 回 False。"""
        assert not isinstance(object(), Reconciler)
        assert not isinstance("some-string", Reconciler)


# ─────────────── 既有實作 isinstance check ───────────────


class TestBuiltinImplementationsMatchProtocol:
    """CommandRefreshService / HeartbeatService / SetpointDriftReconciler
    均應通過 isinstance(service, Reconciler) check。
    """

    def test_command_refresh_service_isinstance(self):
        reg = DeviceRegistry()
        router = CommandRouter(reg, mappings=[])
        svc = CommandRefreshService(router, interval=1.0)
        assert isinstance(svc, Reconciler)

    def test_heartbeat_service_isinstance(self):
        reg = DeviceRegistry()
        svc = HeartbeatService(reg, mappings=[], interval=1.0)
        assert isinstance(svc, Reconciler)

    def test_setpoint_drift_reconciler_isinstance(self):
        reg = DeviceRegistry()
        router = CommandRouter(reg, mappings=[])
        svc = SetpointDriftReconciler(
            router=router,
            registry=reg,
            tolerance=DriftTolerance(absolute=0.0, relative=0.01),
        )
        assert isinstance(svc, Reconciler)
