# =============== Manager Command - Redis Adapter ===============
#
# Redis Pub/Sub 指令適配器
#
# 監聽 Redis channel 接收指令並轉發至 WriteCommandManager
# 支援兩種指令類型：
#   - WriteCommand: 點位寫入 {"device_id", "point_name", "value"}
#   - ActionCommand: 動作執行 {"device_id", "action", "params"}

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from csp_lib.core import AsyncLifecycleMixin, get_logger
from csp_lib.equipment.transport import WriteStatus

from ..schema import ActionCommand, CommandSource
from .config import CommandAdapterConfig

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from csp_lib.integration.orchestrator import SystemCommandOrchestrator

    from ..manager import WriteCommandManager

logger = get_logger(__name__)


# ========== Result Schema ==========


@dataclass(frozen=True)
class CommandResult:
    """
    指令執行結果

    用於發布到 result_channel 的標準化結果格式。

    Attributes:
        command_id: 指令 ID
        device_id: 設備 ID
        status: 執行狀態
        action: 動作名稱（ActionCommand 時）
        point_name: 點位名稱（WriteCommand 時）
        value: 寫入值或動作參數
        error_message: 錯誤訊息
    """

    command_id: str
    device_id: str
    status: str
    action: str | None = None
    point_name: str | None = None
    value: Any = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """轉為字典（用於 JSON 序列化）"""
        return {
            "command_id": self.command_id,
            "device_id": self.device_id,
            "status": self.status,
            "action": self.action,
            "point_name": self.point_name,
            "value": self.value,
            "error_message": self.error_message,
        }


# ========== Redis Adapter ==========


