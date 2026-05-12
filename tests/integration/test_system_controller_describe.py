"""SystemController.describe() 聚合觀測 API 測試（J-P2）

涵蓋 acceptance criteria AC1~AC12：
- AC1  auto-discovery 對 StrategyExecutor 的 HealthCheckable 路徑
- AC2  顯式 attach 並走 ManagerDescribable.describe() 路徑
- AC3  detach 行為（idempotent + 回傳 bool）
- AC4  重複 attach 同名 raise ValueError
- AC5  attach name 型別檢查（空字串、None、非 str → TypeError）
- AC6  既非 ManagerDescribable 亦非 HealthCheckable 的物件 → kind="unknown"
- AC7  subsystem describe()/health() 拋例外時 kind="error"，整體不 raise
- AC8  同時實作兩個 protocol 時 describe() 優先勝過 health()
- AC9  status.subsystems 為 MappingProxyType，賦值會 raise TypeError
- AC10 SystemControllerStatus / SubsystemSnapshot 為 frozen dataclass
- AC11 describe() 不影響 health() 行為
- AC12 alarmed_device_ids 排序穩定
"""

from dataclasses import FrozenInstanceError
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import HeartbeatMapping, SubsystemSnapshot, SystemControllerStatus
from csp_lib.integration.system_controller import (
    CommandRefreshConfig,
    HeartbeatConfig,
    SystemController,
    SystemControllerConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_device(
    device_id: str,
    *,
    responsive: bool = True,
    protected: bool = False,
    connected: bool = True,
) -> MagicMock:
    """Mirror of test_system_controller.py::_make_device for consistency."""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=connected)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    type(dev).is_healthy = PropertyMock(return_value=connected and responsive and not protected)
    type(dev).latest_values = PropertyMock(return_value={})
    type(dev).active_alarms = PropertyMock(return_value=[])
    dev.write = AsyncMock()
    dev.on = MagicMock(return_value=MagicMock())

    def _health() -> HealthReport:
        if connected and responsive and not protected:
            status = HealthStatus.HEALTHY
        elif connected:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNHEALTHY
        return HealthReport(
            status=status,
            component=f"device:{device_id}",
            details={"connected": connected, "responsive": responsive, "protected": protected},
        )

    dev.health = _health
    return dev


class _FakeDescribable:
    """符合 ManagerDescribable Protocol 的最小實作。"""

    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.describe_calls = 0

    def describe(self) -> object:
        self.describe_calls += 1
        return self._payload


class _FakeHealthy:
    """符合 HealthCheckable Protocol 的最小實作。"""

    def __init__(self, report: HealthReport) -> None:
        self._report = report
        self.health_calls = 0

    def health(self) -> HealthReport:
        self.health_calls += 1
        return self._report


class _FakeBoth:
    """同時符合兩個 Protocol — 用於驗證 describe 優先順序。"""

    def __init__(self, describe_payload: object, health_report: HealthReport) -> None:
        self._describe_payload = describe_payload
        self._health_report = health_report
        self.describe_calls = 0
        self.health_calls = 0

    def describe(self) -> object:
        self.describe_calls += 1
        return self._describe_payload

    def health(self) -> HealthReport:
        self.health_calls += 1
        return self._health_report


class _RaisingDescribable:
    """describe() 會拋例外，用於驗證 fail-soft。"""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def describe(self) -> object:
        raise self._exc


class _Plain:
    """既非 ManagerDescribable 亦非 HealthCheckable 的純物件。"""

    pass


def _make_controller(*, with_devices: list | None = None) -> SystemController:
    """建立最小 SystemController（無 mappings、無 protection）。"""
    reg = DeviceRegistry()
    for dev in with_devices or []:
        reg.register(dev)
    return SystemController(reg, SystemControllerConfig())


# ---------------------------------------------------------------------------
# AC1: auto-discovery
# ---------------------------------------------------------------------------


