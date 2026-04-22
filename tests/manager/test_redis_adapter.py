# =============== Manager Redis Adapter Tests ===============
#
# RedisCommandAdapter 單元測試
#
# 重點驗證 _execute_action 對缺少 execute_action 能力之裝置的 fail-fast 行為
# （Copilot PR#104 review 建議 — 避免 AttributeError 被 except Exception 吞掉
# 導致 CommandResult 不 publish 的 silent failure）。

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.equipment.transport import WriteResult, WriteStatus
from csp_lib.manager.command.adapters.redis import RedisCommandAdapter
from csp_lib.manager.command.manager import WriteCommandManager


@pytest.fixture
def adapter() -> RedisCommandAdapter:
    """最小 RedisCommandAdapter 實例（redis/manager 皆 MagicMock，無需真連線）。"""
    redis_client = MagicMock()
    manager = MagicMock(spec=WriteCommandManager)
    return RedisCommandAdapter(redis_client=redis_client, manager=manager)


class TestExecuteActionCapabilityCheck:
    """_execute_action 對 execute_action 能力缺失時的 fail-fast 驗證。

    共用 ``make_mock_device_protocol`` fixture（conftest）—— MockDeviceProtocol 預設
    **不含** execute_action，剛好作為「能力缺失」 scenario；具能力時於測試內 attach AsyncMock。
    """

    async def test_device_without_execute_action_returns_write_failed(
        self, adapter: RedisCommandAdapter, make_mock_device_protocol
    ):
        """缺 execute_action 的裝置應回傳明確 WRITE_FAILED（而非讓 AttributeError 被吞）。"""
        device = make_mock_device_protocol("proto_only")
        adapter._manager.get_device = MagicMock(return_value=device)  # type: ignore[assignment]

        result = await adapter._execute_action({"device_id": "proto_only", "action": "start"})

        assert result.status == WriteStatus.WRITE_FAILED.value
        assert result.device_id == "proto_only"
        assert result.action == "start"
        assert result.error_message is not None
        assert "does not support action" in result.error_message

    async def test_device_with_execute_action_executes_normally(
        self, adapter: RedisCommandAdapter, make_mock_device_protocol
    ):
        """具 execute_action 的裝置應正常執行並回傳 SUCCESS。"""
        device = make_mock_device_protocol("dev_action")
        device.execute_action = AsyncMock(
            return_value=WriteResult(status=WriteStatus.SUCCESS, point_name="", value=None)
        )
        adapter._manager.get_device = MagicMock(return_value=device)  # type: ignore[assignment]

        result = await adapter._execute_action({"device_id": "dev_action", "action": "start"})

        assert result.status == WriteStatus.SUCCESS.value
        assert result.device_id == "dev_action"
        assert result.action == "start"
        device.execute_action.assert_awaited_once_with("start")

    async def test_device_without_execute_action_preserves_value(
        self, adapter: RedisCommandAdapter, make_mock_device_protocol
    ):
        """能力不足回傳的 CommandResult 應包含原 value（方便呼叫端追蹤是哪筆指令）。"""
        device = make_mock_device_protocol("proto_only")
        adapter._manager.get_device = MagicMock(return_value=device)  # type: ignore[assignment]

        result = await adapter._execute_action({"device_id": "proto_only", "action": "set_power", "value": {"p": 80}})

        assert result.status == WriteStatus.WRITE_FAILED.value
        assert result.action == "set_power"
        assert result.value == {"p": 80}
