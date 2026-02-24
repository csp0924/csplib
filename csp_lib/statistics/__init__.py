# =============== Statistics ===============
#
# 能源統計模組
#
# 提供設備能耗統計與功率加總功能：
#   - config: 統計配置定義
#   - tracker: 設備能源追蹤器
#   - engine: 統計計算引擎
#   - manager: 事件驅動統計管理器（需要 csp_lib[mongo] 依賴）
#
# 使用方式：
#   1. 建立 StatisticsConfig 配置
#   2. 建立 StatisticsManager 並注入 MongoBatchUploader / DeviceRegistry
#   3. 呼叫 subscribe() 訂閱 AsyncModbusDevice
#   4. 讀取資料自動計算統計並上傳至 MongoDB

from .config import DeviceMeterType, MetricDefinition, PowerSumDefinition, StatisticsConfig
from .engine import PowerSumRecord, StatisticsEngine
from .tracker import DeviceEnergyTracker, IntervalAccumulator, IntervalRecord

__all__ = [
    # Config
    "DeviceMeterType",
    "MetricDefinition",
    "PowerSumDefinition",
    "StatisticsConfig",
    # Tracker
    "IntervalRecord",
    "IntervalAccumulator",
    "DeviceEnergyTracker",
    # Engine
    "PowerSumRecord",
    "StatisticsEngine",
]

# Manager 依賴 csp_lib.manager.base（需要 optional deps），延遲匯入
try:
    from .manager import StatisticsManager  # noqa: F401

    __all__.append("StatisticsManager")
except ImportError:
    pass