class TestAutoDiscovery:
    def test_executor_auto_attached_via_health_protocol(self) -> None:
        """AC1: StrategyExecutor 實作 HealthCheckable，__init__ 應自動 attach 為
        'executor'，describe() 該欄位 kind='health'，payload 為 HealthReport instance。
        """
        sc = _make_controller()
        status = sc.describe()

        assert "executor" in status.subsystems
        snapshot = status.subsystems["executor"]
        assert snapshot.kind == "health"
        assert isinstance(snapshot.payload, HealthReport)
        assert snapshot.error is None
        assert snapshot.name == "executor"

    def test_optional_subsystems_absent_when_None(self) -> None:
        """heartbeat / command_refresh 在 default config 下為 None，不應出現在 subsystems。

        注意：v0.10.x 後 orchestrator 一律建立（且實作 HealthCheckable），
        因此一定會被 auto-attach；此處只驗證 None 的兩個 optional subsystem 缺席。
        """
        sc = _make_controller()
        status = sc.describe()
        assert "heartbeat" not in status.subsystems
        assert "command_refresh" not in status.subsystems

    def test_orchestrator_auto_attached_via_health_protocol(self) -> None:
        """SystemCommandOrchestrator 實作 HealthCheckable，__init__ 應 auto-attach
        為 'orchestrator'，kind='health'，payload 是 HealthReport instance，
        component='SystemCommandOrchestrator'。"""
        sc = _make_controller()
        status = sc.describe()

        assert "orchestrator" in status.subsystems
        snapshot = status.subsystems["orchestrator"]
        assert snapshot.kind == "health"
        assert isinstance(snapshot.payload, HealthReport)
        assert snapshot.payload.component == "SystemCommandOrchestrator"
        assert snapshot.error is None

    def test_all_four_subsystems_auto_attached_when_configured(self) -> None:
        """4/4 hit case：executor + heartbeat (mappings configured) +
        command_refresh (enabled) + orchestrator 都 auto-attach 為 kind='health'。"""
        reg = DeviceRegistry()
        config = SystemControllerConfig(
            heartbeat=HeartbeatConfig(
                mappings=[HeartbeatMapping(point_name="hb", trait="pcs")],
                interval_seconds=1.0,
            ),
            command_refresh=CommandRefreshConfig(refresh_interval=1.0, enabled=True),
        )
        sc = SystemController(reg, config)
        status = sc.describe()

        # 4/4 都應該 auto-attach
        assert "executor" in status.subsystems
        assert "heartbeat" in status.subsystems
        assert "command_refresh" in status.subsystems
        assert "orchestrator" in status.subsystems

        # 全部應該是 kind='health'，無 error
        expected_components = {
            "executor": None,  # StrategyExecutor.health() component name 由實作決定
            "heartbeat": "HeartbeatService",
            "command_refresh": "CommandRefreshService",
            "orchestrator": "SystemCommandOrchestrator",
        }
        for sub_name, expected_component in expected_components.items():
            snapshot = status.subsystems[sub_name]
            assert snapshot.kind == "health", f"{sub_name}: kind={snapshot.kind}"
            assert snapshot.error is None, f"{sub_name}: error={snapshot.error}"
            assert isinstance(snapshot.payload, HealthReport)
            if expected_component is not None:
                assert snapshot.payload.component == expected_component

    def test_only_executor_and_orchestrator_when_optional_absent(self) -> None:
        """default config（無 heartbeat / 無 command_refresh）→ subsystems 應有
        executor + orchestrator，但 NOT heartbeat / command_refresh。"""
        sc = _make_controller()
        status = sc.describe()

        assert "executor" in status.subsystems
        assert "orchestrator" in status.subsystems
        assert "heartbeat" not in status.subsystems
        assert "command_refresh" not in status.subsystems

    def test_three_of_four_with_heartbeat_only(self) -> None:
        """heartbeat 配置但 command_refresh 為 None → 3/4 (executor + heartbeat + orchestrator)。"""
        reg = DeviceRegistry()
        config = SystemControllerConfig(
            heartbeat=HeartbeatConfig(
                mappings=[HeartbeatMapping(point_name="hb", trait="pcs")],
            ),
        )
        sc = SystemController(reg, config)
        status = sc.describe()

        assert "executor" in status.subsystems
        assert "heartbeat" in status.subsystems
        assert "orchestrator" in status.subsystems
        assert "command_refresh" not in status.subsystems


# ---------------------------------------------------------------------------
# AC2: 顯式 attach + describe 路徑
# ---------------------------------------------------------------------------


class TestExplicitAttachDescribe:
    def test_attach_describable_appears_with_describe_kind(self) -> None:
        """AC2: 顯式 attach 一個 ManagerDescribable，describe() 該 subsystem
        kind='describe'，payload is 該物件 describe() 回傳值（identity 相等）。"""
        sc = _make_controller()
        payload = {"foo": "bar", "count": 42}
        fake = _FakeDescribable(payload)

        sc.attach_subsystem("mongo_uploader", fake)
        status = sc.describe()

        assert "mongo_uploader" in status.subsystems
        snapshot = status.subsystems["mongo_uploader"]
        assert snapshot.kind == "describe"
        assert snapshot.payload is payload  # identity, not eq
        assert snapshot.error is None
        assert fake.describe_calls == 1


# ---------------------------------------------------------------------------
# AC3: detach 行為
# ---------------------------------------------------------------------------


