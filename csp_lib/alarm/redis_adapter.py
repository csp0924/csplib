# =============== Alarm - Redis Adapter ===============
#
# 將 AlarmAggregator 與 Redis pub/sub 串接：
#   - RedisAlarmPublisher: 訂閱 aggregator.on_change → publish 到 channel
#   - RedisAlarmSource:    訂閱 channel → 將遠端事件注入 aggregator
#
# 需要 ``csp_lib[redis]`` extra；import redis.asyncio 延遲到 ctor。

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from csp_lib.core import AsyncLifecycleMixin, get_logger

from .aggregator import AlarmAggregator

if TYPE_CHECKING:
    # 僅供 static type checker 使用；執行期不 import 避免強制依賴 redis extra
    from redis.asyncio import Redis


logger = get_logger(__name__)


# ---------- 型別別名 ----------

PayloadBuilder = Callable[[bool, AlarmAggregator], dict[str, Any]]
EventParser = Callable[[dict[str, Any]], bool]


def _default_payload_builder(active: bool, aggregator: AlarmAggregator) -> dict[str, Any]:
    """預設 payload schema（相容日本 demo）。

    Returns:
        ``{"type": "aggregated_alarm", "active": bool, "sources": [...], "timestamp": "..."}``
    """
    return {
        "type": "aggregated_alarm",
        "active": active,
        "sources": sorted(aggregator.active_sources),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _default_event_parser(payload: dict[str, Any]) -> bool:
    """預設 event parser：讀取 ``payload["active"]``，預設 False。"""
    return bool(payload.get("active", False))


def _require_redis_extra() -> None:
    """驗證 redis.asyncio 可 import；否則拋 ImportError 給 ctor。"""
    try:
        import redis.asyncio  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "csp_lib.alarm.redis_adapter requires 'csp_lib[redis]'. Install with: pip install \"csp0924_lib[redis]\""
        ) from exc


# ---------- Publisher ----------


