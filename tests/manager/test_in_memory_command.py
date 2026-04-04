# =============== Manager Tests - In-Memory Command Repository ===============
#
# InMemoryCommandRepository 單元測試
#
# 測試覆蓋：
# - create 回傳唯一 ID
# - update_status 狀態轉換與時間戳
# - get 查詢
# - list_by_device 排序與限制
# - 測試輔助方法：clear, get_all_records
# - health_check

from __future__ import annotations

from datetime import datetime, timezone

from csp_lib.manager.command.in_memory import InMemoryCommandRepository
from csp_lib.manager.command.schema import CommandRecord, CommandStatus


def _make_command(
    command_id: str = "cmd_001",
    device_id: str = "pcs_01",
    point_name: str = "p_setpoint",
    value: float = 100.0,
    timestamp: datetime | None = None,
) -> CommandRecord:
    """建立測試用 CommandRecord"""
    return CommandRecord(
        command_id=command_id,
        device_id=device_id,
        point_name=point_name,
        value=value,
        source="internal",
        source_info={},
        status=CommandStatus.PENDING,
        timestamp=timestamp or datetime.now(timezone.utc),
    )


class TestInMemoryCommandRepository:
    """InMemoryCommandRepository 功能測試"""

    async def test_create_returns_id(self):
        """create 回傳非空 ID"""
        repo = InMemoryCommandRepository()
        record_id = await repo.create(_make_command())
        assert isinstance(record_id, str)
        assert len(record_id) > 0

    async def test_create_unique_ids(self):
        """多次 create 回傳不同 ID"""
        repo = InMemoryCommandRepository()
        id1 = await repo.create(_make_command(command_id="c1"))
        id2 = await repo.create(_make_command(command_id="c2"))
        assert id1 != id2

    async def test_get_by_command_id(self):
        """get 以 command_id 查詢"""
        repo = InMemoryCommandRepository()
        await repo.create(_make_command(command_id="find_me"))

        record = await repo.get("find_me")
        assert record is not None
        assert record.command_id == "find_me"

    async def test_get_nonexistent(self):
        """get 不存在的 command_id → None"""
        repo = InMemoryCommandRepository()
        assert await repo.get("nonexistent") is None

    async def test_update_status_executing(self):
        """update_status → EXECUTING 設定 executed_at"""
        repo = InMemoryCommandRepository()
        await repo.create(_make_command(command_id="cmd1"))

        result = await repo.update_status("cmd1", CommandStatus.EXECUTING)
        assert result is True

        record = await repo.get("cmd1")
        assert record is not None
        assert record.status == CommandStatus.EXECUTING
        assert record.executed_at is not None

    async def test_update_status_success(self):
        """update_status → SUCCESS 設定 completed_at"""
        repo = InMemoryCommandRepository()
        await repo.create(_make_command(command_id="cmd2"))

        await repo.update_status("cmd2", CommandStatus.EXECUTING)
        result = await repo.update_status("cmd2", CommandStatus.SUCCESS, result={"ok": True})
        assert result is True

        record = await repo.get("cmd2")
        assert record is not None
        assert record.status == CommandStatus.SUCCESS
        assert record.completed_at is not None
        assert record.result == {"ok": True}

    async def test_update_status_failed_with_error(self):
        """update_status → FAILED 設定 error_message"""
        repo = InMemoryCommandRepository()
        await repo.create(_make_command(command_id="cmd3"))

        result = await repo.update_status("cmd3", CommandStatus.FAILED, error_message="timeout")
        assert result is True

        record = await repo.get("cmd3")
        assert record is not None
        assert record.status == CommandStatus.FAILED
        assert record.error_message == "timeout"
        assert record.completed_at is not None

    async def test_update_status_device_not_found(self):
        """update_status → DEVICE_NOT_FOUND 設定 completed_at"""
        repo = InMemoryCommandRepository()
        await repo.create(_make_command(command_id="cmd4"))

        result = await repo.update_status("cmd4", CommandStatus.DEVICE_NOT_FOUND)
        assert result is True

        record = await repo.get("cmd4")
        assert record is not None
        assert record.completed_at is not None

    async def test_update_status_nonexistent(self):
        """update_status 不存在的 command_id → False"""
        repo = InMemoryCommandRepository()
        result = await repo.update_status("nope", CommandStatus.EXECUTING)
        assert result is False

    async def test_list_by_device_sorted_desc(self):
        """list_by_device 按 timestamp DESC 排序"""
        repo = InMemoryCommandRepository()
        ts1 = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        ts3 = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)

        await repo.create(_make_command(command_id="c1", device_id="d1", timestamp=ts1))
        await repo.create(_make_command(command_id="c2", device_id="d1", timestamp=ts2))
        await repo.create(_make_command(command_id="c3", device_id="d1", timestamp=ts3))

        records = await repo.list_by_device("d1")
        assert len(records) == 3
        assert records[0].command_id == "c2"  # 最新
        assert records[1].command_id == "c3"
        assert records[2].command_id == "c1"  # 最舊

    async def test_list_by_device_limit(self):
        """list_by_device 限制回傳數量"""
        repo = InMemoryCommandRepository()
        for i in range(5):
            ts = datetime(2024, 1, 1, i, tzinfo=timezone.utc)
            await repo.create(_make_command(command_id=f"c{i}", device_id="d1", timestamp=ts))

        records = await repo.list_by_device("d1", limit=2)
        assert len(records) == 2

    async def test_list_by_device_filters_device(self):
        """list_by_device 只回傳指定設備"""
        repo = InMemoryCommandRepository()
        await repo.create(_make_command(command_id="c1", device_id="d1"))
        await repo.create(_make_command(command_id="c2", device_id="d2"))

        records = await repo.list_by_device("d1")
        assert len(records) == 1
        assert records[0].command_id == "c1"

    async def test_list_by_device_empty(self):
        """list_by_device 無資料回傳空列表"""
        repo = InMemoryCommandRepository()
        assert await repo.list_by_device("no_device") == []

    async def test_clear(self):
        """clear 清除所有記錄"""
        repo = InMemoryCommandRepository()
        await repo.create(_make_command())
        repo.clear()
        assert repo.get_all_records() == {}

    async def test_get_all_records(self):
        """get_all_records 回傳所有記錄"""
        repo = InMemoryCommandRepository()
        await repo.create(_make_command(command_id="a"))
        await repo.create(_make_command(command_id="b"))
        assert len(repo.get_all_records()) == 2

    async def test_health_check(self):
        """health_check 回傳 True"""
        repo = InMemoryCommandRepository()
        assert await repo.health_check() is True
