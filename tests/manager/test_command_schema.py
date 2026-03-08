# =============== Manager Command Tests - Schema ===============
#
# 指令 Schema 單元測試
#
# 測試覆蓋：
# - WriteCommand 建立與序列化
# - ActionCommand 建立、序列化與類別方法
# - CommandRecord 建立與序列化

from __future__ import annotations

import pytest

from csp_lib.manager.command.schema import (
    ActionCommand,
    CommandRecord,
    CommandSource,
    CommandStatus,
    WriteCommand,
)

# ======================== WriteCommand Tests ========================


class TestWriteCommand:
    """WriteCommand 測試"""

    def test_create_with_defaults(self):
        """建立 WriteCommand 使用預設值"""
        cmd = WriteCommand(
            device_id="device_001",
            point_name="setpoint",
            value=100,
        )

        assert cmd.device_id == "device_001"
        assert cmd.point_name == "setpoint"
        assert cmd.value == 100
        assert cmd.source == CommandSource.INTERNAL
        assert cmd.verify is False
        assert cmd.command_id  # 應自動生成
        assert cmd.created_at  # 應自動生成

    def test_create_with_all_fields(self):
        """建立 WriteCommand 使用全部欄位"""
        cmd = WriteCommand(
            device_id="device_001",
            point_name="setpoint",
            value=100,
            source=CommandSource.REDIS_PUBSUB,
            source_info={"user_id": "admin"},
            verify=True,
            command_id="custom_id",
        )

        assert cmd.source == CommandSource.REDIS_PUBSUB
        assert cmd.source_info == {"user_id": "admin"}
        assert cmd.verify is True
        assert cmd.command_id == "custom_id"

    def test_to_dict(self):
        """to_dict 應正確序列化"""
        cmd = WriteCommand(
            device_id="device_001",
            point_name="setpoint",
            value=100,
            command_id="test_id",
        )

        data = cmd.to_dict()
        assert data["device_id"] == "device_001"
        assert data["point_name"] == "setpoint"
        assert data["value"] == 100
        assert data["command_id"] == "test_id"
        assert data["source"] == "internal"

    def test_from_dict(self):
        """from_dict 應正確反序列化"""
        data = {
            "device_id": "device_001",
            "point_name": "setpoint",
            "value": 100,
            "verify": True,
            "source_info": {"user_id": "admin"},
        }

        cmd = WriteCommand.from_dict(data, source=CommandSource.REDIS_PUBSUB)

        assert cmd.device_id == "device_001"
        assert cmd.point_name == "setpoint"
        assert cmd.value == 100
        assert cmd.verify is True
        assert cmd.source == CommandSource.REDIS_PUBSUB

    def test_from_dict_missing_required(self):
        """from_dict 缺少必要欄位應拋出 KeyError"""
        data = {"device_id": "device_001"}

        with pytest.raises(KeyError):
            WriteCommand.from_dict(data)


# ======================== ActionCommand Tests ========================


class TestActionCommand:
    """ActionCommand 測試"""

    def test_create_without_value(self):
        """建立無參數 ActionCommand"""
        cmd = ActionCommand(
            device_id="Generator",
            action="start",
        )

        assert cmd.device_id == "Generator"
        assert cmd.action == "start"
        assert cmd.value is None
        assert cmd.params == {}  # property 應回傳空 dict

    def test_create_with_value(self):
        """建立有參數 ActionCommand"""
        cmd = ActionCommand(
            device_id="Generator",
            action="set_power",
            value={"p": 80, "q": 10},
        )

        assert cmd.value == {"p": 80, "q": 10}
        assert cmd.params == {"p": 80, "q": 10}

    def test_params_property_with_none(self):
        """params property 當 value 為 None 時回傳空 dict"""
        cmd = ActionCommand(device_id="d", action="start", value=None)
        assert cmd.params == {}

    def test_params_property_with_non_dict(self):
        """params property 當 value 非 dict 時包裝為 {'value': value}"""
        cmd = ActionCommand(device_id="d", action="start", value=123)  # type: ignore
        assert cmd.params == {"value": 123}

    def test_to_dict(self):
        """to_dict 應正確序列化"""
        cmd = ActionCommand(
            device_id="Generator",
            action="set_power",
            value={"p": 80},
            command_id="test_id",
        )

        data = cmd.to_dict()
        assert data["device_id"] == "Generator"
        assert data["action"] == "set_power"
        assert data["value"] == {"p": 80}
        assert data["command_id"] == "test_id"
        assert "params" not in data  # 應使用 value 非 params

    def test_from_dict_with_value(self):
        """from_dict 應正確解析 value"""
        data = {
            "device_id": "Generator",
            "action": "set_power",
            "value": {"p": 80, "q": 10},
        }

        cmd = ActionCommand.from_dict(data, source=CommandSource.REDIS_PUBSUB)

        assert cmd.device_id == "Generator"
        assert cmd.action == "set_power"
        assert cmd.value == {"p": 80, "q": 10}
        assert cmd.params == {"p": 80, "q": 10}
        assert cmd.source == CommandSource.REDIS_PUBSUB

    def test_from_dict_without_value(self):
        """from_dict 無 value 時應設為 None"""
        data = {
            "device_id": "Generator",
            "action": "start",
        }

        cmd = ActionCommand.from_dict(data)

        assert cmd.value is None
        assert cmd.params == {}

    def test_from_dict_missing_required(self):
        """from_dict 缺少必要欄位應拋出 KeyError"""
        data = {"device_id": "Generator"}

        with pytest.raises(KeyError):
            ActionCommand.from_dict(data)

    def test_is_action_command_true(self):
        """is_action_command 有 action 無 point_name 應返回 True"""
        data = {"device_id": "Generator", "action": "start"}
        assert ActionCommand.is_action_command(data) is True

    def test_is_action_command_with_value(self):
        """is_action_command 有 value 仍應返回 True"""
        data = {"device_id": "Generator", "action": "set_power", "value": {"p": 80}}
        assert ActionCommand.is_action_command(data) is True

    def test_is_action_command_false_no_action(self):
        """is_action_command 無 action 應返回 False"""
        data = {"device_id": "d", "point_name": "sp", "value": 100}
        assert ActionCommand.is_action_command(data) is False

    def test_is_action_command_false_has_point_name(self):
        """is_action_command 有 point_name 應返回 False"""
        data = {"device_id": "d", "action": "start", "point_name": "sp"}
        assert ActionCommand.is_action_command(data) is False


# ======================== CommandRecord Tests ========================


class TestCommandRecord:
    """CommandRecord 測試"""

    def test_from_command(self):
        """from_command 應正確建立記錄"""
        cmd = WriteCommand(
            device_id="device_001",
            point_name="setpoint",
            value=100,
            source=CommandSource.REDIS_PUBSUB,
            command_id="cmd_123",
        )

        record = CommandRecord.from_command(cmd)

        assert record.command_id == "cmd_123"
        assert record.device_id == "device_001"
        assert record.point_name == "setpoint"
        assert record.value == 100
        assert record.source == "redis_pubsub"
        assert record.status == CommandStatus.PENDING

    def test_to_dict(self):
        """to_dict 應正確序列化"""
        cmd = WriteCommand(
            device_id="device_001",
            point_name="setpoint",
            value=100,
        )
        record = CommandRecord.from_command(cmd)

        data = record.to_dict()
        assert data["device_id"] == "device_001"
        assert data["status"] == "pending"
