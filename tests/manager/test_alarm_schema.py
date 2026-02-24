# =============== Manager Alarm Tests - Schema ===============
#
# AlarmRecord Schema 單元測試
#
# 測試覆蓋：
# - AlarmRecord 建立與預設值
# - to_document / from_document 轉換
# - make_key 生成邏輯
# - Enum 類型測試

from __future__ import annotations

from datetime import datetime, timezone

from csp_lib.equipment.alarm import AlarmLevel
from csp_lib.manager.alarm.schema import AlarmRecord, AlarmStatus, AlarmType


class TestAlarmType:
    """AlarmType Enum 測試"""

    def test_values(self):
        """驗證 Enum 值"""
        assert AlarmType.DISCONNECT.value == "disconnect"
        assert AlarmType.DEVICE_ALARM.value == "device_alarm"


class TestAlarmStatus:
    """AlarmStatus Enum 測試"""

    def test_values(self):
        """驗證 Enum 值"""
        assert AlarmStatus.ACTIVE.value == "active"
        assert AlarmStatus.RESOLVED.value == "resolved"


class TestAlarmRecord:
    """AlarmRecord 測試"""

    def test_create_with_defaults(self):
        """使用預設值建立 AlarmRecord"""
        record = AlarmRecord(
            alarm_key="device_001:disconnect:DISCONNECT",
            device_id="device_001",
            alarm_type=AlarmType.DISCONNECT,
        )

        assert record.alarm_key == "device_001:disconnect:DISCONNECT"
        assert record.device_id == "device_001"
        assert record.alarm_type == AlarmType.DISCONNECT
        assert record.alarm_code == ""  # 預設值
        assert record.name == ""  # 預設值
        assert record.level == AlarmLevel.INFO  # 預設值
        assert record.description == ""  # 預設值
        assert record.occurred_at is None  # 預設值
        assert record.resolved_at is None  # 預設值
        assert record.status == AlarmStatus.ACTIVE  # 預設值

    def test_create_full(self):
        """建立完整 AlarmRecord"""
        now = datetime.now(timezone.utc)
        record = AlarmRecord(
            alarm_key="device_001:device_alarm:OVER_TEMP",
            device_id="device_001",
            alarm_type=AlarmType.DEVICE_ALARM,
            alarm_code="OVER_TEMP",
            name="溫度過高",
            level=AlarmLevel.WARNING,
            description="設備溫度超過閾值",
            occurred_at=now,
            resolved_at=None,
            status=AlarmStatus.ACTIVE,
        )

        assert record.alarm_key == "device_001:device_alarm:OVER_TEMP"
        assert record.alarm_code == "OVER_TEMP"
        assert record.name == "溫度過高"
        assert record.level == AlarmLevel.WARNING
        assert record.description == "設備溫度超過閾值"
        assert record.occurred_at == now

    def test_make_key(self):
        """make_key 應生成正確格式"""
        key = AlarmRecord.make_key("device_001", AlarmType.DISCONNECT, "DISCONNECT")
        assert key == "device_001:disconnect:DISCONNECT"

        key2 = AlarmRecord.make_key("pcs_002", AlarmType.DEVICE_ALARM, "OVER_CURRENT")
        assert key2 == "pcs_002:device_alarm:OVER_CURRENT"

    def test_to_document(self):
        """to_document 應正確轉換為 dict"""
        now = datetime.now(timezone.utc)
        record = AlarmRecord(
            alarm_key="device_001:disconnect:DISCONNECT",
            device_id="device_001",
            alarm_type=AlarmType.DISCONNECT,
            alarm_code="DISCONNECT",
            name="設備斷線",
            level=AlarmLevel.WARNING,
            description="連線逾時",
            occurred_at=now,
            resolved_at=None,
            status=AlarmStatus.ACTIVE,
        )

        doc = record.to_document()

        assert doc["alarm_key"] == "device_001:disconnect:DISCONNECT"
        assert doc["device_id"] == "device_001"
        assert doc["alarm_type"] == "disconnect"  # Enum.value
        assert doc["alarm_code"] == "DISCONNECT"
        assert doc["name"] == "設備斷線"
        assert doc["level"] == 2  # AlarmLevel.WARNING.value
        assert doc["description"] == "連線逾時"
        assert doc["occurred_at"] == now
        assert doc["resolved_at"] is None
        assert doc["status"] == "active"  # Enum.value

    def test_from_document(self):
        """from_document 應正確從 dict 建立"""
        now = datetime.now(timezone.utc)
        doc = {
            "_id": "mongo_object_id_12345",  # MongoDB 自動產生
            "alarm_key": "device_001:disconnect:DISCONNECT",
            "device_id": "device_001",
            "alarm_type": "disconnect",
            "alarm_code": "DISCONNECT",
            "name": "設備斷線",
            "level": 2,
            "description": "連線逾時",
            "occurred_at": now,
            "resolved_at": None,
            "status": "active",
        }

        record = AlarmRecord.from_document(doc)

        assert record.alarm_key == "device_001:disconnect:DISCONNECT"
        assert record.device_id == "device_001"
        assert record.alarm_type == AlarmType.DISCONNECT
        assert record.alarm_code == "DISCONNECT"
        assert record.name == "設備斷線"
        assert record.level == AlarmLevel.WARNING
        assert record.description == "連線逾時"
        assert record.occurred_at == now
        assert record.resolved_at is None
        assert record.status == AlarmStatus.ACTIVE

    def test_from_document_removes_id(self):
        """from_document 應移除 _id 欄位"""
        doc = {
            "_id": "mongo_object_id",
            "alarm_key": "test",
            "device_id": "test",
            "alarm_type": "disconnect",
            "alarm_code": "",
            "name": "",
            "level": 1,
            "description": "",
            "occurred_at": None,
            "resolved_at": None,
            "status": "active",
        }

        # 不應拋出 TypeError: __init__() got an unexpected keyword argument '_id'
        record = AlarmRecord.from_document(doc)
        assert record.alarm_key == "test"

    def test_roundtrip(self):
        """to_document / from_document 循環轉換應保持一致"""
        now = datetime.now(timezone.utc)
        original = AlarmRecord(
            alarm_key="device_001:device_alarm:OVER_TEMP",
            device_id="device_001",
            alarm_type=AlarmType.DEVICE_ALARM,
            alarm_code="OVER_TEMP",
            name="溫度過高",
            level=AlarmLevel.ALARM,
            description="測試告警",
            occurred_at=now,
            resolved_at=None,
            status=AlarmStatus.ACTIVE,
        )

        doc = original.to_document()
        restored = AlarmRecord.from_document(doc)

        assert restored.alarm_key == original.alarm_key
        assert restored.device_id == original.device_id
        assert restored.alarm_type == original.alarm_type
        assert restored.alarm_code == original.alarm_code
        assert restored.name == original.name
        assert restored.level == original.level
        assert restored.description == original.description
        assert restored.occurred_at == original.occurred_at
        assert restored.resolved_at == original.resolved_at
        assert restored.status == original.status
