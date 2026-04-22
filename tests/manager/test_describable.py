# =============== Test ManagerDescribable / UnifiedManagerStatus ===============
#
# Wave 2a：Manager 觀測介面統一測試。
#
# 覆蓋：
#   - UnifiedManagerStatus frozen 驗證（FrozenInstanceError）
#   - UnifiedDeviceManager 結構性符合 ManagerDescribable Protocol
#   - describe() 各欄位在不同配置下的行為
#     * 無 leader_gate → is_leader is None
#     * 有 leader_gate(True/False) → is_leader 反映
#     * 無 alarm_manager → alarms_active_count is None
#     * 有 alarm_manager 但無 active_count 屬性 → is None
#     * 有 alarm_manager 且有 active_count → 回傳該整數
#   - 註冊設備後 devices_count 反映正確（standalone / group）
#   - 未 start 時 running=False

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock

import pytest

from csp_lib.manager import (
    ManagerDescribable,
    UnifiedConfig,
    UnifiedDeviceManager,
    UnifiedManagerStatus,
)
from csp_lib.manager.base import AlwaysLeaderGate
from tests.manager.test_leader_gate import ToggleLeaderGate

# ================ Fixtures ================


def _make_mock_device(device_id: str = "dev_desc_01") -> MagicMock:
    """產生一個最小 device mock，符合 DeviceProtocol 慣例。"""
    device = MagicMock()
    device.device_id = device_id
    return device


def _make_group_devices(count: int = 2) -> list[MagicMock]:
    """產生共用同一 client 的 mock devices（register_group 需要）。"""
    shared_client = MagicMock()
    devices: list[MagicMock] = []
    for i in range(count):
        d = MagicMock()
        d.device_id = f"grp_dev_{i:03d}"
        d._client = shared_client
        devices.append(d)
    return devices


# ================ UnifiedManagerStatus frozen 驗證 ================


class TestUnifiedManagerStatusFrozen:
    """UnifiedManagerStatus 是 frozen dataclass，欄位不可變更。"""

    def test_status_fields_assignment_raises(self) -> None:
        """改 frozen dataclass 欄位應 raise FrozenInstanceError。"""
        status = UnifiedManagerStatus(
            devices_count=0,
            running=False,
            is_leader=None,
            alarms_active_count=None,
            command_queue_depth=None,
            upload_queue_depth=None,
            state_sync_enabled=False,
            statistics_enabled=False,
        )
        with pytest.raises(FrozenInstanceError):
            status.devices_count = 99  # type: ignore[misc]

    def test_status_all_fields_accessible(self) -> None:
        """所有欄位都可讀取且型別正確。"""
        status = UnifiedManagerStatus(
            devices_count=3,
            running=True,
            is_leader=True,
            alarms_active_count=2,
            command_queue_depth=5,
            upload_queue_depth=10,
            state_sync_enabled=True,
            statistics_enabled=False,
        )
        assert status.devices_count == 3
        assert status.running is True
        assert status.is_leader is True
        assert status.alarms_active_count == 2
        assert status.command_queue_depth == 5
        assert status.upload_queue_depth == 10
        assert status.state_sync_enabled is True
        assert status.statistics_enabled is False


# ================ ManagerDescribable Protocol ================


class TestManagerDescribableProtocol:
    """UnifiedDeviceManager 結構性符合 ManagerDescribable。"""

    def test_unified_manager_is_describable(self) -> None:
        """runtime_checkable：isinstance 應為 True。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        assert isinstance(manager, ManagerDescribable) is True

    def test_describe_returns_unified_manager_status(self) -> None:
        """describe() 應回傳 UnifiedManagerStatus 實例。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        status = manager.describe()
        assert isinstance(status, UnifiedManagerStatus)


# ================ describe() 欄位行為 ================


