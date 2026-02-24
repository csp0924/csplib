# =============== Modbus Server - Public API ===============
#
# Modbus TCP 模擬伺服器模組
#
# 提供設備模擬、系統聯動、告警管理等功能，
# 用於整合測試與設備控制機制驗證。

# Re-export behavior classes
from .behaviors import AlarmBehavior, CurveBehavior, NoiseBehavior, RampBehavior
from .config import (
    AlarmPointConfig,
    AlarmResetMode,
    ControllabilityMode,
    GeneratorSimConfig,
    LoadSimConfig,
    MicrogridConfig,
    PCSSimConfig,
    PowerMeterSimConfig,
    ServerConfig,
    SimulatedDeviceConfig,
    SimulatedPoint,
    SolarSimConfig,
)
from .microgrid import MicrogridSimulator
from .register_block import RegisterBlock
from .server import SimulationServer, SimulatorDataBlock
from .simulator import (
    BaseDeviceSimulator,
    GeneratorSimulator,
    LoadSimulator,
    PCSSimulator,
    PowerMeterSimulator,
    SolarSimulator,
)

__all__ = [
    # Config
    "AlarmPointConfig",
    "AlarmResetMode",
    "ControllabilityMode",
    "GeneratorSimConfig",
    "LoadSimConfig",
    "MicrogridConfig",
    "PCSSimConfig",
    "PowerMeterSimConfig",
    "ServerConfig",
    "SimulatedDeviceConfig",
    "SimulatedPoint",
    "SolarSimConfig",
    # Register
    "RegisterBlock",
    # Server
    "SimulationServer",
    "SimulatorDataBlock",
    # Microgrid
    "MicrogridSimulator",
    # Simulators
    "BaseDeviceSimulator",
    "GeneratorSimulator",
    "LoadSimulator",
    "PCSSimulator",
    "PowerMeterSimulator",
    "SolarSimulator",
    # Behaviors
    "AlarmBehavior",
    "CurveBehavior",
    "NoiseBehavior",
    "RampBehavior",
]
