# =============== Integration Distributed Module ===============
#
# 分散式控制模組
#
# 支援多機分散式設備控制架構：
#   - DistributedConfig / RemoteSiteConfig: 分散式配置
#   - DeviceStateSubscriber: 從 Redis 輪詢遠端設備狀態
#   - RemoteCommandRouter: 透過 Redis 發送指令到遠端站台
#   - DistributedController: Controller 端主編排器
#   - RemoteSiteRunner: 遠端站台設備端執行器

from .command_router import RemoteCommandRouter
from .config import DistributedConfig, RemoteSiteConfig
from .controller import DistributedController
from .site_runner import RemoteSiteRunner
from .subscriber import DeviceStateSubscriber

__all__ = [
    # Config
    "DistributedConfig",
    "RemoteSiteConfig",
    # Subscriber
    "DeviceStateSubscriber",
    # Command Router
    "RemoteCommandRouter",
    # Controller
    "DistributedController",
    # Site Runner
    "RemoteSiteRunner",
]
