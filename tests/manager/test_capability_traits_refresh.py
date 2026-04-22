# =============== Manager - Capability Traits Dynamic Refresh 測試 ===============
#
# 驗證 UnifiedDeviceManager 訂閱 device 的 capability 變更事件，
# 自動呼叫 DeviceRegistry.refresh_capability_traits 同步 cap: trait 索引。

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from csp_lib.equipment.device.events import EVENT_CAPABILITY_ADDED, EVENT_CAPABILITY_REMOVED
from csp_lib.manager.unified import UnifiedConfig, UnifiedDeviceManager


class _FakeRegistry:
    """最小 DeviceRegistry stub，只追蹤 refresh_capability_traits 呼叫次數。"""

    def __init__(self) -> None:
        self.registered: list[str] = []
        self.unregistered: list[str] = []
        self.refreshed: list[str] = []
        self.raise_key_error_on_refresh = False

    def register(self, device, traits=None, metadata=None) -> None:  # type: ignore[no-untyped-def]
        self.registered.append(device.device_id)

    def unregister(self, device_id: str) -> None:
        self.unregistered.append(device_id)

    def refresh_capability_traits(self, device_id: str) -> None:
        if self.raise_key_error_on_refresh:
            raise KeyError(device_id)
        self.refreshed.append(device_id)


def _make_event_capable_device(device_id: str = "dev1") -> MagicMock:
    """建立支援 ``on`` 事件訂閱的 mock device。handlers 保留以便測試觸發。"""
    dev = MagicMock()
    dev.device_id = device_id

    handlers: dict[str, list] = {}

    def _register(event: str, handler):  # type: ignore[no-untyped-def]
        handlers.setdefault(event, []).append(handler)

        def _unsub():
            if handler in handlers.get(event, []):
                handlers[event].remove(handler)

        return _unsub

    dev.on = MagicMock(side_effect=_register)
    dev._handlers = handlers  # type: ignore[attr-defined]
    return dev


class TestCapabilityRefreshSubscription:
    """Register 時訂閱 capability 事件；觸發時 registry.refresh_capability_traits 被呼叫。"""

    def test_register_subscribes_capability_events(self):
        reg = _FakeRegistry()
        mgr = UnifiedDeviceManager(UnifiedConfig(device_registry=reg))  # type: ignore[arg-type]

        dev = _make_event_capable_device("dev1")
        mgr.register(dev)

        # on() 被呼叫兩次（ADDED + REMOVED）
        assert dev.on.call_count == 2
        subscribed_events = {call.args[0] for call in dev.on.call_args_list}
        assert subscribed_events == {EVENT_CAPABILITY_ADDED, EVENT_CAPABILITY_REMOVED}

    def test_register_triggers_initial_refresh(self):
        """register() 本身會呼叫一次 refresh_capability_traits 讓既有 capabilities 立即索引。"""
        reg = _FakeRegistry()
        mgr = UnifiedDeviceManager(UnifiedConfig(device_registry=reg))  # type: ignore[arg-type]

        dev = _make_event_capable_device("dev1")
        mgr.register(dev)

        assert reg.refreshed == ["dev1"]

    async def test_capability_added_event_triggers_refresh(self):
        reg = _FakeRegistry()
        mgr = UnifiedDeviceManager(UnifiedConfig(device_registry=reg))  # type: ignore[arg-type]

        dev = _make_event_capable_device("dev1")
        mgr.register(dev)
        # 初始 refresh 已記 1 次；再觸發事件應再多 1 次
        refresh_count_before = len(reg.refreshed)

        handler = dev._handlers[EVENT_CAPABILITY_ADDED][0]
        await handler({"capability_name": "pq_control"})

        assert len(reg.refreshed) == refresh_count_before + 1
        assert reg.refreshed[-1] == "dev1"

    async def test_capability_removed_event_triggers_refresh(self):
        reg = _FakeRegistry()
        mgr = UnifiedDeviceManager(UnifiedConfig(device_registry=reg))  # type: ignore[arg-type]

        dev = _make_event_capable_device("dev1")
        mgr.register(dev)
        refresh_count_before = len(reg.refreshed)

        handler = dev._handlers[EVENT_CAPABILITY_REMOVED][0]
        await handler({"capability_name": "qv_control"})

        assert len(reg.refreshed) == refresh_count_before + 1
        assert reg.refreshed[-1] == "dev1"

    async def test_refresh_key_error_suppressed(self):
        """device 已從 registry unregister 但事件在排隊 → KeyError 吞掉不影響其他流程。"""
        reg = _FakeRegistry()
        reg.raise_key_error_on_refresh = True
        mgr = UnifiedDeviceManager(UnifiedConfig(device_registry=reg))  # type: ignore[arg-type]

        dev = _make_event_capable_device("dev1")
        mgr.register(dev)

        handler = dev._handlers[EVENT_CAPABILITY_ADDED][0]
        # 不該 raise
        await handler({})

        assert reg.refreshed == []  # 沒有進入正常路徑