class TestDetach:
    def test_detach_existing_returns_true_and_removes(self) -> None:
        sc = _make_controller()
        fake = _FakeDescribable({"k": "v"})
        sc.attach_subsystem("uploader", fake)

        # 確認 attach 成功
        assert "uploader" in sc.describe().subsystems

        # detach 回 True
        assert sc.detach_subsystem("uploader") is True

        # describe 後不再出現
        assert "uploader" not in sc.describe().subsystems

    def test_detach_nonexistent_returns_false(self) -> None:
        sc = _make_controller()
        assert sc.detach_subsystem("nonexistent") is False

    def test_detach_is_idempotent(self) -> None:
        sc = _make_controller()
        sc.attach_subsystem("x", _FakeDescribable(None))
        assert sc.detach_subsystem("x") is True
        # 第二次回 False 而非 raise
        assert sc.detach_subsystem("x") is False


# ---------------------------------------------------------------------------
# AC4: 重複 attach 同名 raise ValueError
# ---------------------------------------------------------------------------


class TestNameConflict:
    def test_duplicate_attach_raises_value_error(self) -> None:
        """AC4: 同名重複 attach 應 raise ValueError。"""
        sc = _make_controller()
        sc.attach_subsystem("dup", _FakeDescribable(None))
        with pytest.raises(ValueError):
            sc.attach_subsystem("dup", _FakeDescribable(None))

    def test_duplicate_with_auto_discovered_name_raises(self) -> None:
        """auto-discovery 已用掉 'executor' 名，再次手動 attach 同名要 raise。"""
        sc = _make_controller()
        with pytest.raises(ValueError):
            sc.attach_subsystem("executor", _FakeDescribable(None))


# ---------------------------------------------------------------------------
# AC5: name 型別檢查
# ---------------------------------------------------------------------------


class TestNameTypeValidation:
    def test_empty_name_raises_type_error(self) -> None:
        sc = _make_controller()
        with pytest.raises(TypeError):
            sc.attach_subsystem("", _FakeDescribable(None))

    def test_none_name_raises_type_error(self) -> None:
        sc = _make_controller()
        with pytest.raises(TypeError):
            sc.attach_subsystem(None, _FakeDescribable(None))  # type: ignore[arg-type]

    def test_non_string_name_raises_type_error(self) -> None:
        sc = _make_controller()
        with pytest.raises(TypeError):
            sc.attach_subsystem(123, _FakeDescribable(None))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC6: unknown 物件
# ---------------------------------------------------------------------------


class TestUnknownComponent:
    def test_plain_object_yields_unknown_kind(self) -> None:
        """AC6: 既非 ManagerDescribable 亦非 HealthCheckable 的物件 → kind='unknown'。"""
        sc = _make_controller()
        sc.attach_subsystem("plain", _Plain())

        snapshot = sc.describe().subsystems["plain"]
        assert snapshot.kind == "unknown"
        assert snapshot.payload is None
        assert snapshot.error is None


# ---------------------------------------------------------------------------
# AC7: 例外 fail-soft
# ---------------------------------------------------------------------------


class TestFailSoft:
    def test_describe_raising_subsystem_yields_error_kind(self) -> None:
        """AC7: subsystem.describe() 拋例外 → 該 subsystem kind='error'，
        error 含例外字串；其他 subsystem 不受影響；整個 describe() 不 raise。"""
        sc = _make_controller()
        good = _FakeDescribable({"ok": True})
        bad = _RaisingDescribable(RuntimeError("boom!"))

        sc.attach_subsystem("good", good)
        sc.attach_subsystem("bad", bad)

        # 整體 describe() 不 raise
        status = sc.describe()

        # 壞的轉成 error kind
        bad_snap = status.subsystems["bad"]
        assert bad_snap.kind == "error"
        assert bad_snap.payload is None
        assert bad_snap.error is not None
        assert "boom!" in bad_snap.error

        # 好的不受影響
        good_snap = status.subsystems["good"]
        assert good_snap.kind == "describe"
        assert good_snap.payload == {"ok": True}
        assert good_snap.error is None

        # auto-discovered executor 也不受影響
        assert status.subsystems["executor"].kind == "health"

    def test_value_error_in_describe_also_caught(self) -> None:
        """非 RuntimeError 也應被攔截（例如 ValueError）。"""
        sc = _make_controller()
        sc.attach_subsystem("bad", _RaisingDescribable(ValueError("invalid state")))

        status = sc.describe()  # 不應 raise
        assert status.subsystems["bad"].kind == "error"
        assert "invalid state" in (status.subsystems["bad"].error or "")


# ---------------------------------------------------------------------------
# AC8: describe 優先勝過 health
# ---------------------------------------------------------------------------


class TestProtocolPriority:
    def test_describe_takes_precedence_over_health(self) -> None:
        """AC8: 同時實作 ManagerDescribable + HealthCheckable，
        describe() 走 describe() 而非 health()。"""
        describe_payload = {"source": "describe"}
        health_report = HealthReport(status=HealthStatus.HEALTHY, component="should_not_be_used")
        fake = _FakeBoth(describe_payload, health_report)

        sc = _make_controller()
        sc.attach_subsystem("dual", fake)

        snapshot = sc.describe().subsystems["dual"]

        assert snapshot.kind == "describe"
        assert snapshot.payload is describe_payload
        # describe() 被呼叫；health() 完全沒被呼叫
        assert fake.describe_calls == 1
        assert fake.health_calls == 0


