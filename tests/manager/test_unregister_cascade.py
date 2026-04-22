# =============== Test UnifiedDeviceManager.unregister cascade ===============
#
# Wave 2a：UnifiedDeviceManager 新增 unregister / unregister_group 的測試。
#
# 覆蓋：
#   - unregister(device_id)
#     * 已註冊設備 → 回 True，所有 sub-manager unsubscribe 被呼叫
#     * 未註冊設備 → 回 False，不 raise、不呼叫 sub-manager
#     * 某 sub-manager raise → warn log、不中斷、device_manager.unregister 仍執行
#     * device_registry 配置 → registry.unregister 被呼叫
#   - unregister_group(device_ids)
#     * 已註冊群組 → 回 True，群組內設備 sub-manager 訂閱全解除
#     * 部分 ID 不符 → 回 False
#     * 單設備 sub-manager 失敗不中斷其他設備

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.manager import UnifiedConfig, UnifiedDeviceManager

# ================ Fixtures ================


@pytest.fixture
def mock_device() -> MagicMock:
    device = MagicMock()
    device.device_id = "unreg_dev_01"
    return device


@pytest.fixture
def mock_group_devices() -> list[MagicMock]:
    shared_client = MagicMock()
    devices: list[MagicMock] = []
    for i in range(3):
        d = MagicMock()
        d.device_id = f"unreg_grp_{i:03d}"
        d._client = shared_client
        devices.append(d)
    return devices


@pytest.fixture
def mock_alarm_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_command_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_uploader() -> MagicMock:
    u = MagicMock()
    u.register_collection = MagicMock()
    return u


@pytest.fixture
def mock_redis() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_registry() -> MagicMock:
    """Mock DeviceRegistry：register + unregister 皆同步呼叫。"""
    reg = MagicMock()
    reg.register = MagicMock()
    reg.unregister = MagicMock(return_value=True)
    return reg


# ================ unregister(): 找不到設備 ================


class TestUnregisterNotFound:
    """未註冊 device_id 的行為。"""

    async def test_unregister_unknown_returns_false(self) -> None:
        """未註冊設備 → 回 False，不 raise。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        result = await manager.unregister("nonexistent_device")
        assert result is False

    async def test_unregister_unknown_does_not_touch_sub_managers(
        self,
        mock_alarm_repo: MagicMock,
        mock_command_repo: MagicMock,
        mock_redis: MagicMock,
    ) -> None:
        """未註冊設備時不應呼叫任何 sub-manager（整個 fast-path 早退）。"""
        config = UnifiedConfig(
            alarm_repository=mock_alarm_repo,
            command_repository=mock_command_repo,
            redis_client=mock_redis,
        )
        manager = UnifiedDeviceManager(config)

        # 把所有 sub-manager 換成 MagicMock 以便驗證零呼叫
        manager._alarm_manager = MagicMock()  # type: ignore[assignment]
        manager._command_manager = MagicMock()  # type: ignore[assignment]
        manager._state_manager = MagicMock()  # type: ignore[assignment]

        result = await manager.unregister("ghost")

        assert result is False
        manager._alarm_manager.unsubscribe.assert_not_called()
        manager._command_manager.unregister_device.assert_not_called()
        manager._state_manager.unsubscribe.assert_not_called()


# ================ unregister(): 成功路徑 ================


class TestUnregisterCascadeSuccess:
    """已註冊設備的級聯解除。"""

    async def test_unregister_calls_all_sub_managers(
        self,
        mock_device: MagicMock,
        mock_alarm_repo: MagicMock,
        mock_command_repo: MagicMock,
        mock_uploader: MagicMock,
        mock_redis: MagicMock,
    ) -> None:
        """已註冊設備 → 所有啟用的 sub-manager 對應 unsubscribe/unregister_device 被呼叫。"""
        config = UnifiedConfig(
            alarm_repository=mock_alarm_repo,
            command_repository=mock_command_repo,
            mongo_uploader=mock_uploader,
            redis_client=mock_redis,
        )
        manager = UnifiedDeviceManager(config)
        manager.register(mock_device, collection_name="meter")

        # 替換成可追蹤的 mock（保留 subscribe 時插入的狀態）
        alarm_mgr = MagicMock()
        command_mgr = MagicMock()
        data_mgr = MagicMock()
        state_mgr = MagicMock()
        manager._alarm_manager = alarm_mgr  # type: ignore[assignment]
        manager._command_manager = command_mgr  # type: ignore[assignment]
        manager._data_manager = data_mgr  # type: ignore[assignment]
        manager._state_manager = state_mgr  # type: ignore[assignment]

        # device_manager.unregister 也替成 AsyncMock 以避免真實 lifecycle
        manager._device_manager.unregister = AsyncMock(return_value=True)  # type: ignore[method-assign]

        result = await manager.unregister(mock_device.device_id)

        assert result is True
        alarm_mgr.unsubscribe.assert_called_once_with(mock_device)
        command_mgr.unregister_device.assert_called_once_with(mock_device.device_id)
        data_mgr.unsubscribe.assert_called_once_with(mock_device)
        state_mgr.unsubscribe.assert_called_once_with(mock_device)
        manager._device_manager.unregister.assert_awaited_once_with(mock_device.device_id)

    async def test_unregister_calls_registry_when_configured(
        self,
        mock_device: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """配置 device_registry 時 unregister 應呼叫 registry.unregister。"""
        config = UnifiedConfig(device_registry=mock_registry)
        manager = UnifiedDeviceManager(config)
        manager.register(mock_device)
        manager._device_manager.unregister = AsyncMock(return_value=True)  # type: ignore[method-assign]

        await manager.unregister(mock_device.device_id)

        mock_registry.unregister.assert_called_once_with(mock_device.device_id)

    async def test_unregister_no_registry_skips_registry_call(
        self,
        mock_device: MagicMock,
    ) -> None:
        """未配置 device_registry 時不應嘗試呼叫 registry。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        manager.register(mock_device)
        manager._device_manager.unregister = AsyncMock(return_value=True)  # type: ignore[method-assign]

        # 不 raise 即視為通過（無 registry 可呼叫）
        result = await manager.unregister(mock_device.device_id)
        assert result is True


