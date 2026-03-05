# =============== Manager Command - Schema ===============
#
# 寫入指令資料結構
#
# 提供指令相關的資料類別：
#   - CommandSource: 指令來源類型
#   - CommandStatus: 指令執行狀態
#   - WriteCommand: 寫入指令
#   - CommandRecord: 指令記錄（DB 儲存用）

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class CommandSource(Enum):
    """指令來源類型"""

    REDIS_PUBSUB = "redis_pubsub"
    GRPC = "grpc"
    REST_API = "rest_api"
    INTERNAL = "internal"


class CommandStatus(Enum):
    """指令執行狀態"""

    PENDING = "pending"  # 等待執行
    EXECUTING = "executing"  # 執行中
    SUCCESS = "success"  # 成功
    FAILED = "failed"  # 失敗
    DEVICE_NOT_FOUND = "device_not_found"  # 設備未找到


@dataclass
class WriteCommand:
    """
    寫入指令（點位寫入）

    Attributes:
        command_id: 唯一識別碼（UUID）
        device_id: 目標設備 ID
        point_name: 點位名稱
        value: 寫入值
        source: 來源類型
        source_info: 來源詳細資訊（如 user_id, ip, channel）
        verify: 是否寫後讀回驗證
        created_at: 建立時間
    """

    device_id: str
    point_name: str
    value: Any
    source: CommandSource = CommandSource.INTERNAL
    source_info: dict[str, Any] = field(default_factory=dict)
    verify: bool = False
    command_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """轉為字典（用於 DB 儲存）"""
        return {
            "command_id": self.command_id,
            "device_id": self.device_id,
            "point_name": self.point_name,
            "value": self.value,
            "source": self.source.value,
            "source_info": self.source_info,
            "verify": self.verify,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: CommandSource = CommandSource.INTERNAL) -> WriteCommand:
        """
        從字典建立指令

        Args:
            data: 包含 device_id, point_name, value 等欄位的字典
            source: 指令來源

        Returns:
            WriteCommand 實例
        """
        return cls(
            command_id=data.get("command_id", str(uuid4())),
            device_id=data["device_id"],
            point_name=data["point_name"],
            value=data["value"],
            source=source,
            source_info=data.get("source_info", {}),
            verify=data.get("verify", False),
            created_at=data.get("created_at", datetime.now(timezone.utc)),
        )


@dataclass
class ActionCommand:
    """
    動作指令（高階動作執行）

    用於執行設備預定義的動作方法，如 start、stop 等。

    Attributes:
        command_id: 唯一識別碼（UUID）
        device_id: 目標設備 ID
        action: 動作名稱（對應設備 ACTIONS 映射）
        value: 動作參數（傳遞給方法的關鍵字參數），與 WriteCommand 統一欄位名
        source: 來源類型
        source_info: 來源詳細資訊
        created_at: 建立時間

    Example:
        ```python
        # 無參數動作
        cmd = ActionCommand(device_id="Generator", action="start")

        # 有參數動作
        cmd = ActionCommand(
            device_id="Generator",
            action="set_power",
            value={"p": 80, "q": 10},
        )
        result = await device.execute_action(cmd.action, **cmd.value)
        ```
    """

    device_id: str
    action: str
    value: dict[str, Any] | None = None
    source: CommandSource = CommandSource.INTERNAL
    source_info: dict[str, Any] = field(default_factory=dict)
    command_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def params(self) -> dict[str, Any]:
        """動作參數（用於傳遞給 execute_action）"""
        if isinstance(self.value, dict):
            return self.value
        if self.value is not None:
            return {"value": self.value}
        return {}

    def to_dict(self) -> dict[str, Any]:
        """轉為字典"""
        return {
            "command_id": self.command_id,
            "device_id": self.device_id,
            "action": self.action,
            "value": self.value,
            "source": self.source.value,
            "source_info": self.source_info,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: CommandSource = CommandSource.INTERNAL) -> ActionCommand:
        """
        從字典建立動作指令

        Args:
            data: 包含 device_id, action, value(可選) 等欄位的字典
            source: 指令來源

        Returns:
            ActionCommand 實例

        Raises:
            KeyError: 缺少必要欄位
        """
        return cls(
            command_id=data.get("command_id", str(uuid4())),
            device_id=data["device_id"],
            action=data["action"],
            value=data.get("value"),
            source=source,
            source_info=data.get("source_info", {}),
            created_at=data.get("created_at", datetime.now(timezone.utc)),
        )

    @classmethod
    def is_action_command(cls, data: dict[str, Any]) -> bool:
        """
        判斷字典是否為動作指令

        Args:
            data: 待判斷的字典

        Returns:
            True 如果包含 action 欄位且不包含 point_name
        """
        return "action" in data and "point_name" not in data


@dataclass
class CommandRecord:
    """
    指令記錄（MongoDB 儲存用）

    Attributes:
        command_id: 唯一識別碼
        device_id: 目標設備 ID
        point_name: 點位名稱
        value: 寫入值
        source: 來源類型
        source_info: 來源詳細資訊
        status: 執行狀態
        result: 執行結果
        created_at: 建立時間
        executed_at: 開始執行時間
        completed_at: 完成時間
        error_message: 錯誤訊息
    """

    command_id: str
    device_id: str
    point_name: str
    value: Any
    source: str
    source_info: dict[str, Any]
    status: CommandStatus = CommandStatus.PENDING
    result: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None

    @classmethod
    def from_command(cls, command: WriteCommand) -> CommandRecord:
        """從 WriteCommand 建立記錄"""
        return cls(
            command_id=command.command_id,
            device_id=command.device_id,
            point_name=command.point_name,
            value=command.value,
            source=command.source.value,
            source_info=command.source_info,
            status=CommandStatus.PENDING,
            created_at=command.created_at,
        )

    def to_dict(self) -> dict[str, Any]:
        """轉為字典（用於 DB 儲存）"""
        return {
            "command_id": self.command_id,
            "device_id": self.device_id,
            "point_name": self.point_name,
            "value": self.value,
            "source": self.source,
            "source_info": self.source_info,
            "status": self.status.value,
            "result": self.result,
            "created_at": self.created_at,
            "executed_at": self.executed_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandRecord:
        """從字典建立記錄"""
        return cls(
            command_id=data["command_id"],
            device_id=data["device_id"],
            point_name=data["point_name"],
            value=data["value"],
            source=data["source"],
            source_info=data.get("source_info", {}),
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            created_at=data.get("created_at", datetime.now(timezone.utc)),
            executed_at=data.get("executed_at"),
            completed_at=data.get("completed_at"),
            error_message=data.get("error_message"),
        )


__all__ = [
    "CommandSource",
    "CommandStatus",
    "WriteCommand",
    "ActionCommand",
    "CommandRecord",
]