# ---------------------------------------------------------------------------
# AC9: subsystems 為 MappingProxyType
# ---------------------------------------------------------------------------


class TestSubsystemsImmutability:
    def test_subsystems_is_mapping_proxy(self) -> None:
        sc = _make_controller()
        status = sc.describe()
        assert isinstance(status.subsystems, MappingProxyType)

    def test_subsystems_assignment_raises_type_error(self) -> None:
        """AC9: 嘗試 status.subsystems[key] = ... 應 raise TypeError。"""
        sc = _make_controller()
        status = sc.describe()
        fake_snapshot = SubsystemSnapshot(name="x", kind="unknown", payload=None)
        with pytest.raises(TypeError):
            status.subsystems["x"] = fake_snapshot  # type: ignore[index]

    def test_subsystems_deletion_raises_type_error(self) -> None:
        sc = _make_controller()
        status = sc.describe()
        # auto-discovered "executor" 一定存在
        with pytest.raises(TypeError):
            del status.subsystems["executor"]  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# AC10: frozen dataclass
# ---------------------------------------------------------------------------


class TestFrozenDataclasses:
    def test_system_controller_status_is_frozen(self) -> None:
        sc = _make_controller()
        status = sc.describe()
        with pytest.raises(FrozenInstanceError):
            status.component = "hacked"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            status.effective_mode = "x"  # type: ignore[misc]

    def test_subsystem_snapshot_is_frozen(self) -> None:
        snap = SubsystemSnapshot(name="x", kind="unknown", payload=None)
        with pytest.raises(FrozenInstanceError):
            snap.kind = "health"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            snap.payload = {"hacked": True}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AC11: describe() 不影響 health()
# ---------------------------------------------------------------------------


class TestDescribeDoesNotAffectHealth:
    def test_health_unchanged_after_describe(self) -> None:
        """AC11: 呼叫 describe() 不改變 health() 行為。"""
        dev = _make_device("D1", protected=False, responsive=True, connected=True)
        sc = _make_controller(with_devices=[dev])

        h1 = sc.health()
        _ = sc.describe()
        h2 = sc.health()

        # health 結果結構相同
        assert h1.status == h2.status
        assert h1.component == h2.component
        # 子設備數一致
        assert len(h1.children) == len(h2.children)

    def test_describe_embeds_health_report(self) -> None:
        """status.device_health 應為 SystemController.health() 的回傳結構。"""
        dev = _make_device("D1")
        sc = _make_controller(with_devices=[dev])

        status = sc.describe()
        assert isinstance(status.device_health, HealthReport)
        assert status.device_health.component == "system_controller"


# ---------------------------------------------------------------------------
# AC12: alarmed_device_ids 排序穩定
# ---------------------------------------------------------------------------


class TestAlarmedDeviceIdsStable:
    def test_alarmed_device_ids_is_sorted_tuple(self) -> None:
        """AC12: alarmed_device_ids 為已排序的 tuple，多次呼叫穩定。"""
        sc = _make_controller()
        # 直接操作內部 set 模擬 per-device 告警順序非確定性
        sc._alarmed_devices.update({"PCS3", "PCS1", "PCS2"})

        s1 = sc.describe()
        s2 = sc.describe()

        assert isinstance(s1.alarmed_device_ids, tuple)
        # 排序確定
        assert s1.alarmed_device_ids == ("PCS1", "PCS2", "PCS3")
        # 多次呼叫穩定
        assert s1.alarmed_device_ids == s2.alarmed_device_ids

    def test_alarmed_device_ids_empty_when_no_alarm(self) -> None:
        sc = _make_controller()
        status = sc.describe()
        assert status.alarmed_device_ids == ()


# ---------------------------------------------------------------------------
# 整體 sanity: SystemControllerStatus 結構正確
# ---------------------------------------------------------------------------


class TestStatusStructure:
    def test_status_is_system_controller_status_instance(self) -> None:
        sc = _make_controller()
        status = sc.describe()
        assert isinstance(status, SystemControllerStatus)
        assert status.component == "system_controller"
        assert status.effective_mode is None  # 未註冊 mode
        assert status.auto_stop_active is False
        assert status.auto_stop_on_alarm is True  # SystemControllerConfig 預設

    def test_status_with_auto_stop_disabled(self) -> None:
        reg = DeviceRegistry()
        config = SystemControllerConfig(auto_stop_on_alarm=False)
        sc = SystemController(reg, config)

        status = sc.describe()
        assert status.auto_stop_on_alarm is False
