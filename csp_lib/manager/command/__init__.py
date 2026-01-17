# =============== Manager - Command ===============
#
# 寫入指令管理模組
#
# 提供外部寫入指令管理功能：
#   - Schema: WriteCommand, ActionCommand, CommandRecord, CommandSource, CommandStatus
#   - Repository: CommandRepository (Protocol), MongoCommandRepository (實作)
#   - Manager: WriteCommandManager (指令執行與審計)
#   - Adapters: RedisCommandAdapter (Redis Pub/Sub 適配器)
#
# 使用方式：
#   1. 建立 MongoCommandRepository
#   2. 建立 WriteCommandManager 並注入 Repository
#   3. 註冊設備 (register_device)
#   4. 直接呼叫 execute() 或透過 RedisCommandAdapter 接收外部指令

from .adapters.redis import CommandResult, RedisCommandAdapter
from .manager import WriteCommandManager
from .repository import CommandRepository, MongoCommandRepository
from .schema import ActionCommand, CommandRecord, CommandSource, CommandStatus, WriteCommand

__all__ = [
    # Schema
    "WriteCommand",
    "ActionCommand",
    "CommandRecord",
    "CommandSource",
    "CommandStatus",
    # Repository
    "CommandRepository",
    "MongoCommandRepository",
    # Manager
    "WriteCommandManager",
    # Adapters
    "RedisCommandAdapter",
    "CommandResult",
]