# ================ unregister(): 部分失敗 ================


class TestUnregisterPartialFailure:
    """單步 sub-manager raise 不應中斷其他步驟。"""

    async def test_sub_manager_raise_does_not_abort_cascade(
        self,
        mock_device: MagicMock,
        mock_alarm_repo: MagicMock,
        mock_command_repo: MagicMock,
        mock_redis: MagicMock,
    ) -> None:
        """alarm_manager.unsubscribe 爆 → 後續 sub-manager 與 device_manager 仍被呼叫。"""
        config = UnifiedConfig(
            alarm_repository=mock_alarm_repo,
            command_repository=mock_command_repo,
            redis_client=mock_redis,
        )
        manager = UnifiedDeviceManager(config)
        manager.register(mock_device)

        alarm_mgr = MagicMock()
        alarm_mgr.unsubscribe.side_effect = RuntimeError("alarm boom")
        command_mgr = MagicMock()
        state_mgr = MagicMock()
        manager._alarm_manager = alarm_mgr  # type: ignore[assignment]
        manager._command_manager = command_mgr  # type: ignore[assignment]
        manager._state_manager = state_mgr  # type: ignore[assignment]
        manager._device_manager.unregister = AsyncMock(return_value=True)  # type: ignore[method-assign]

        # 不應 raise（每步獨立 try/except）
        result = await manager.unregister(mock_device.device_id)
        assert result is True

        # 即便 alarm 失敗，後續步驟仍被呼叫
        alarm_mgr.unsubscribe.assert_called_once()
        command_mgr.unregister_device.assert_called_once_with(mock_device.device_id)
        state_mgr.unsubscribe.assert_called_once_with(mock_device)
        manager._device_manager.unregister.assert_awaited_once()

    async def test_registry_raise_does_not_abort_device_manager(
        self,
        mock_device: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """registry.unregister raise → device_manager.unregister 仍應被呼叫。"""
        mock_registry.unregister.side_effect = RuntimeError("registry boom")
        config = UnifiedConfig(device_registry=mock_registry)
        manager = UnifiedDeviceManager(config)
        manager.register(mock_device)
        manager._device_manager.unregister = AsyncMock(return_value=True)  # type: ignore[method-assign]

        result = await manager.unregister(mock_device.device_id)
        assert result is True
        manager._device_manager.unregister.assert_awaited_once()

    async def test_device_manager_raise_returns_true_but_logs(
        self,
        mock_device: MagicMock,
    ) -> None:
        """device_manager.unregister 爆仍應回 True（表示「已觸發卸載流程」）。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        manager.register(mock_device)
        manager._device_manager.unregister = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("dm boom")
        )

        # 契約：回 True 代表「找到並觸發」，即便 async 步驟 log warning
        result = await manager.unregister(mock_device.device_id)
        assert result is True


# ================ unregister_group() ================


class TestUnregisterGroup:
    """unregister_group 測試。"""

    async def test_unregister_group_success_returns_true(
        self,
        mock_group_devices: list[MagicMock],
        mock_redis: MagicMock,
    ) -> None:
        """已註冊群組 → 回 True，所有設備 state_manager.unsubscribe 被呼叫。"""
        config = UnifiedConfig(redis_client=mock_redis)
        manager = UnifiedDeviceManager(config)
        manager.register_group(mock_group_devices)

        state_mgr = MagicMock()
        manager._state_manager = state_mgr  # type: ignore[assignment]
        manager._device_manager.unregister_group = AsyncMock(return_value=True)  # type: ignore[method-assign]

        device_ids = [d.device_id for d in mock_group_devices]
        result = await manager.unregister_group(device_ids)

        assert result is True
        assert state_mgr.unsubscribe.call_count == len(mock_group_devices)
        manager._device_manager.unregister_group.assert_awaited_once_with(device_ids)

    async def test_unregister_group_partial_ids_returns_false(
        self,
        mock_group_devices: list[MagicMock],
    ) -> None:
        """給的 ID 集合與任何群組都不匹配（少了一個）→ 回 False。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        manager.register_group(mock_group_devices)

        partial = [d.device_id for d in mock_group_devices[:-1]]  # 少最後一個
        result = await manager.unregister_group(partial)
        assert result is False

    async def test_unregister_group_unknown_returns_false(self) -> None:
        """完全陌生的 device_ids → 回 False。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        result = await manager.unregister_group(["ghost_a", "ghost_b"])
        assert result is False

    async def test_unregister_group_single_device_failure_does_not_abort(
        self,
        mock_group_devices: list[MagicMock],
        mock_redis: MagicMock,
    ) -> None:
        """某設備 sub-manager unsubscribe 爆 → 後續設備仍被處理。"""
        config = UnifiedConfig(redis_client=mock_redis)
        manager = UnifiedDeviceManager(config)
        manager.register_group(mock_group_devices)

        state_mgr = MagicMock()

        # 第一個設備 unsubscribe 爆，後兩個正常
        def _maybe_raise(device: MagicMock) -> None:
            if device.device_id == mock_group_devices[0].device_id:
                raise RuntimeError("state boom")

        state_mgr.unsubscribe.side_effect = _maybe_raise
        manager._state_manager = state_mgr  # type: ignore[assignment]
        manager._device_manager.unregister_group = AsyncMock(return_value=True)  # type: ignore[method-assign]

        device_ids = [d.device_id for d in mock_group_devices]
        result = await manager.unregister_group(device_ids)

        assert result is True
        # 三個設備都應嘗試 unsubscribe（不因第一個爆就停）
        assert state_mgr.unsubscribe.call_count == len(mock_group_devices)

    async def test_unregister_group_id_order_independent(
        self,
        mock_group_devices: list[MagicMock],
        mock_redis: MagicMock,
    ) -> None:
        """ID 順序不同但集合相符 → 應被識別為同一群組。"""
        config = UnifiedConfig(redis_client=mock_redis)
        manager = UnifiedDeviceManager(config)
        manager.register_group(mock_group_devices)
        manager._device_manager.unregister_group = AsyncMock(return_value=True)  # type: ignore[method-assign]

        reversed_ids = list(reversed([d.device_id for d in mock_group_devices]))
        result = await manager.unregister_group(reversed_ids)
        assert result is True


# ================ _find_registered_device helper ================


class TestFindRegisteredDevice:
    """_find_registered_device 在 standalone / group 中找 device。"""

    def test_find_standalone_device(self, mock_device: MagicMock) -> None:
        manager = UnifiedDeviceManager(UnifiedConfig())
        manager.register(mock_device)

        found = manager._find_registered_device(mock_device.device_id)
        assert found is mock_device

    def test_find_group_device(self, mock_group_devices: list[MagicMock]) -> None:
        manager = UnifiedDeviceManager(UnifiedConfig())
        manager.register_group(mock_group_devices)

        target = mock_group_devices[1]
        found = manager._find_registered_device(target.device_id)
        assert found is target

    def test_find_returns_none_when_not_found(self) -> None:
        manager = UnifiedDeviceManager(UnifiedConfig())
        assert manager._find_registered_device("ghost") is None
