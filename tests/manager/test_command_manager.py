# =============== Manager Command Tests - Manager ===============
#
# WriteCommandManager 單元測試
#
# 測試覆蓋：
# - register/unregister 設備
# - execute 指令流程
# - execute_from_dict 便捷方法

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.transport import WriteResult, WriteStatus
from csp_lib.manager.command.manager import WriteCommandManager
from csp_lib.manager.command.schema import CommandSource, CommandStatus, WriteCommand


class MockDevice:
    """Mock AsyncModbusDevice for testing"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.write = AsyncMock(
            return_value=WriteResult(
                status=WriteStatus.SUCCESS,
                point_name="setpoint",
                value=100,
            )
        )


class MockRepository:
    """Mock CommandRepository for testing"""

    def __init__(self):
        self.create = AsyncMock(return_value="record_id_123")
        self.update_status = AsyncMock(return_value=True)
        self.get = AsyncMock(return_value=None)
        self.list_by_device = AsyncMock(return_value=[])


# ======================== Device Registration Tests ========================


class TestWriteCommandManagerRegistration:
    """設備註冊測試"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository()

    @pytest.fixture
    def manager(self, repository: MockRepository) -> WriteCommandManager:
        return WriteCommandManager(repository=repository)

    def test_register_device(self, manager: WriteCommandManager):
        """register_device 應註冊設備"""
        device = MockDevice("device_001")
        manager.register_device(device)

        assert "device_001" in manager.registered_device_ids
        assert manager.get_device("device_001") is device

    def test_register_device_overwrite(self, manager: WriteCommandManager):
        """重複註冊同一設備應覆蓋"""
        device1 = MockDevice("device_001")
        device2 = MockDevice("device_001")

        manager.register_device(device1)
        manager.register_device(device2)

        assert manager.get_device("device_001") is device2

    def test_unregister_device(self, manager: WriteCommandManager):
        """unregister_device 應移除設備"""
        device = MockDevice("device_001")
        manager.register_device(device)
        manager.unregister_device("device_001")

        assert "device_001" not in manager.registered_device_ids
        assert manager.get_device("device_001") is None

    def test_get_device_not_found(self, manager: WriteCommandManager):
        """get_device 應返回 None 如設備不存在"""
        assert manager.get_device("nonexistent") is None


# ======================== Execute Tests ========================


class TestWriteCommandManagerExecute:
    """指令執行測試"""

    @pytest.fixture
    def repository(self) -> MockRepository:
        return MockRepository()

    @pytest.fixture
    def manager(self, repository: MockRepository) -> WriteCommandManager:
        return WriteCommandManager(repository=repository)

    @pytest.mark.asyncio
    async def test_execute_success(self, manager: WriteCommandManager, repository: MockRepository):
        """execute 成功時應正確記錄"""
        device = MockDevice("device_001")
        manager.register_device(device)

        command = WriteCommand(
            device_id="device_001",
            point_name="setpoint",
            value=100,
        )
        result = await manager.execute(command)

        assert result.status == WriteStatus.SUCCESS
        assert result.point_name == "setpoint"
        assert result.value == 100

        # 應呼叫 create
        repository.create.assert_called_once()

        # 應呼叫 update_status 兩次（executing, success）
        assert repository.update_status.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_device_not_found(self, manager: WriteCommandManager, repository: MockRepository):
        """execute 設備未找到時應返回錯誤"""
        command = WriteCommand(
            device_id="nonexistent",
            point_name="setpoint",
            value=100,
        )
        result = await manager.execute(command)

        assert result.status == WriteStatus.WRITE_FAILED
        assert "未註冊" in result.error_message

        # 應更新狀態為 DEVICE_NOT_FOUND
        repository.update_status.assert_called()
        call_args = repository.update_status.call_args
        assert call_args[0][1] == CommandStatus.DEVICE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_execute_write_failed(self, manager: WriteCommandManager, repository: MockRepository):
        """execute 寫入失敗時應正確記錄"""
        device = MockDevice("device_001")
        device.write = AsyncMock(
            return_value=WriteResult(
                status=WriteStatus.WRITE_FAILED,
                point_name="setpoint",
                value=100,
                error_message="連線逾時",
            )
        )
        manager.register_device(device)

        command = WriteCommand(
            device_id="device_001",
            point_name="setpoint",
            value=100,
        )
        result = await manager.execute(command)

        assert result.status == WriteStatus.WRITE_FAILED
        assert result.error_message == "連線逾時"

    @pytest.mark.asyncio
    async def test_execute_from_dict(self, manager: WriteCommandManager, repository: MockRepository):
        """execute_from_dict 應正確解析並執行"""
        device = MockDevice("device_001")
        manager.register_device(device)

        data = {
            "device_id": "device_001",
            "point_name": "setpoint",
            "value": 100,
            "verify": True,
            "source_info": {"user_id": "admin"},
        }
        result = await manager.execute_from_dict(data, source=CommandSource.REDIS_PUBSUB)

        assert result.status == WriteStatus.SUCCESS
        device.write.assert_called_once_with(name="setpoint", value=100, verify=True)