class RedisAlarmPublisher(AsyncLifecycleMixin):
    """訂閱 ``AlarmAggregator.on_change`` → publish 到 Redis channel。

    AlarmAggregator 的 observer 是 **同步** callback；為避免阻塞 event loop，
    publisher 在 observer 內以 ``asyncio.create_task`` 排程 async publish，
    並保留 task 參照避免被 GC。

    Payload schema（預設）::

        {
            "type": "aggregated_alarm",
            "active": true,
            "sources": ["dev_a", "gateway_wd"],
            "timestamp": "2026-04-17T00:00:00+00:00"
        }

    Publish 失敗僅 log warning，不 raise，避免影響其他 observer。

    Args:
        aggregator: 要訂閱的 :class:`AlarmAggregator`。
        redis_client: ``redis.asyncio.Redis`` 實例（已連線）。
        channel: Redis channel 名稱。
        payload_builder: 自訂 payload 構造器；省略用預設 schema。
    """

    def __init__(
        self,
        aggregator: AlarmAggregator,
        redis_client: Redis,
        channel: str,
        payload_builder: PayloadBuilder | None = None,
    ) -> None:
        _require_redis_extra()
        self._aggregator = aggregator
        self._redis = redis_client
        self._channel = channel
        self._payload_builder = payload_builder or _default_payload_builder
        self._observer: Callable[[bool], None] | None = None
        self._pending_tasks: set[asyncio.Task[None]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def _on_start(self) -> None:
        """註冊 observer；記住 event loop 以便同步 callback 內排程 async task。"""
        self._loop = asyncio.get_running_loop()

        def _observer(active: bool) -> None:
            # observer 是同步的，在任何 thread 都可能被呼叫（aggregator lock 釋放後）
            loop = self._loop
            if loop is None:
                return
            try:
                # 若 observer 在 loop thread 上執行，直接 create_task；否則 threadsafe
                task: asyncio.Task[None]
                try:
                    running = asyncio.get_running_loop()
                except RuntimeError:
                    running = None
                if running is loop:
                    task = loop.create_task(self._publish(active))
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
                else:
                    # 來自其他 thread：用 run_coroutine_threadsafe
                    asyncio.run_coroutine_threadsafe(self._publish(active), loop)
            except Exception:  # noqa: BLE001
                logger.opt(exception=True).warning(
                    "RedisAlarmPublisher: failed to schedule publish for active={}", active
                )

        self._observer = _observer
        self._aggregator.on_change(_observer)
        logger.info("RedisAlarmPublisher started (channel={})", self._channel)

    async def _on_stop(self) -> None:
        """解除 observer 並等待進行中的 publish task 結束。"""
        if self._observer is not None:
            self._aggregator.remove_observer(self._observer)
            self._observer = None
        # 等待尚未完成的 publish task
        if self._pending_tasks:
            pending = list(self._pending_tasks)
            try:
                await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("RedisAlarmPublisher: pending publish tasks timed out on stop")
            self._pending_tasks.clear()
        self._loop = None
        logger.info("RedisAlarmPublisher stopped (channel={})", self._channel)

    async def _publish(self, active: bool) -> None:
        """實際 publish；失敗僅 log warning。"""
        try:
            payload = self._payload_builder(active, self._aggregator)
            message = json.dumps(payload, ensure_ascii=False)
            await self._redis.publish(self._channel, message)
            logger.debug("RedisAlarmPublisher: published to '{}' (active={})", self._channel, active)
        except Exception:  # noqa: BLE001 - publish 失敗不 raise
            logger.opt(exception=True).warning(
                "RedisAlarmPublisher: publish failed (channel={}, active={})", self._channel, active
            )


# ---------- Source ----------


class RedisAlarmSource(AsyncLifecycleMixin):
    """訂閱 Redis channel → 將遠端事件注入 :class:`AlarmAggregator`。

    Source 名稱固定為 ``name``，aggregator 會以此名稱追蹤 active 狀態。

    Args:
        aggregator: 事件注入目標。
        redis_client: ``redis.asyncio.Redis`` 實例。
        channel: 要訂閱的 Redis channel。
        name: source 名稱（對應 aggregator 內部狀態 key）。
        event_parser: 自訂 parser，從 JSON payload 解出 ``active: bool``；
            省略用預設 parser（讀取 ``payload["active"]``）。
    """

    def __init__(
        self,
        aggregator: AlarmAggregator,
        redis_client: Redis,
        channel: str,
        name: str,
        event_parser: EventParser | None = None,
    ) -> None:
        _require_redis_extra()
        if not name:
            raise ValueError("RedisAlarmSource 需提供非空的 name")
        self._aggregator = aggregator
        self._redis = redis_client
        self._channel = channel
        self._name = name
        self._event_parser = event_parser or _default_event_parser
        self._task: asyncio.Task[None] | None = None
        self._pubsub: Any = None  # redis.asyncio.client.PubSub（延遲建立）

    async def _on_start(self) -> None:
        """建立 pubsub 訂閱並啟動背景 task。"""
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self._channel)
        self._task = asyncio.create_task(self._listen_loop(), name=f"alarm_source_{self._name}")
        logger.info("RedisAlarmSource started (channel={}, name={})", self._channel, self._name)

    async def _on_stop(self) -> None:
        """取消 task 並關閉 pubsub。"""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe(self._channel)
                await self._pubsub.aclose()
            except Exception:  # noqa: BLE001
                logger.opt(exception=True).warning(
                    "RedisAlarmSource: failed to close pubsub (channel={})", self._channel
                )
            self._pubsub = None
        # 清除該 source 的 active 狀態
        self._aggregator.unbind(self._name)
        logger.info("RedisAlarmSource stopped (channel={}, name={})", self._channel, self._name)

    async def _listen_loop(self) -> None:
        """背景 listen loop：解析每筆訊息並注入 aggregator。"""
        try:
            async for message in self._pubsub.listen():
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue
                raw = message.get("data")
                if raw is None:
                    continue
                try:
                    if isinstance(raw, (bytes, bytearray)):
                        raw = raw.decode("utf-8")
                    payload = json.loads(raw)
                    active = self._event_parser(payload)
                except Exception:  # noqa: BLE001 - 解析失敗不應中斷 listen loop
                    logger.opt(exception=True).warning(
                        "RedisAlarmSource: failed to parse message (channel={})", self._channel
                    )
                    continue
                # 注入 aggregator
                self._aggregator.mark_source(self._name, active)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            logger.opt(exception=True).warning(
                "RedisAlarmSource: listen loop terminated unexpectedly (channel={})", self._channel
            )


__all__ = [
    "RedisAlarmPublisher",
    "RedisAlarmSource",
]
