# =============== Test Unified Device Manager ===============
"""
UnifiedDeviceManager 單元測試

測試統一設備管理器的功能：
  - 註冊設備時自動訂閱子管理器
  - 可選子管理器（未配置時不報錯）
  - 生命週期管理
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from csp_lib.manager import UnifiedConfig, UnifiedDeviceManager

# ================ Fixtures ================


@pytest.fixture
def mock_device():
    """建立 Mock 設備"""
    device = MagicMock()
    device.device_id = "test_device_001"
    device.connect = AsyncMock()
    device.disconnect = AsyncMock()
    device.start = AsyncMock()
    device.stop = AsyncMock()
    return device


@pytest.fixture
def mock_devices():
    """建立多個 Mock 設備（共用同一 client）"""
    shared_client = MagicMock()  # 共用 client
    devices = []
    for i in range(3):
        device = MagicMock()
        device.device_id = f"test_device_{i:03d}"
        device._client = shared_client  # 設定共用 client
        device.connect = AsyncMock()
        device.disconnect = AsyncMock()
        device.start = AsyncMock()
        device.stop = AsyncMock()
        devices.append(device)
    return devices


@pytest.fixture
def mock_alarm_repo():
    """Mock AlarmRepository"""
    return MagicMock()


@pytest.fixture
def mock_command_repo():
    """Mock CommandRepository"""
    return MagicMock()


@pytest.fixture
def mock_uploader():
    """Mock MongoBatchUploader"""
    uploader = MagicMock()
    uploader.register_collection = MagicMock()
    return uploader


@pytest.fixture
def mock_redis():
    """Mock RedisClient"""
    return MagicMock()


# ================ 測試：配置與初始化 ================


class TestUnifiedConfig:
    """UnifiedConfig 測試"""

    def test_empty_config(self):
        """空配置應可正常建立"""
        config = UnifiedConfig()
        assert config.alarm_repository is None
        assert config.command_repository is None
        assert config.mongo_uploader is None
        assert config.redis_client is None
        assert config.notification_dispatcher is None

    def test_partial_config(self, mock_alarm_repo):
        """部分配置應可正常建立"""
        config = UnifiedConfig(alarm_repository=mock_alarm_repo)
        assert config.alarm_repository is mock_alarm_repo
        assert config.command_repository is None

    def test_config_with_notification_dispatcher(self, mock_alarm_repo):
        """配置 notification_dispatcher 應可正常建立"""
        mock_dispatcher = MagicMock()
        config = UnifiedConfig(
            alarm_repository=mock_alarm_repo,
            notification_dispatcher=mock_dispatcher,
        )
        assert config.notification_dispatcher is mock_dispatcher


# ================ 測試：初始化 ================


class TestUnifiedDeviceManagerInit:
    """UnifiedDeviceManager 初始化測試"""

    def test_empty_config_creates_only_device_manager(self):
        """空配置只建立 DeviceManager"""
        config = UnifiedConfig()
        manager = UnifiedDeviceManager(config)

        assert manager.device_manager is not None
        assert manager.alarm_manager is None
        assert manager.command_manager is None
        assert manager.data_manager is None
        assert manager.state_manager is None

    @patch("csp_lib.manager.unified.AlarmPersistenceManager")
    def test_alarm_repo_creates_alarm_manager(self, mock_apm, mock_alarm_repo):
        """配置 alarm_repository 時建立 AlarmPersistenceManager"""
        config = UnifiedConfig(alarm_repository=mock_alarm_repo)
        manager = UnifiedDeviceManager(config)

        mock_apm.assert_called_once_with(mock_alarm_repo, None)
        assert manager.alarm_manager is not None

    @patch("csp_lib.manager.unified.AlarmPersistenceManager")
    def test_alarm_repo_with_dispatcher(self, mock_apm, mock_alarm_repo):
        """配置 notification_dispatcher 時應傳遞給 AlarmPersistenceManager"""
        mock_dispatcher = MagicMock()
        config = UnifiedConfig(
            alarm_repository=mock_alarm_repo,
            notification_dispatcher=mock_dispatcher,
        )
        manager = UnifiedDeviceManager(config)

        mock_apm.assert_called_once_with(mock_alarm_repo, mock_dispatcher)
        assert manager.alarm_manager is not None

    @patch("csp_lib.manager.unified.WriteCommandManager")
    def test_command_repo_creates_command_manager(self, mock_wcm, mock_command_repo):
        """配置 command_repository 時建立 WriteCommandManager"""
        config = UnifiedConfig(command_repository=mock_command_repo)
        manager = UnifiedDeviceManager(config)

        mock_wcm.assert_called_once_with(mock_command_repo)
        assert manager.command_manager is not None

    @patch("csp_lib.manager.unified.DataUploadManager")
    def test_uploader_creates_data_manager(self, mock_dum, mock_uploader):
        """配置 mongo_uploader 時建立 DataUploadManager"""
        config = UnifiedConfig(mongo_uploader=mock_uploader)
        manager = UnifiedDeviceManager(config)

        mock_dum.assert_called_once_with(mock_uploader)
        assert manager.data_manager is not None

    @patch("csp_lib.manager.unified.StateSyncManager")
    def test_redis_creates_state_manager(self, mock_ssm, mock_redis):
        """配置 redis_client 時建立 StateSyncManager"""
        config = UnifiedConfig(redis_client=mock_redis)
        manager = UnifiedDeviceManager(config)

        mock_ssm.assert_called_once_with(mock_redis)
        assert manager.state_manager is not None


# ================ 測試：註冊設備 ================


class TestRegister:
    """register() 測試"""

    @patch("csp_lib.manager.unified.AlarmPersistenceManager")
    @patch("csp_lib.manager.unified.WriteCommandManager")
    @patch("csp_lib.manager.unified.StateSyncManager")
    def test_register_subscribes_all_managers(
        self,
        mock_ssm_cls,
        mock_wcm_cls,
        mock_apm_cls,
        mock_device,
        mock_alarm_repo,
        mock_command_repo,
        mock_redis,
    ):
        """register 應訂閱所有已啟用的子管理器"""
        mock_apm = MagicMock()
        mock_wcm = MagicMock()
        mock_ssm = MagicMock()
        mock_apm_cls.return_value = mock_apm
        mock_wcm_cls.return_value = mock_wcm
        mock_ssm_cls.return_value = mock_ssm

        config = UnifiedConfig(
            alarm_repository=mock_alarm_repo,
            command_repository=mock_command_repo,
            redis_client=mock_redis,
        )
        manager = UnifiedDeviceManager(config)
        manager.register(mock_device)

        mock_apm.subscribe.assert_called_once_with(mock_device)
        mock_wcm.register_device.assert_called_once_with(mock_device)
        mock_ssm.subscribe.assert_called_once_with(mock_device)

    @patch("csp_lib.manager.unified.DataUploadManager")
    def test_register_with_collection_name(
        self,
        mock_dum_cls,
        mock_device,
        mock_uploader,
    ):
        """register 帶 collection_name 應訂閱 DataUploadManager"""
        mock_dum = MagicMock()
        mock_dum_cls.return_value = mock_dum

        config = UnifiedConfig(mongo_uploader=mock_uploader)
        manager = UnifiedDeviceManager(config)
        manager.register(mock_device, collection_name="meter")

        mock_dum.subscribe.assert_called_once_with(mock_device, "meter")

    @patch("csp_lib.manager.unified.DataUploadManager")
    def test_register_without_collection_skips_data_upload(
        self,
        mock_dum_cls,
        mock_device,
        mock_uploader,
    ):
        """register 未帶 collection_name 應跳過 DataUploadManager"""
        mock_dum = MagicMock()
        mock_dum_cls.return_value = mock_dum

        config = UnifiedConfig(mongo_uploader=mock_uploader)
        manager = UnifiedDeviceManager(config)
        manager.register(mock_device)  # 未指定 collection_name

        mock_dum.subscribe.assert_not_called()


class TestRegisterGroup:
    """register_group() 測試"""

    @patch("csp_lib.manager.unified.StateSyncManager")
    def test_register_group_subscribes_all_devices(
        self,
        mock_ssm_cls,
        mock_devices,
        mock_redis,
    ):
        """register_group 應為每個設備訂閱子管理器"""
        mock_ssm = MagicMock()
        mock_ssm_cls.return_value = mock_ssm

        config = UnifiedConfig(redis_client=mock_redis)
        manager = UnifiedDeviceManager(config)
        manager.register_group(mock_devices)

        assert mock_ssm.subscribe.call_count == len(mock_devices)

    @patch("csp_lib.manager.unified.DataUploadManager")
    def test_register_group_with_shared_collection(
        self,
        mock_dum_cls,
        mock_devices,
        mock_uploader,
    ):
        """register_group 帶 collection_name 應為每個設備使用相同 collection"""
        mock_dum = MagicMock()
        mock_dum_cls.return_value = mock_dum

        config = UnifiedConfig(mongo_uploader=mock_uploader)
        manager = UnifiedDeviceManager(config)
        manager.register_group(mock_devices, collection_name="rtu_data")

        assert mock_dum.subscribe.call_count == len(mock_devices)
        for call in mock_dum.subscribe.call_args_list:
            assert call.args[1] == "rtu_data"


# ================ 測試：生命週期 ================


class TestLifecycle:
    """生命週期測試"""

    @pytest.mark.asyncio
    async def test_start_delegates_to_device_manager(self):
        """start 應委派給 DeviceManager"""
        config = UnifiedConfig()
        manager = UnifiedDeviceManager(config)

        with patch.object(manager._device_manager, "start", new_callable=AsyncMock) as mock_start:
            await manager.start()
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_delegates_to_device_manager(self):
        """stop 應委派給 DeviceManager"""
        config = UnifiedConfig()
        manager = UnifiedDeviceManager(config)

        with patch.object(manager._device_manager, "stop", new_callable=AsyncMock) as mock_stop:
            await manager.stop()
            mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """context manager 應正確呼叫 start/stop"""
        config = UnifiedConfig()
        manager = UnifiedDeviceManager(config)

        with (
            patch.object(manager._device_manager, "start", new_callable=AsyncMock) as mock_start,
            patch.object(manager._device_manager, "stop", new_callable=AsyncMock) as mock_stop,
        ):
            async with manager:
                mock_start.assert_called_once()
            mock_stop.assert_called_once()


# ================ 測試：屬性 ================


class TestProperties:
    """屬性測試"""

    def test_is_running_reflects_device_manager(self):
        """is_running 應反映 DeviceManager 狀態"""
        config = UnifiedConfig()
        manager = UnifiedDeviceManager(config)

        assert manager.is_running is False

    def test_repr(self):
        """__repr__ 應返回可讀字串"""
        config = UnifiedConfig()
        manager = UnifiedDeviceManager(config)

        repr_str = repr(manager)
        assert "UnifiedDeviceManager" in repr_str
        assert "devices=" in repr_str
        assert "running=" in repr_str
