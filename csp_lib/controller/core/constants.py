"""StrategyContext.extra 常用 key 常數（internal，不匯出到 public API）"""

from __future__ import annotations

# 設備讀值
CTX_FREQUENCY: str = "frequency"
CTX_VOLTAGE: str = "voltage"
CTX_METER_POWER: str = "meter_power"

# 排程/控制
CTX_SCHEDULE_P: str = "schedule_p"
CTX_DT: str = "dt"

# 系統狀態
CTX_SYSTEM_ALARM: str = "system_alarm"

# 級聯
CTX_REMAINING_S_KVA: str = "remaining_s_kva"