class TestCapabilityRefreshUnregister:
    """Unregister 時應清理 capability 訂閱，避免 event handler leak。"""

    async def test_unregister_cleans_up_capability_subscriptions(self):
        reg = _FakeRegistry()
        mgr = UnifiedDeviceManager(UnifiedConfig(device_registry=reg))  # type: ignore[arg-type]

        dev = _make_event_capable_device("dev1")
        dev.connect = AsyncMock()
        dev.disconnect = AsyncMock()
        dev.start = AsyncMock()
        dev.stop = AsyncMock()

        mgr.register(dev)
        assert len(dev._handlers[EVENT_CAPABILITY_ADDED]) == 1
        assert len(dev._handlers[EVENT_CAPABILITY_REMOVED]) == 1

        await mgr.unregister("dev1")

        # handlers 已被清空（unsubscribe 被呼叫）
        assert len(dev._handlers[EVENT_CAPABILITY_ADDED]) == 0
        assert len(dev._handlers[EVENT_CAPABILITY_REMOVED]) == 0


class TestNoRegistryFallback:
    """UnifiedConfig 未配置 device_registry 時，capability refresh 完全 no-op（不訂閱）。"""

    def test_no_registry_means_no_subscription(self):
        mgr = UnifiedDeviceManager(UnifiedConfig())

        dev = _make_event_capable_device("dev1")
        mgr.register(dev)

        # on() 完全不被呼叫（因為 registry 是 None）
        dev.on.assert_not_called()


class TestDeviceWithoutOnMethod:
    """Device 不支援事件訂閱（無 on method）→ 跳過 dynamic refresh 但 register 仍成功。"""

    def test_register_succeeds_even_without_on_method(self):
        reg = _FakeRegistry()
        mgr = UnifiedDeviceManager(UnifiedConfig(device_registry=reg))  # type: ignore[arg-type]

        # Device 有 lifecycle methods（符合 DeviceManager 要求）但缺 on（模擬
        # DerivedDevice / RemoteSnapshotDevice 未實作事件訂閱的情境）
        dev = MagicMock(spec=["device_id", "connect", "disconnect", "start", "stop"])
        dev.device_id = "dev_no_events"
        dev.connect = AsyncMock()
        dev.disconnect = AsyncMock()
        dev.start = AsyncMock()
        dev.stop = AsyncMock()

        # 不該 raise
        mgr.register(dev)

        assert "dev_no_events" in reg.registered
        assert "dev_no_events" not in mgr._capability_unsubscribes  # type: ignore[operator]


class TestReregisterIdempotent:
    """Re-register 同一 device 不會累積 subscribe callbacks。"""

    def test_reregister_clears_old_subscriptions(self):
        reg = _FakeRegistry()
        mgr = UnifiedDeviceManager(UnifiedConfig(device_registry=reg))  # type: ignore[arg-type]

        dev = _make_event_capable_device("dev1")
        # 直接呼叫 _subscribe_capability_refresh 兩次（模擬 idempotent）
        mgr._subscribe_capability_refresh(dev)  # type: ignore[attr-defined]
        mgr._subscribe_capability_refresh(dev)  # type: ignore[attr-defined]

        # 每次訂閱 2 個事件；第二次會先清掉第一次 → 手上只剩 2 個（而非 4 個）
        assert len(dev._handlers[EVENT_CAPABILITY_ADDED]) == 1
        assert len(dev._handlers[EVENT_CAPABILITY_REMOVED]) == 1
