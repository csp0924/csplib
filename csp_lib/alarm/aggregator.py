# =============== Alarm - Aggregator ===============
#
# In-process 的事件驅動告警聚合器：
#   - 多個 source（device / watchdog / 自訂）可獨立註冊 active 狀態
#   - 聚合語義為 OR：任一 source active 即整體 active
#   - 狀態變化時觸發同步 on_change callback
#
# Thread safety：
#   - 使用 threading.Lock 保護 _active_sources 與 _observers
#   - callback 在 lock 釋放後以快照呼叫，避免 reentrant deadlock

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from csp_lib.core import get_logger

from .protocols import AlarmChangeCallback, WatchdogProtocol

logger = get_logger(__name__)


class AlarmAggregator:
    """In-process 事件驅動告警聚合器。

    多個告警來源可獨立登記 active 狀態，聚合器以 OR 語義維護整體旗標；
    整體旗標由 ``False → True`` 或 ``True → False`` 時，通知所有
    ``on_change`` 訂閱者。

    使用場景：
        * 日本 demo：任一設備告警 / gateway watchdog timeout → publish
          到 Redis channel → 其他 node 立即停機
        * 本機 in-process：策略鎖定、Modbus gateway coil 同步等

    Thread safety:
        使用 ``threading.Lock`` 保護內部狀態；callback 在 lock 釋放後
        以快照呼叫，避免 observer 回呼期間重進 aggregator 造成死鎖。

    Example:
        >>> agg = AlarmAggregator()
        >>> agg.bind_device(device)  # 任一 alarm_triggered → source active
        >>> agg.bind_watchdog(wd, name="gateway_wd")
        >>> agg.on_change(lambda active: print(f"aggregated={active}"))
    """

    def __init__(self) -> None:
        self._active_sources: set[str] = set()
        self._observers: list[AlarmChangeCallback] = []
        self._lock = threading.Lock()
        # 每個 bound source 的 unbinder（呼叫以解除原 event hook）
        self._unbinders: dict[str, Callable[[], None]] = {}

    # ---------- 綁定 ----------

    def bind_device(self, device: Any, *, name: str | None = None) -> None:
        """訂閱 ``device.on("alarm_triggered" / "alarm_cleared")``。

        - ``name`` 省略時使用 ``device.device_id``
        - device 層級的 source active 定義為：
          「該 device 有 ≥1 個 alarm_triggered 尚未 cleared」
          本 MVP 用簡單 bool 實作（觸發→True；解除→False）；
          如未來需要精確計數可在此擴充每 alarm_event 加減計數。
        - 同名重綁會先 ``unbind`` 舊 source。

        Args:
            device: 任何提供 ``on(event, handler)`` 且回傳 unbind 函式的物件
                （例如 :class:`csp_lib.equipment.device.AsyncModbusDevice`）。
            name: source 名稱；省略用 ``device.device_id``。

        Raises:
            ValueError: 若無法決定 source 名稱（device 無 ``device_id`` 且未指定 ``name``）。
        """
        source_name = name if name is not None else getattr(device, "device_id", None)
        if not source_name:
            raise ValueError("bind_device 需提供 name 或 device 需有 device_id 屬性")

        # 同名重綁：先解除舊的
        if source_name in self._unbinders:
            self.unbind(source_name)

        async def _on_triggered(_payload: Any) -> None:
            self._set_source_active(source_name, True)

        async def _on_cleared(_payload: Any) -> None:
            self._set_source_active(source_name, False)

        # device.on() 回傳 unbind 函式
        unbind_trig = device.on("alarm_triggered", _on_triggered)
        unbind_clr = device.on("alarm_cleared", _on_cleared)

        def _combined_unbind() -> None:
            try:
                unbind_trig()
            except Exception:  # noqa: BLE001 - 解綁失敗不可中斷流程
                logger.opt(exception=True).warning(
                    "AlarmAggregator: failed to unbind alarm_triggered for source {}", source_name
                )
            try:
                unbind_clr()
            except Exception:  # noqa: BLE001
                logger.opt(exception=True).warning(
                    "AlarmAggregator: failed to unbind alarm_cleared for source {}", source_name
                )

        self._unbinders[source_name] = _combined_unbind
        logger.debug("AlarmAggregator: bound device source '{}'", source_name)

    def bind_watchdog(self, watchdog: WatchdogProtocol, *, name: str) -> None:
        """訂閱 watchdog 的 timeout / recover 事件。

        ``CommunicationWatchdog.on_timeout`` / ``on_recover`` 均接受
        ``Callable[[], Awaitable[None]]``，且 **沒有 unbind 機制**；
        我們透過 captured flag 實作軟取消：``unbind()`` 後 callback
        仍會被呼叫但會 early return，不影響 aggregator 狀態。

        Args:
            watchdog: 符合 :class:`WatchdogProtocol` 的物件。
            name: source 名稱（watchdog 無 device_id 概念，必填）。

        Raises:
            ValueError: 若 ``name`` 為空字串。
        """
        if not name:
            raise ValueError("bind_watchdog 需提供非空的 name")

        # 同名重綁：先解除舊的
        if name in self._unbinders:
            self.unbind(name)

        # 用可變容器實作軟取消（watchdog 無原生 unbind）
        alive = {"value": True}

        async def _on_timeout() -> None:
            if not alive["value"]:
                return
            self._set_source_active(name, True)

        async def _on_recover() -> None:
            if not alive["value"]:
                return
            self._set_source_active(name, False)

        watchdog.on_timeout(_on_timeout)
        watchdog.on_recover(_on_recover)

        def _soft_unbind() -> None:
            alive["value"] = False

        self._unbinders[name] = _soft_unbind
        logger.debug("AlarmAggregator: bound watchdog source '{}'", name)

    def unbind(self, name: str) -> None:
        """移除指定 source。

        步驟：
            1. 呼叫 unbinder 解除原 event hook（device 為硬 unbind；
               watchdog 為軟 unbind）
            2. 若該 source 曾 active，從 ``_active_sources`` 移除；
               若此操作讓整體旗標 ``True → False`` 則觸發 ``on_change``。

        Args:
            name: 要移除的 source 名稱；不存在時靜默忽略。
        """
        unbinder = self._unbinders.pop(name, None)
        if unbinder is not None:
            try:
                unbinder()
            except Exception:  # noqa: BLE001
                logger.opt(exception=True).warning("AlarmAggregator: unbinder for '{}' raised", name)
        # 移除該 source 的 active 狀態（可能觸發聚合旗標變化）
        self._set_source_active(name, False)

    # ---------- Observer ----------

    def on_change(self, callback: AlarmChangeCallback) -> None:
        """註冊聚合旗標變化 callback。

        Callback 在聚合旗標 ``False → True`` 或 ``True → False`` 時觸發，
        參數為新的旗標值。Callback 為 **同步** 函式；若需發起 async I/O，
        請於 callback 內使用 ``asyncio.create_task``。

        Args:
            callback: 同步 callback，簽名 ``(active: bool) -> None``。
        """
        with self._lock:
            self._observers.append(callback)

    def remove_observer(self, callback: AlarmChangeCallback) -> None:
        """移除已註冊的 callback；不存在則靜默忽略。"""
        with self._lock:
            try:
                self._observers.remove(callback)
            except ValueError:
                pass

    # ---------- 狀態查詢 ----------

    @property
    def active(self) -> bool:
        """當前聚合旗標。任一 source active → ``True``；全部 cleared → ``False``。"""
        with self._lock:
            return bool(self._active_sources)

    @property
    def active_sources(self) -> set[str]:
        """當前 active 的 source 名稱快照（copy，不共享底層 set）。"""
        with self._lock:
            return set(self._active_sources)

    # ---------- 外部：直接注入狀態（for RedisAlarmSource 等自訂來源） ----------

    def mark_source(self, name: str, active: bool) -> None:
        """外部直接設定某 source 的 active 狀態。

        使用場景：
            * :class:`RedisAlarmSource` 從遠端 channel 收到事件後注入
            * 使用者自訂 source 沒有 device.on() 或 watchdog.on_timeout() 介面

        Args:
            name: source 名稱。
            active: True=active；False=cleared。
        """
        self._set_source_active(name, active)

    # ---------- 內部：狀態變更入口 ----------

    def _set_source_active(self, name: str, active: bool) -> None:
        """單一 source 狀態變更入口。

        聚合旗標若因此變化，在鎖外以快照呼叫所有 observers。
        callback 例外僅 log warning，不影響其他 observer 或狀態。
        """
        with self._lock:
            was_aggregated = bool(self._active_sources)
            if active:
                self._active_sources.add(name)
            else:
                self._active_sources.discard(name)
            is_aggregated = bool(self._active_sources)
            # 僅當聚合旗標真的變化時才快照 observers
            observers_snapshot = list(self._observers) if was_aggregated != is_aggregated else []

        if not observers_snapshot:
            return

        for cb in observers_snapshot:
            try:
                cb(is_aggregated)
            except Exception:  # noqa: BLE001 - observer 失敗不應影響其他 observer
                logger.opt(exception=True).warning("AlarmAggregator: observer raised (active={})", is_aggregated)


__all__ = ["AlarmAggregator"]
