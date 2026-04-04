# =============== Manager Tests - In-Memory Alarm Repository ===============
#
# InMemoryAlarmRepository 單元測試
#
# 測試覆蓋：
# - upsert 新告警 / 已存在 ACTIVE 告警
# - resolve 成功 / 不存在
# - get_active_alarms / get_active_by_device 過濾
# - 測試輔助方法：clear, get_all_records
# - health_check

from __future__ import annotations

from datetime import datetime, timezone

from csp_lib.equipment.alarm import AlarmLevel
from csp_lib.manager.alarm.in_memory import InMemoryAlarmRepository
from csp_lib.manager.alarm.schema import AlarmRecord, AlarmStatus, AlarmType


def _make_alarm(
    device_id: str = "pcs_01",
    alarm_code: str = "OVER_TEMP",
    alarm_type: AlarmType = AlarmType.DEVICE_ALARM,
    status: AlarmStatus = AlarmStatus.ACTIVE,
) -> AlarmRecord:
    """建立測試用 AlarmRecord"""
    key = AlarmRecord.make_key(device_id, alarm_type, alarm_code)
    return AlarmRecord(
        alarm_key=key,
        device_id=device_id,
        alarm_type=alarm_type,
        alarm_code=alarm_code,
        name=f"Test alarm {alarm_code}",
        level=AlarmLevel.WARNING,
        timestamp=datetime.now(timezone.utc),
        status=status,
    )


class TestInMemoryAlarmRepository:
    """InMemoryAlarmRepository 功能測試"""

    async def test_upsert_new_alarm(self):
        """upsert 新告警 → (key, True)"""
        repo = InMemoryAlarmRepository()
        record = _make_alarm()
        key, is_new = await repo.upsert(record)
        assert key == record.alarm_key
        assert is_new is True

    async def test_upsert_existing_active_alarm(self):
        """upsert 已存在的 ACTIVE 告警 → (key, False)"""
        repo = InMemoryAlarmRepository()
        record = _make_alarm()
        await repo.upsert(record)

        key, is_new = await repo.upsert(record)
        assert key == record.alarm_key
        assert is_new is False

    async def test_upsert_after_resolve_creates_new(self):
        """解除後再 upsert 同一 key → 視為新告警"""
        repo = InMemoryAlarmRepository()
        record = _make_alarm()
        await repo.upsert(record)
        await repo.resolve(record.alarm_key, datetime.now(timezone.utc))

        new_record = _make_alarm()
        key, is_new = await repo.upsert(new_record)
        assert is_new is True

    async def test_resolve_existing_active(self):
        """resolve 存在的 ACTIVE 告警 → True"""
        repo = InMemoryAlarmRepository()
        record = _make_alarm()
        await repo.upsert(record)

        resolved_at = datetime.now(timezone.utc)
        result = await repo.resolve(record.alarm_key, resolved_at)
        assert result is True

        # 驗證狀態已更新
        all_records = repo.get_all_records()
        resolved = all_records[record.alarm_key]
        assert resolved.status == AlarmStatus.RESOLVED
        assert resolved.resolved_timestamp == resolved_at

    async def test_resolve_nonexistent(self):
        """resolve 不存在的 alarm_key → False"""
        repo = InMemoryAlarmRepository()
        result = await repo.resolve("nonexistent_key", datetime.now(timezone.utc))
        assert result is False

    async def test_resolve_already_resolved(self):
        """resolve 已 RESOLVED 的告警 → False"""
        repo = InMemoryAlarmRepository()
        record = _make_alarm()
        await repo.upsert(record)
        await repo.resolve(record.alarm_key, datetime.now(timezone.utc))

        result = await repo.resolve(record.alarm_key, datetime.now(timezone.utc))
        assert result is False

    async def test_get_active_alarms(self):
        """get_active_alarms 只回傳 ACTIVE 狀態"""
        repo = InMemoryAlarmRepository()
        r1 = _make_alarm(device_id="d1", alarm_code="A1")
        r2 = _make_alarm(device_id="d2", alarm_code="A2")
        await repo.upsert(r1)
        await repo.upsert(r2)
        await repo.resolve(r1.alarm_key, datetime.now(timezone.utc))

        active = await repo.get_active_alarms()
        assert len(active) == 1
        assert active[0].device_id == "d2"

    async def test_get_active_by_device(self):
        """get_active_by_device 正確過濾設備"""
        repo = InMemoryAlarmRepository()
        r1 = _make_alarm(device_id="d1", alarm_code="A1")
        r2 = _make_alarm(device_id="d1", alarm_code="A2")
        r3 = _make_alarm(device_id="d2", alarm_code="A3")
        await repo.upsert(r1)
        await repo.upsert(r2)
        await repo.upsert(r3)

        d1_alarms = await repo.get_active_by_device("d1")
        assert len(d1_alarms) == 2
        assert all(a.device_id == "d1" for a in d1_alarms)

    async def test_get_active_by_device_empty(self):
        """get_active_by_device 無告警時回傳空列表"""
        repo = InMemoryAlarmRepository()
        assert await repo.get_active_by_device("no_device") == []

    async def test_clear(self):
        """clear 清除所有記錄"""
        repo = InMemoryAlarmRepository()
        await repo.upsert(_make_alarm())
        repo.clear()
        assert repo.get_all_records() == {}

    async def test_get_all_records(self):
        """get_all_records 回傳所有記錄（含 RESOLVED）"""
        repo = InMemoryAlarmRepository()
        r1 = _make_alarm(alarm_code="X1")
        r2 = _make_alarm(alarm_code="X2")
        await repo.upsert(r1)
        await repo.upsert(r2)
        await repo.resolve(r1.alarm_key, datetime.now(timezone.utc))

        all_records = repo.get_all_records()
        assert len(all_records) == 2

    async def test_health_check(self):
        """health_check 回傳 True"""
        repo = InMemoryAlarmRepository()
        assert await repo.health_check() is True
