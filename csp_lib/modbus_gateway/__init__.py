# =============== Modbus Gateway Module ===============
#
# Modbus Gateway 模組
#
# 提供 Modbus TCP 閘道伺服器，讓 PCS/BMS 等設備以 Modbus slave
# 身份對外暴露暫存器，供 EMS 或 SCADA 讀寫。
#
# Usage:
#     from csp_lib.modbus_gateway import (
#         # Errors
#         GatewayError,
#         RegisterConflictError,
#         WriteRejectedError,
#         # Config
#         RegisterType,
#         GatewayRegisterDef,
#         WatchdogConfig,
#         GatewayServerConfig,
#         # Protocol
#         WriteValidator,
#         WriteHook,
#         WriteRule,
#         DataSyncSource,
#         UpdateRegisterCallback,
#         # Rules
#         RangeRule,
#         AllowedValuesRule,
#         StepRule,
#         CompositeRule,
#         # Watchdog
#         CommunicationWatchdog,
#         # Validators
#         AddressWhitelistValidator,
#     )

from .config import (
    GatewayRegisterDef,
    GatewayServerConfig,
    RegisterType,
    WatchdogConfig,
    WriteRule,
)
from .errors import (
    GatewayError,
    RegisterConflictError,
    WriteRejectedError,
)
from .hooks import CallbackHook, RedisPublishHook, StatePersistHook
from .protocol import (
    DataSyncSource,
    UpdateRegisterCallback,
    WriteHook,
    WriteValidator,
)
from .register_map import GatewayRegisterMap
from .rules import AllowedValuesRule, CompositeRule, RangeRule, StepRule
from .server import ModbusGatewayServer
from .sync_sources import PollingCallbackSource, RedisSubscriptionSource
from .validators import AddressWhitelistValidator
from .watchdog import CommunicationWatchdog

__all__ = [
    # Errors
    "GatewayError",
    "RegisterConflictError",
    "WriteRejectedError",
    # Config
    "RegisterType",
    "GatewayRegisterDef",
    "WatchdogConfig",
    "GatewayServerConfig",
    # Protocol
    "WriteValidator",
    "WriteHook",
    "WriteRule",
    "DataSyncSource",
    "UpdateRegisterCallback",
    # Rules
    "RangeRule",
    "AllowedValuesRule",
    "StepRule",
    "CompositeRule",
    # Core
    "GatewayRegisterMap",
    "ModbusGatewayServer",
    # Watchdog
    "CommunicationWatchdog",
    # Validators
    "AddressWhitelistValidator",
    # Hooks
    "RedisPublishHook",
    "CallbackHook",
    "StatePersistHook",
    # Sync Sources
    "RedisSubscriptionSource",
    "PollingCallbackSource",
]
