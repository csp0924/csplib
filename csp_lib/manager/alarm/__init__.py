# =============== Manager - Alarm ===============
#
# 告警管理模組
#
# 提供告警持久化與管理功能：
#   - Schema: AlarmType, AlarmStatus, AlarmRecord
#   - Repository: AlarmRepository (Protocol), MongoAlarmRepository (實作)
#   - Persistence: AlarmPersistenceManager (事件驅動持久化)
#
# 使用方式：
#   1. 建立 Repository 實例（如 MongoAlarmRepository）
#   2. 建立 AlarmPersistenceManager 並注入 Repository
#   3. 呼叫 subscribe() 訂閱 AsyncModbusDevice 事件
#   4. 告警將自動持久化至資料庫

from .persistence import AlarmPersistenceManager
from .repository import AlarmRepository, MongoAlarmRepository
from .schema import AlarmRecord, AlarmStatus, AlarmType

__all__ = [
    # Persistence
    "AlarmPersistenceManager",
    # Repository
    "AlarmRepository",
    "MongoAlarmRepository",
    # Schema
    "AlarmRecord",
    "AlarmStatus",
    "AlarmType",
]