class TestDescribeIsLeader:
    """describe().is_leader 欄位行為。"""

    def test_is_leader_none_when_no_gate(self) -> None:
        """未注入 leader_gate 時 is_leader is None。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        status = manager.describe()
        assert status.is_leader is None

    def test_is_leader_true_with_always_gate(self) -> None:
        """AlwaysLeaderGate 時 is_leader is True。"""
        manager = UnifiedDeviceManager(UnifiedConfig(), leader_gate=AlwaysLeaderGate())
        assert manager.describe().is_leader is True

    def test_is_leader_reflects_toggle_gate(self) -> None:
        """ToggleLeaderGate 切換時 is_leader 即時反映。"""
        gate = ToggleLeaderGate(initial=False)
        manager = UnifiedDeviceManager(UnifiedConfig(), leader_gate=gate)

        assert manager.describe().is_leader is False
        gate.promote()
        assert manager.describe().is_leader is True
        gate.demote()
        assert manager.describe().is_leader is False


class TestDescribeAlarmsActive:
    """describe().alarms_active_count 欄位行為。"""

    def test_alarms_none_when_no_alarm_manager(self) -> None:
        """未配置 alarm_repository 時 alarms_active_count is None。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        assert manager.describe().alarms_active_count is None

    def test_alarms_none_when_manager_lacks_active_count(self) -> None:
        """alarm_manager 存在但無 active_count 屬性時回 None。

        目前 AlarmPersistenceManager 未暴露 active_count，所以即便注入
        alarm_repository，仍應得 None。未來 Wave 若補上此屬性，下面
        ``test_alarms_count_reflects_active_count`` 會驗證正確值；本測試
        保留 None path 的行為契約。
        """
        mock_repo = MagicMock()
        manager = UnifiedDeviceManager(UnifiedConfig(alarm_repository=mock_repo))
        # 手動把 active_count 屬性移除（hasattr 檢查應回 False）
        # AlarmPersistenceManager 預設就沒有 active_count，所以直接斷言即可
        assert not hasattr(manager.alarm_manager, "active_count")
        assert manager.describe().alarms_active_count is None

    def test_alarms_count_reflects_active_count(self) -> None:
        """alarm_manager.active_count 存在時 describe 回傳該值。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        # 模擬子 manager 補了 active_count 屬性
        fake_alarm_manager = MagicMock()
        fake_alarm_manager.active_count = 7
        manager._alarm_manager = fake_alarm_manager  # type: ignore[assignment]

        assert manager.describe().alarms_active_count == 7


class TestDescribeSubManagerEnabled:
    """state_sync_enabled / statistics_enabled 反映子 manager 是否存在。"""

    def test_state_sync_disabled_by_default(self) -> None:
        manager = UnifiedDeviceManager(UnifiedConfig())
        status = manager.describe()
        assert status.state_sync_enabled is False
        assert status.statistics_enabled is False

    def test_state_sync_enabled_when_redis_configured(self) -> None:
        """配置 redis_client → state_sync_enabled=True。"""
        mock_redis = MagicMock()
        manager = UnifiedDeviceManager(UnifiedConfig(redis_client=mock_redis))
        assert manager.describe().state_sync_enabled is True


class TestDescribeDevicesCount:
    """devices_count 反映 standalone + group 設備總和。"""

    def test_devices_count_zero_initial(self) -> None:
        manager = UnifiedDeviceManager(UnifiedConfig())
        assert manager.describe().devices_count == 0

    def test_devices_count_after_standalone_register(self) -> None:
        """單設備註冊後 devices_count == 1。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        device = _make_mock_device("desc_01")
        manager.register(device)
        assert manager.describe().devices_count == 1

    def test_devices_count_after_group_register(self) -> None:
        """群組註冊後 devices_count == len(group)。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        devices = _make_group_devices(3)
        manager.register_group(devices)
        assert manager.describe().devices_count == 3

    def test_devices_count_mixed_standalone_and_group(self) -> None:
        """混合 standalone + group → devices_count 為兩者和。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        manager.register(_make_mock_device("mix_standalone"))
        manager.register_group(_make_group_devices(2))
        assert manager.describe().devices_count == 3


# ================ Edge cases ================


class TestDescribeEdgeCases:
    """邊界情境。"""

    def test_describe_before_start_running_false(self) -> None:
        """未 start 時 running=False，其他欄位正常生成（不 raise）。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        status = manager.describe()
        assert status.running is False
        assert status.devices_count == 0
        assert status.is_leader is None
        assert status.alarms_active_count is None
        # Wave 2a 預留欄位先回 None
        assert status.command_queue_depth is None
        assert status.upload_queue_depth is None

    def test_describe_is_no_io(self) -> None:
        """describe() 為純快照讀取，呼叫多次應一致（無副作用）。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        s1 = manager.describe()
        s2 = manager.describe()
        assert s1 == s2