class RedisCommandAdapter(AsyncLifecycleMixin):
    """
    Redis Pub/Sub 指令適配器

    監聯指定 channel，解析 JSON 指令並轉發至 WriteCommandManager。
    執行完成後將結果發布到結果 channel。

    支援兩種指令類型：
        - 點位寫入 (WriteCommand): {"device_id", "point_name", "value", "verify"}
        - 動作執行 (ActionCommand): {"device_id", "action", "params"}

    Attributes:
        _redis: Redis 客戶端
        _manager: 寫入指令管理器
        _command_channel: 接收指令的 channel
        _result_channel: 發布結果的 channel

    Example:
        ```python
        adapter = RedisCommandAdapter(
            redis_client=redis_client._client,
            manager=command_manager,
        )
        await adapter.start()

        # 點位寫入
        # PUBLISH channel:commands:write '{"device_id":"d1","point_name":"sp","value":100}'

        # 動作執行
        # PUBLISH channel:commands:write '{"device_id":"Generator","action":"start"}'
        # PUBLISH channel:commands:write '{"device_id":"Generator","action":"set_power","params":{"p":80}}'
        ```
    """

    def __init__(
        self,
        redis_client: Redis,
        manager: WriteCommandManager,
        config: CommandAdapterConfig | None = None,
        command_channel: str | None = None,
        result_channel: str | None = None,
        orchestrator: SystemCommandOrchestrator | None = None,
    ) -> None:
        """
        初始化 Redis 指令適配器

        Args:
            redis_client: redis.asyncio.Redis 客戶端實例
            manager: 寫入指令管理器
            config: 適配器配置（優先使用）
            command_channel: 接收指令的 channel，config 為 None 時使用
            result_channel: 發布結果的 channel，config 為 None 時使用
            orchestrator: 系統指令編排器（可選，提供時支援系統級指令）
        """
        self._redis = redis_client
        self._manager = manager
        if config is None:
            config = CommandAdapterConfig(
                command_channel=command_channel or "channel:commands:write",
                result_channel=result_channel or "channel:commands:result",
            )
        self._config = config
        self._command_channel = self._config.command_channel
        self._result_channel = self._config.result_channel
        self._orchestrator = orchestrator
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        """是否正在運行"""
        return self._running

    async def _on_start(self) -> None:
        """
        啟動監聽

        開始訂閱 command_channel 並處理指令。
        """
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._listen_loop())
        logger.info(f"Redis 指令適配器已啟動: {self._command_channel}")

    async def _on_stop(self) -> None:
        """
        停止監聽

        取消訂閱並停止處理。
        """
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Redis 指令適配器已停止")

    async def _listen_loop(self) -> None:
        """監聽循環"""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._command_channel)

        try:
            while self._running:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    await self._handle_message(message["data"])
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(self._command_channel)
            await pubsub.aclose()

    async def _handle_message(self, data: str | bytes) -> None:
        """處理訊息"""
        try:
            if isinstance(data, bytes):
                data = data.decode("utf-8")

            command_data = json.loads(data)
            logger.debug(f"收到指令: {command_data}")

            # 判斷指令類型：系統指令 → 動作指令 → 寫入指令
            if "system_command" in command_data:
                result = await self._execute_system_command(command_data)
            elif ActionCommand.is_action_command(command_data):
                result = await self._execute_action(command_data)
            else:
                result = await self._execute_write(command_data)

            # 發布結果
            await self._publish_result(result)

        except json.JSONDecodeError as e:
            logger.error(f"指令 JSON 解析失敗: {e}")
        except KeyError as e:
            logger.error(f"指令缺少必要欄位: {e}")
        except Exception as e:
            logger.error(f"指令處理失敗: {e}")

    async def _execute_action(self, data: dict[str, Any]) -> CommandResult:
        """
        執行動作指令

        Args:
            data: 包含 device_id, action, value(可選) 的字典

        Returns:
            CommandResult
        """
        try:
            command = ActionCommand.from_dict(data, source=CommandSource.REDIS_PUBSUB)
        except KeyError as e:
            return CommandResult(
                command_id=data.get("command_id", ""),
                device_id=data.get("device_id", ""),
                status=WriteStatus.VALIDATION_FAILED.value,
                action=data.get("action"),
                error_message=f"Missing required field: {e}",
            )

        device = self._manager.get_device(command.device_id)
        if device is None:
            return CommandResult(
                command_id=command.command_id,
                device_id=command.device_id,
                status=WriteStatus.WRITE_FAILED.value,
                action=command.action,
                error_message=f"Device '{command.device_id}' not registered",
            )

        logger.info(f"執行 action: {command.device_id}.{command.action}, value={command.value}")
        result = await device.execute_action(command.action, **command.params)
        if result.status != WriteStatus.SUCCESS:
            logger.error(
                f"Action 執行失敗: device_id={command.device_id}, action={command.action}, value={command.value}, error={result.error_message}"
            )
            return CommandResult(
                command_id=command.command_id,
                device_id=command.device_id,
                status=result.status.value,
                action=command.action,
                value=command.value,
                error_message=result.error_message,
            )
        else:
            logger.info(
                f"Action 執行成功: device_id={command.device_id}, action={command.action}, value={command.value}"
            )

        return CommandResult(
            command_id=command.command_id,
            device_id=command.device_id,
            status=result.status.value,
            action=command.action,
            value=command.value,
            error_message=result.error_message,
        )

    async def _execute_system_command(self, data: dict[str, Any]) -> CommandResult:
        """
        執行系統級指令

        Args:
            data: 包含 system_command 的字典

        Returns:
            CommandResult
        """
        command_name = data["system_command"]

        if self._orchestrator is None:
            return CommandResult(
                command_id=data.get("command_id", ""),
                device_id="system",
                status="failed",
                action=command_name,
                error_message="System command orchestrator is not configured",
            )

        try:
            result = await self._orchestrator.execute(command_name)
            return CommandResult(
                command_id=data.get("command_id", ""),
                device_id="system",
                status=result.status,
                action=command_name,
                error_message=result.error_message,
            )
        except KeyError as e:
            return CommandResult(
                command_id=data.get("command_id", ""),
                device_id="system",
                status="failed",
                action=command_name,
                error_message=str(e),
            )

    async def _execute_write(self, data: dict[str, Any]) -> CommandResult:
        """
        執行寫入指令

        Args:
            data: 包含 device_id, point_name, value 的字典

        Returns:
            CommandResult
        """
        result = await self._manager.execute_from_dict(
            data,
            source=CommandSource.REDIS_PUBSUB,
        )

        return CommandResult(
            command_id=data.get("command_id", ""),
            device_id=data.get("device_id", ""),
            status=result.status.value,
            point_name=result.point_name,
            value=result.value,
            error_message=result.error_message,
        )

    async def _publish_result(self, result: CommandResult) -> None:
        """
        發布執行結果

        Args:
            result: 指令執行結果
        """
        message = json.dumps(result.to_dict())
        await self._redis.publish(self._result_channel, message)


__all__ = [
    "RedisCommandAdapter",
    "CommandResult",
]
