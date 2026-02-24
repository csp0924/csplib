# =============== Manager Command - Manager ===============
#
# 寫入指令管理器
#
# 統一管理外部寫入指令：
#   - 維護設備註冊表
#   - 接收指令 → 記錄 DB → 執行 → 更新結果

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from csp_lib.core import get_logger
from csp_lib.equipment.transport import WriteResult, WriteStatus

from .repository import CommandRepository
from .schema import CommandRecord, CommandSource, CommandStatus, WriteCommand

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice

logger = get_logger(__name__)


class WriteCommandManager:
    """
    寫入指令管理器

    統一管理外部寫入指令，提供審計日誌與設備路由功能。

    職責：
        1. 維護設備註冊表（device_id → device）
        2. 接收指令 → 記錄 DB → 執行 → 更新結果
        3. 支援多種指令來源（Redis、gRPC、REST 等）

    Example:
        ```python
        from csp_lib.manager.command import WriteCommandManager, MongoCommandRepository

        repo = MongoCommandRepository(db["commands"])
        manager = WriteCommandManager(repo)

        # 註冊設備
        manager.register_device(device1)
        manager.register_device(device2)

        # 執行指令
        command = WriteCommand(
            device_id="device_001",
            point_name="setpoint",
            value=100,
        )
        result = await manager.execute(command)
        ```
    """

    def __init__(self, repository: CommandRepository) -> None:
        """
        初始化寫入指令管理器

        Args:
            repository: 指令記錄儲存庫
        """
        self._repository = repository
        self._devices: dict[str, AsyncModbusDevice] = {}

    # ================ 設備註冊 ================

    def register_device(self, device: AsyncModbusDevice) -> None:
        """
        註冊可寫入的設備

        Args:
            device: Modbus 設備實例
        """
        device_id = device.device_id
        if device_id in self._devices:
            logger.warning(f"設備 {device_id} 已註冊，將覆蓋")
        self._devices[device_id] = device
        logger.info(f"寫入指令管理器: 已註冊設備 {device_id}")

    def unregister_device(self, device_id: str) -> None:
        """
        取消註冊設備

        Args:
            device_id: 設備 ID
        """
        if device_id in self._devices:
            del self._devices[device_id]
            logger.info(f"寫入指令管理器: 已取消註冊設備 {device_id}")

    def get_device(self, device_id: str) -> AsyncModbusDevice | None:
        """
        取得已註冊的設備

        Args:
            device_id: 設備 ID

        Returns:
            設備實例，不存在時返回 None
        """
        return self._devices.get(device_id)

    @property
    def registered_device_ids(self) -> list[str]:
        """已註冊的設備 ID 列表"""
        return list(self._devices.keys())

    # ================ 指令執行 ================

    async def execute(self, command: WriteCommand) -> WriteResult:
        """
        執行寫入指令

        流程：
            1. 建立 pending 記錄至 DB
            2. 查找目標設備
            3. 執行寫入
            4. 更新 DB 結果
            5. 回傳結果

        Args:
            command: 寫入指令

        Returns:
            寫入結果
        """
        # 1. 建立記錄
        record = CommandRecord.from_command(command)
        await self._repository.create(record)

        # 2. 查找設備
        device = self._devices.get(command.device_id)
        if device is None:
            await self._repository.update_status(
                command.command_id,
                CommandStatus.DEVICE_NOT_FOUND,
                error_message=f"設備 {command.device_id} 未註冊",
            )
            logger.warning(f"寫入指令失敗: 設備 {command.device_id} 未註冊")
            return WriteResult(
                status=WriteStatus.WRITE_FAILED,
                point_name=command.point_name,
                value=command.value,
                error_message=f"設備 {command.device_id} 未註冊",
            )

        # 3. 更新狀態為執行中
        await self._repository.update_status(command.command_id, CommandStatus.EXECUTING)

        # 4. 執行寫入
        try:
            result = await device.write(
                name=command.point_name,
                value=command.value,
                verify=command.verify,
            )
        except Exception as e:
            await self._repository.update_status(
                command.command_id,
                CommandStatus.FAILED,
                error_message=str(e),
            )
            logger.error(f"寫入指令執行異常: {command.command_id}, {e}")
            return WriteResult(
                status=WriteStatus.WRITE_FAILED,
                point_name=command.point_name,
                value=command.value,
                error_message=str(e),
            )

        # 5. 更新結果
        result_dict = {
            "status": result.status.value,
            "point_name": result.point_name,
            "value": result.value,
            "error_message": result.error_message,
        }

        if result.status == WriteStatus.SUCCESS:
            await self._repository.update_status(
                command.command_id,
                CommandStatus.SUCCESS,
                result=result_dict,
            )
            logger.info(f"寫入指令成功: {command.command_id}")
        else:
            await self._repository.update_status(
                command.command_id,
                CommandStatus.FAILED,
                result=result_dict,
                error_message=result.error_message,
            )
            logger.warning(f"寫入指令失敗: {command.command_id}, {result.error_message}")

        return result

    async def execute_from_dict(
        self,
        data: dict[str, Any],
        source: CommandSource = CommandSource.INTERNAL,
    ) -> WriteResult:
        """
        從字典建立指令並執行

        供 Adapter 使用的便捷方法。

        Args:
            data: 包含 device_id, point_name, value 等欄位的字典
            source: 指令來源

        Returns:
            寫入結果
        """
        command = WriteCommand.from_dict(data, source=source)
        return await self.execute(command)


__all__ = [
    "WriteCommandManager",
]
