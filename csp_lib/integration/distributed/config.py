# =============== Integration Distributed - Config ===============
#
# 分散式控制配置
#
# 定義遠端站台與分散式控制器的配置：
#   - RemoteSiteConfig: 單一遠端站台設定
#   - DistributedConfig: 分散式控制器總配置

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RemoteSiteConfig:
    """
    遠端站台配置

    定義一個遠端站台（例如 Computer_1 上的 BMS）的相關設定。

    Attributes:
        site_id: 站台唯一識別碼（例如 "site_bms"）
        device_ids: 此站台上的設備 ID 列表
        command_channel: 指令接收 channel（預設 "channel:commands:{site_id}:write"）
        result_channel: 結果回傳 channel（預設 "channel:commands:{site_id}:result"）
    """

    site_id: str
    device_ids: list[str] = field(default_factory=list)
    command_channel: str | None = None
    result_channel: str | None = None

    @property
    def effective_command_channel(self) -> str:
        """實際使用的指令 channel"""
        return self.command_channel or f"channel:commands:{self.site_id}:write"

    @property
    def effective_result_channel(self) -> str:
        """實際使用的結果 channel"""
        return self.result_channel or f"channel:commands:{self.site_id}:result"


@dataclass(frozen=True)
class DistributedConfig:
    """
    分散式控制器配置

    Attributes:
        sites: 遠端站台配置列表
        trait_device_map: trait -> device_id 列表的映射
        poll_interval: 設備狀態輪詢間隔（秒）
        command_timeout: 指令執行超時（秒）
        system_alarm_on_device_offline: 設備離線時是否觸發 system_alarm
    """

    sites: list[RemoteSiteConfig] = field(default_factory=list)
    trait_device_map: dict[str, list[str]] = field(default_factory=dict)
    poll_interval: float = 1.0
    command_timeout: float = 5.0
    system_alarm_on_device_offline: bool = True

    @property
    def all_device_ids(self) -> list[str]:
        """所有站台的設備 ID 列表"""
        result: list[str] = []
        for site in self.sites:
            result.extend(site.device_ids)
        return result

    @property
    def device_site_map(self) -> dict[str, RemoteSiteConfig]:
        """device_id -> 所屬站台配置的映射"""
        result: dict[str, RemoteSiteConfig] = {}
        for site in self.sites:
            for device_id in site.device_ids:
                result[device_id] = site
        return result


__all__ = [
    "DistributedConfig",
    "RemoteSiteConfig",
]
