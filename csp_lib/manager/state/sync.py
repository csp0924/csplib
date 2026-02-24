# =============== Manager State - Sync ===============
#
# 狀態同步管理器
#
# 提供設備狀態自動同步至 Redis 功能：
#   - StateSyncManager: 訂閱設備事件並同步至 Redis + Pub/Sub
#
# 設計模式：
#   - 觀察者模式：訂閱 AsyncModbusDevice 的多種事件
#   - 事件驅動：讀取/連線/告警 → Redis Hash/String/Set + Pub/Sub

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable

from csp_lib.core import get_logger
from csp_lib.equipment.device.events import (
    EVENT_ALARM_CLEARED,
    EVENT_ALARM_TRIGGERED,
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    ConnectedPayload,
    DeviceAlarmPayload,
    DisconnectPayload,
    ReadCompletePayload,
)
from csp_lib.manager.base import DeviceEventSubscriber
from csp_lib.manager.state.config import StateSyncConfig

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice
    from csp_lib.redis import RedisClient

logger = get_logger(__name__)


class StateSyncManager(DeviceEventSubscriber):
    """
    狀態同步管理器

    自動將設備狀態同步至 Redis，並透過 Pub/Sub 通知前端。

    職責：
        1. 訂閱 AsyncModbusDevice 的事件
        2. read_complete → 更新 Hash + 發布 data channel
        3. connected/disconnected → 更新 online 狀態 + 發布 status channel
        4. alarm_triggered/cleared → 更新 alarms Set + 發布 alarm channel

    Redis Key 結構：
        - device:{device_id}:state - Hash，存放所有點位最新值（有 TTL）
        - device:{device_id}:online - String，"1" 或 "0"（有 TTL）
        - device:{device_id}:alarms - Set，活躍告警 codes（無 TTL）

    Pub/Sub Channel：
        - channel:device:{device_id}:data - 資料更新
        - channel:device:{device_id}:status - 連線狀態
        - channel:device:{device_id}:alarm - 告警事件

    Example:
        ```python
        from csp_lib.redis import RedisClient
        from csp_lib.manager.state import StateSyncManager

        redis_client = RedisClient("redis://localhost:6379")
        await redis_client.connect()

        state_manager = StateSyncManager(redis_client, state_ttl=60, online_ttl=60)
        state_manager.subscribe(device)

        # 設備事件自動同步至 Redis + Pub/Sub
        ```
    """

    def __init__(
        self,
        redis_client: RedisClient,
        config: StateSyncConfig | None = None,
        state_ttl: int | None = None,
        online_ttl: int | None = None,
    ) -> None:
        """
        初始化狀態同步管理器

        Args:
            redis_client: Redis 客戶端實例
            config: 狀態同步配置（優先使用）
            state_ttl: 設備狀態 Hash TTL（秒），config 為 None 時使用
            online_ttl: 連線狀態 TTL（秒），config 為 None 時使用
        """
        super().__init__()
        self._redis = redis_client
        if config is None:
            config = StateSyncConfig(
                state_ttl=state_ttl if state_ttl is not None else 60,
                online_ttl=online_ttl if online_ttl is not None else 60,
            )
        self._config = config
        self._state_ttl = self._config.state_ttl
        self._online_ttl = self._config.online_ttl

    # ================ Key/Channel 命名 ================

    @staticmethod
    def _state_key(device_id: str) -> str:
        """設備狀態 Hash key"""
        return f"device:{device_id}:state"

    @staticmethod
    def _online_key(device_id: str) -> str:
        """設備連線狀態 key"""
        return f"device:{device_id}:online"

    @staticmethod
    def _alarms_key(device_id: str) -> str:
        """設備活躍告警 Set key"""
        return f"device:{device_id}:alarms"

    @staticmethod
    def _data_channel(device_id: str) -> str:
        """資料更新 channel"""
        return f"channel:device:{device_id}:data"

    @staticmethod
    def _status_channel(device_id: str) -> str:
        """連線狀態 channel"""
        return f"channel:device:{device_id}:status"

    @staticmethod
    def _alarm_channel(device_id: str) -> str:
        """告警事件 channel"""
        return f"channel:device:{device_id}:alarm"

    # ================ 訂閱管理 ================

    def _register_events(self, device: AsyncModbusDevice) -> list[Callable[[], None]]:
        """註冊設備的 read/連線/告警事件"""
        logger.info(f"狀態同步管理器已訂閱設備: {device.device_id}")
        return [
            device.on(EVENT_READ_COMPLETE, self._on_read_complete),
            device.on(EVENT_CONNECTED, self._on_connected),
            device.on(EVENT_DISCONNECTED, self._on_disconnected),
            device.on(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered),
            device.on(EVENT_ALARM_CLEARED, self._on_alarm_cleared),
        ]

    def _on_unsubscribe(self, device_id: str) -> None:
        logger.info(f"狀態同步管理器已取消訂閱設備: {device_id}")

    # ================ 事件處理器 ================

    async def _on_read_complete(self, payload: ReadCompletePayload) -> None:
        """
        處理讀取完成事件

        更新 Redis Hash 並發布至 data channel。

        Args:
            payload: 讀取完成事件資料
        """
        device_id = payload.device_id
        state_key = self._state_key(device_id)
        online_key = self._online_key(device_id)

        # 更新 Hash + TTL
        await self._redis.hset(state_key, payload.values)
        await self._redis.expire(state_key, self._state_ttl)

        # 同時刷新 online 狀態（作為心跳）
        await self._redis.set(online_key, "1", ex=self._online_ttl)

        # 發布至 channel
        message = json.dumps(
            {
                "timestamp": payload.timestamp.isoformat(),
                "values": payload.values,
            },
            default=str,
        )
        await self._redis.publish(self._data_channel(device_id), message)

    async def _on_connected(self, payload: ConnectedPayload) -> None:
        """
        處理連線成功事件

        設定 online=1 並發布至 status channel。

        Args:
            payload: 連線事件資料
        """
        device_id = payload.device_id

        # 更新連線狀態 + TTL
        await self._redis.set(self._online_key(device_id), "1", ex=self._online_ttl)

        # 發布至 channel
        message = json.dumps(
            {
                "online": True,
                "timestamp": payload.timestamp.isoformat(),
            }
        )
        await self._redis.publish(self._status_channel(device_id), message)
        logger.debug(f"狀態同步: 設備 {device_id} 已連線")

    async def _on_disconnected(self, payload: DisconnectPayload) -> None:
        """
        處理斷線事件

        設定 online=0 並發布至 status channel。

        Args:
            payload: 斷線事件資料
        """
        device_id = payload.device_id

        # 更新連線狀態
        await self._redis.set(self._online_key(device_id), "0")

        # 發布至 channel
        message = json.dumps(
            {
                "online": False,
                "reason": payload.reason,
                "timestamp": payload.timestamp.isoformat(),
            }
        )
        await self._redis.publish(self._status_channel(device_id), message)
        logger.debug(f"狀態同步: 設備 {device_id} 已斷線")

    async def _on_alarm_triggered(self, payload: DeviceAlarmPayload) -> None:
        """
        處理告警觸發事件

        新增告警至 Set 並發布至 alarm channel。

        Args:
            payload: 告警事件資料
        """
        device_id = payload.device_id
        alarm = payload.alarm_event.alarm

        # 新增至 Set
        await self._redis.sadd(self._alarms_key(device_id), alarm.code)

        # 發布至 channel
        message = json.dumps(
            {
                "type": "triggered",
                "alarm": {
                    "code": alarm.code,
                    "name": alarm.name,
                    "level": alarm.level.value,
                    "description": alarm.description,
                },
                "timestamp": payload.timestamp.isoformat(),
            }
        )
        await self._redis.publish(self._alarm_channel(device_id), message)
        logger.debug(f"狀態同步: 設備 {device_id} 告警觸發 {alarm.code}")

    async def _on_alarm_cleared(self, payload: DeviceAlarmPayload) -> None:
        """
        處理告警解除事件

        從 Set 移除告警並發布至 alarm channel。

        Args:
            payload: 告警事件資料
        """
        device_id = payload.device_id
        alarm = payload.alarm_event.alarm

        # 從 Set 移除
        await self._redis.srem(self._alarms_key(device_id), alarm.code)

        # 發布至 channel
        message = json.dumps(
            {
                "type": "cleared",
                "alarm": {
                    "code": alarm.code,
                    "name": alarm.name,
                },
                "timestamp": payload.timestamp.isoformat(),
            }
        )
        await self._redis.publish(self._alarm_channel(device_id), message)
        logger.debug(f"狀態同步: 設備 {device_id} 告警解除 {alarm.code}")


__all__ = [
    "StateSyncManager",
]
