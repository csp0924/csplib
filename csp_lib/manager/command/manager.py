# =============== Manager Command - Manager ===============
#
# 寫入指令管理器
#
# 統一管理外部寫入指令：
#   - 維護設備註冊表
#   - 接收指令 → 記錄 DB → 執行 → 更新結果

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from csp_lib.core import get_logger
from csp_lib.core.errors import NotLeaderError
from csp_lib.equipment.transport import WriteResult, WriteStatus

from .repository import CommandRepository
from .schema import CommandRecord, CommandSource, CommandStatus, WriteCommand

if TYPE_CHECKING:
    from csp_lib.equipment.device.protocol import DeviceProtocol
    from csp_lib.equipment.transport import WriteValidationRule
    from csp_lib.manager.base import LeaderGate

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

    def __init__(
        self,
        repository: CommandRepository,
        *,
        leader_gate: LeaderGate | None = None,
        validation_rules: (Sequence[WriteValidationRule] | Mapping[str, WriteValidationRule] | None) = None,
    ) -> None:
        """
        初始化寫入指令管理器

        Args:
            repository: 指令記錄儲存庫
            leader_gate: Leader 閘門（keyword-only，可選）。非 leader 時 ``execute()``
                會在動到 repository/device 之前 raise ``NotLeaderError``，
                確保寫入指令只在 leader 節點執行。單節點部署可不注入或注入
                ``AlwaysLeaderGate``。
            validation_rules: 寫入驗證鏈（keyword-only，可選）。兩種型別：

                - ``Sequence[WriteValidationRule]``：全域 rule，對每個 point 依序全跑
                - ``Mapping[str, WriteValidationRule]``：per-point rule，僅對 key 指定
                  的 ``point_name`` 套用；未列名的 point 直接 pass-through
                - ``None`` (預設)：完全 pass-through，行為與舊版相同

                鏈中任一條 rule reject 即中止（short-circuit），``execute()`` 回傳
                ``WriteResult(status=WriteStatus.VALIDATION_FAILED)`` 且 repository
                記錄 ``CommandStatus.VALIDATION_FAILED``。clamp 場景下 rule 回傳新
                ``effective_value``，後續 rule 以該值繼續驗證，最終以 clamp 後值
                寫入設備。
        """
        self._repository = repository
        self._devices: dict[str, DeviceProtocol] = {}
        self._leader_gate = leader_gate
        # Split storage keeps Mapping lookup O(1) at execute time; Sequence runs
        # in declared order for all points.
        self._rules_global: tuple[WriteValidationRule, ...] = ()
        self._rules_by_point: dict[str, WriteValidationRule] = {}
        if isinstance(validation_rules, Mapping):
            self._rules_by_point = dict(validation_rules)
        elif validation_rules:
            self._rules_global = tuple(validation_rules)

    # ================ 設備註冊 ================

    def subscribe(self, device: DeviceProtocol) -> None:
        """
        註冊可寫入的設備（統一訂閱 API）

        這是所有子管理器的標準訂閱介面。內部委派至 ``register_device()``。

        Args:
            device: 實作 DeviceProtocol 的設備實例
        """
        self.register_device(device)

    def register_device(self, device: DeviceProtocol) -> None:
        """
        註冊可寫入的設備

        .. deprecated::
            請改用 ``subscribe()``，此方法保留作為向後相容別名。

        Args:
            device: 實作 DeviceProtocol 的設備實例
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

    def get_device(self, device_id: str) -> DeviceProtocol | None:
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

        Raises:
            NotLeaderError: 注入了 ``leader_gate`` 但目前節點非 leader。
                在動到 repository 與 device 之前擋下，避免 follower 產生 side-effect。
        """
        # 0. Leader gate：非 leader 直接拒絕（在 repository.create 之前）
        if self._leader_gate is not None and not self._leader_gate.is_leader:
            raise NotLeaderError(
                operation=f"write_command({command.device_id}.{command.point_name})",
                message="write commands are only allowed on the leader node",
            )

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

        # 3. 驗證鏈：通過回 effective command，首條 reject 回 WriteResult 直接 return
        command, reject_result = await self._run_validation(command)
        if reject_result is not None:
            return reject_result

        # 4. 更新狀態為執行中
        await self._repository.update_status(command.command_id, CommandStatus.EXECUTING)

        # 5. 執行寫入
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

    async def _run_validation(
        self,
        command: WriteCommand,
    ) -> tuple[WriteCommand, WriteResult | None]:
        """跑驗證鏈。

        Returns:
            ``(possibly_updated_command, None)`` 通過（值可能被 clamp），或
            ``(original_command, WriteResult)`` 拒絕（caller 直接 return 該 result）。
            拒絕情境會先把 VALIDATION_FAILED 寫進 repository。
        """
        # Fast path：無 rule 直接放行
        if not self._rules_global and not self._rules_by_point:
            return command, None

        original_value = command.value
        effective_value = original_value

        # Global rules 全跑；per-point rule 直接用 O(1) lookup
        applicable: list[WriteValidationRule] = list(self._rules_global)
        point_rule = self._rules_by_point.get(command.point_name)
        if point_rule is not None:
            applicable.append(point_rule)

        for rule in applicable:
            validation = rule.apply(command.point_name, effective_value)
            if not validation.accepted:
                await self._repository.update_status(
                    command.command_id,
                    CommandStatus.VALIDATION_FAILED,
                    result={
                        "point_name": command.point_name,
                        "value": original_value,
                        "rejected_reason": validation.reason,
                    },
                    error_message=validation.reason,
                )
                logger.warning(
                    f"寫入指令驗證失敗: {command.command_id} "
                    f"point={command.point_name} value={original_value!r} reason={validation.reason}"
                )
                return command, WriteResult(
                    status=WriteStatus.VALIDATION_FAILED,
                    point_name=command.point_name,
                    value=original_value,
                    error_message=validation.reason,
                )
            effective_value = validation.effective_value

        if effective_value != original_value:
            logger.info(
                f"寫入指令值已 clamp: {command.command_id} "
                f"point={command.point_name} {original_value!r} → {effective_value!r}"
            )
            command = dataclasses.replace(command, value=effective_value)
        return command, None

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
