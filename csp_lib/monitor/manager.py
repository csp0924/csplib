# =============== Monitor - Manager ===============
#
# 系統監控管理器
#
# 整合指標收集、告警評估、Redis 發布、通知分發：
#   - SystemMonitor: 系統監控器（AsyncLifecycleMixin）

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable

from csp_lib.core import AsyncLifecycleMixin, HealthCheckable, HealthReport, HealthStatus, get_logger
from csp_lib.equipment.alarm.definition import AlarmLevel
from csp_lib.equipment.alarm.state import AlarmEvent, AlarmEventType
from csp_lib.manager.alarm.schema import AlarmRecord, AlarmType
from csp_lib.notification import Notification, NotificationEvent

from .alarm import SystemAlarmEvaluator
from .collector import ModuleHealthCollector, ModuleHealthSnapshot, SystemMetrics, SystemMetricsCollector
from .config import DistributedMonitorConfig, MonitorConfig
from .publisher import RedisMonitorPublisher

if TYPE_CHECKING:
    from csp_lib.notification import NotificationSender
    from csp_lib.redis import RedisClient

logger = get_logger(__name__)


class SystemMonitor(AsyncLifecycleMixin):
    """
    系統監控器

    定期收集系統指標與模組健康狀態，評估告警，
    發布至 Redis 並透過 NotificationDispatcher 發送通知。

    Example:
        ```python
        monitor = SystemMonitor(redis_client=redis, dispatcher=dispatcher)
        monitor.register_module("device_manager", device_manager)
        monitor.register_check("redis", redis_health_check)

        async with monitor:
            ...  # 監控自動運行
        ```
    """

    def __init__(
        self,
        redis_client: RedisClient | None = None,
        dispatcher: NotificationSender | None = None,
        config: MonitorConfig | None = None,
        distributed_config: DistributedMonitorConfig | None = None,
    ) -> None:
        self._config = config or MonitorConfig()
        self._distributed_config = distributed_config
        self._metrics_collector = SystemMetricsCollector(self._config)
        self._health_collector = ModuleHealthCollector()
        self._alarm_evaluator = SystemAlarmEvaluator(self._config)
        self._publisher = (
            RedisMonitorPublisher(redis_client, self._config, distributed_config) if redis_client else None
        )
        self._dispatcher = dispatcher
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._last_metrics: SystemMetrics | None = None
        self._last_module_health: ModuleHealthSnapshot | None = None

    def register_module(self, name: str, module: HealthCheckable) -> None:
        """註冊 HealthCheckable 模組"""
        self._health_collector.register_module(name, module)

    def register_check(self, name: str, check_fn: Callable[[], HealthReport]) -> None:
        """註冊自訂健康檢查函式"""
        self._health_collector.register_check(name, check_fn)

    # ================ Lifecycle ================

    async def _on_start(self) -> None:
        """啟動監控迴圈"""
        self._running = True

        if self._publisher and self._distributed_config:
            try:
                await self._publisher.register_node()
            except Exception:
                logger.warning("節點註冊失敗", exc_info=True)

        self._task = asyncio.create_task(self._run_loop())
        logger.info("系統監控器已啟動")

    async def _on_stop(self) -> None:
        """停止監控迴圈"""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("系統監控器已停止")

    async def _run_loop(self) -> None:
        """定期執行收集 → 評估 → 發布"""
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("系統監控迴圈異常", exc_info=True)

            try:
                await asyncio.sleep(self._config.interval_seconds)
            except asyncio.CancelledError:
                raise

    async def _tick(self) -> None:
        """單次監控週期"""
        # 1. 收集系統指標
        metrics = self._metrics_collector.collect()
        self._last_metrics = metrics

        # 2. 評估告警
        events = self._alarm_evaluator.evaluate(metrics)

        # 3. 發布指標至 Redis
        if self._publisher:
            try:
                await self._publisher.publish_metrics(metrics)
            except Exception:
                logger.warning("Redis 發布指標失敗", exc_info=True)

        # 4. 處理告警事件
        for event in events:
            # 發布告警至 Redis
            if self._publisher:
                try:
                    await self._publisher.publish_alarm_event(event)
                except Exception:
                    logger.warning("Redis 發布告警失敗", exc_info=True)

            # 發送通知
            await self._notify_alarm(event)

        # 5. 收集模組健康
        if self._config.enable_module_health:
            snapshot = self._health_collector.collect()
            self._last_module_health = snapshot

            if self._publisher:
                try:
                    await self._publisher.publish_module_health(snapshot)
                except Exception:
                    logger.warning("Redis 發布模組健康失敗", exc_info=True)

    async def _notify_alarm(self, event: AlarmEvent) -> None:
        """透過 NotificationDispatcher 發送告警通知"""
        if not self._dispatcher:
            return

        alarm = event.alarm
        if event.event_type == AlarmEventType.TRIGGERED:
            notif_event = NotificationEvent.TRIGGERED
        else:
            notif_event = NotificationEvent.RESOLVED

        alarm_key = AlarmRecord.make_key("__system__", AlarmType.DEVICE_ALARM, alarm.code)
        event_label = "觸發" if notif_event == NotificationEvent.TRIGGERED else "解除"
        title = f"[{AlarmLevel(alarm.level).name}] __system__ {alarm.name} - {event_label}"

        notification = Notification(
            title=title,
            body=alarm.description or alarm.name,
            level=alarm.level,
            device_id="__system__",
            alarm_key=alarm_key,
            event=notif_event,
            occurred_at=event.timestamp,
        )

        try:
            await self._dispatcher.dispatch(notification)
        except Exception:
            logger.warning("通知分發失敗", exc_info=True)

    # ================ HealthCheckable ================

    def health(self) -> HealthReport:
        """回報監控器自身健康狀態"""
        if not self._running:
            return HealthReport(
                status=HealthStatus.UNHEALTHY,
                component="SystemMonitor",
                message="監控器未運行",
            )

        active = self._alarm_evaluator.active_alarms
        if active:
            return HealthReport(
                status=HealthStatus.DEGRADED,
                component="SystemMonitor",
                message=f"活躍告警: {', '.join(active)}",
                details={"active_alarms": active},
            )

        return HealthReport(
            status=HealthStatus.HEALTHY,
            component="SystemMonitor",
            message="正常運行",
        )

    # ================ Properties ================

    @property
    def is_running(self) -> bool:
        """是否正在運行"""
        return self._running

    @property
    def active_alarms(self) -> list[str]:
        """活躍告警代碼列表"""
        return self._alarm_evaluator.active_alarms

    @property
    def last_metrics(self) -> SystemMetrics | None:
        """最近一次系統指標"""
        return self._last_metrics

    @property
    def last_module_health(self) -> ModuleHealthSnapshot | None:
        """最近一次模組健康快照"""
        return self._last_module_health


__all__ = [
    "SystemMonitor",
]
