"""P1 robustness improvement tests.

Covers:
  1. DeviceRegistry threading.Lock concurrency safety
  2. DeviceEventEmitter graceful drain on stop
  3. DeviceManager duplicate device_id registration check
  4. DeviceConfig reconnect_interval validation
  5. WriteRule min/max cross-validation
"""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.equipment.device.events import EVENT_CONNECTED, DeviceEventEmitter
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.manager.device import DeviceManager
from csp_lib.modbus_gateway.config import WriteRule

# ======================== Helpers ========================


def _make_device(device_id: str, responsive: bool = True) -> MagicMock:
    """Create a minimal device mock for registry/manager tests."""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=False)
    type(dev).is_connected = PropertyMock(return_value=True)
    type(dev).capabilities = PropertyMock(return_value={})
    dev.has_capability = MagicMock(return_value=False)
    dev.write = AsyncMock()
    return dev


# ======================== 1. DeviceRegistry Concurrency ========================


class TestDeviceRegistryConcurrency:
    """Verify that DeviceRegistry's threading.Lock protects against concurrent access."""

    def test_concurrent_register_and_query(self):
        """Concurrent register + get_devices_by_trait should not crash.

        Hammers register and query from separate threads to surface any missing
        lock protection or dict-mutation-during-iteration errors.
        """
        registry = DeviceRegistry()
        num_devices = 200
        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def register_worker():
            try:
                barrier.wait(timeout=5)
                for i in range(num_devices):
                    dev = _make_device(f"reg_dev_{i}")
                    registry.register(dev, traits=["power"])
            except Exception as e:
                errors.append(e)

        def query_worker():
            try:
                barrier.wait(timeout=5)
                for _ in range(num_devices):
                    registry.get_devices_by_trait("power")
                    _ = registry.all_devices
                    _ = registry.all_traits
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=register_worker)
        t2 = threading.Thread(target=query_worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        assert not t1.is_alive(), "register_worker thread did not finish in time"
        assert not t2.is_alive(), "query_worker thread did not finish in time"

        assert not errors, f"Concurrent access raised: {errors}"
        assert len(registry) == num_devices

    def test_concurrent_register_and_unregister(self):
        """Concurrent register + unregister on disjoint IDs should not crash."""
        registry = DeviceRegistry()
        errors: list[Exception] = []

        # Pre-register devices that will be unregistered
        for i in range(100):
            registry.register(_make_device(f"unreg_{i}"), traits=["old"])

        barrier = threading.Barrier(2)

        def register_worker():
            try:
                barrier.wait(timeout=5)
                for i in range(100):
                    registry.register(_make_device(f"new_{i}"), traits=["new"])
            except Exception as e:
                errors.append(e)

        def unregister_worker():
            try:
                barrier.wait(timeout=5)
                for i in range(100):
                    registry.unregister(f"unreg_{i}")
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=register_worker)
        t2 = threading.Thread(target=unregister_worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        assert not t1.is_alive(), "register_worker thread did not finish in time"
        assert not t2.is_alive(), "unregister_worker thread did not finish in time"

        assert not errors, f"Concurrent access raised: {errors}"
        # All "unreg_" removed, all "new_" added
        assert len(registry) == 100

    def test_concurrent_add_trait_and_query(self):
        """Concurrent add_trait + get_devices_by_trait should not crash."""
        registry = DeviceRegistry()
        errors: list[Exception] = []

        # Pre-register devices
        for i in range(50):
            registry.register(_make_device(f"dev_{i}"))

        barrier = threading.Barrier(2)

        def trait_worker():
            try:
                barrier.wait(timeout=5)
                for i in range(50):
                    registry.add_trait(f"dev_{i}", "sensor")
            except Exception as e:
                errors.append(e)

        def query_worker():
            try:
                barrier.wait(timeout=5)
                for _ in range(100):
                    registry.get_devices_by_trait("sensor")
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=trait_worker)
        t2 = threading.Thread(target=query_worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        assert not t1.is_alive(), "trait_worker thread did not finish in time"
        assert not t2.is_alive(), "query_worker thread did not finish in time"

        assert not errors, f"Concurrent access raised: {errors}"


class TestDeviceRegistryDuplicateRegistration:
    """Verify that DeviceRegistry rejects duplicate device_id."""

    def test_register_duplicate_raises(self):
        """Registering the same device_id twice raises ValueError."""
        registry = DeviceRegistry()
        dev = _make_device("dup_001")
        registry.register(dev, traits=["inverter"])

        with pytest.raises(ValueError, match="already registered"):
            registry.register(_make_device("dup_001"))

    def test_register_duplicate_does_not_corrupt_state(self):
        """Failed duplicate registration should not alter existing entry."""
        registry = DeviceRegistry()
        dev_original = _make_device("dup_002")
        registry.register(dev_original, traits=["pcs"])

        with pytest.raises(ValueError):
            registry.register(_make_device("dup_002"), traits=["meter"])

        # Original entry and traits preserved
        assert registry.get_device("dup_002") is dev_original
        assert "pcs" in registry.get_traits("dup_002")
        assert "meter" not in registry.get_traits("dup_002")

    def test_register_after_unregister_ok(self):
        """Registering a device_id that was previously unregistered should succeed."""
        registry = DeviceRegistry()
        registry.register(_make_device("recycle_001"))
        registry.unregister("recycle_001")

        new_dev = _make_device("recycle_001")
        registry.register(new_dev, traits=["recycled"])
        assert registry.get_device("recycle_001") is new_dev


# ======================== 2. DeviceEventEmitter Graceful Stop ========================


class TestDeviceEventEmitterGracefulDrain:
    """Verify that stop() drains the queue before cancelling the worker."""

    @pytest.mark.asyncio
    async def test_stop_drains_pending_events(self):
        """Events enqueued before stop() should be delivered to handlers.

        Pre-fix: stop() would cancel the worker immediately, losing events.
        Post-fix: stop() sends a sentinel and waits for the worker to drain.
        """
        emitter = DeviceEventEmitter()
        received: list[int] = []

        async def handler(payload):
            received.append(payload)

        emitter.on(EVENT_CONNECTED, handler)
        await emitter.start()

        # Enqueue several events
        for i in range(5):
            emitter.emit(EVENT_CONNECTED, i)

        # Stop should drain all pending events
        await emitter.stop()

        assert received == [0, 1, 2, 3, 4], f"Not all events drained: {received}"

    @pytest.mark.asyncio
    async def test_emit_skips_after_stop(self):
        """emit() after stop() should silently discard (not raise or enqueue)."""
        emitter = DeviceEventEmitter()
        handler = AsyncMock()
        emitter.on(EVENT_CONNECTED, handler)

        await emitter.start()
        await emitter.stop()

        # Emit after stop - should not raise
        emitter.emit(EVENT_CONNECTED, "late_event")

        # Queue should remain empty (not running)
        assert emitter.queue_size == 0

    @pytest.mark.asyncio
    async def test_emit_skips_when_no_listeners(self):
        """emit() with no registered handlers should not enqueue."""
        emitter = DeviceEventEmitter()
        await emitter.start()
        try:
            emitter.emit(EVENT_CONNECTED, "orphan")
            assert emitter.queue_size == 0
        finally:
            await emitter.stop()

    @pytest.mark.asyncio
    async def test_handler_list_copied_during_iteration(self):
        """Adding a handler during iteration should not cause errors.

        Post-fix: _process_event copies the handler list before iterating.
        """
        emitter = DeviceEventEmitter()
        call_order: list[str] = []

        async def handler_a(payload):
            call_order.append("a")
            # Dynamically add a new handler during processing
            emitter.on(EVENT_CONNECTED, late_handler)

        async def late_handler(payload):
            call_order.append("late")

        emitter.on(EVENT_CONNECTED, handler_a)

        # emit_await processes synchronously, exercising the copy-on-iterate path
        await emitter.emit_await(EVENT_CONNECTED, None)

        # Only handler_a should have run (late_handler was added after copy)
        assert call_order == ["a"]

        # On second emit, both should run
        call_order.clear()
        await emitter.emit_await(EVENT_CONNECTED, None)
        assert "a" in call_order
        assert "late" in call_order


# ======================== 3. DeviceManager Duplicate Registration ========================


class TestDeviceDuplicateRegistration:
    """Verify that DeviceManager rejects duplicate device_id in register and register_group."""

    def test_register_duplicate_standalone_raises(self):
        """Registering the same device_id twice via register() raises ValueError."""
        manager = DeviceManager()
        dev1 = MagicMock()
        dev1.device_id = "pcs_001"
        dev2 = MagicMock()
        dev2.device_id = "pcs_001"

        manager.register(dev1)

        with pytest.raises(ValueError, match="already registered"):
            manager.register(dev2)

    def test_register_group_duplicate_within_group_raises(self):
        """Group containing duplicate device_id raises ValueError."""
        manager = DeviceManager()
        dev1 = MagicMock()
        dev1.device_id = "rtu_001"
        dev2 = MagicMock()
        dev2.device_id = "rtu_001"  # Same ID

        with pytest.raises(ValueError, match="already registered"):
            manager.register_group([dev1, dev2])

    def test_register_group_duplicate_across_existing_raises(self):
        """Group with device_id already registered as standalone raises ValueError."""
        manager = DeviceManager()
        standalone = MagicMock()
        standalone.device_id = "shared_001"
        manager.register(standalone)

        group_dev = MagicMock()
        group_dev.device_id = "shared_001"

        with pytest.raises(ValueError, match="already registered"):
            manager.register_group([group_dev])

    def test_register_group_duplicate_across_groups_raises(self):
        """Device_id in a new group that already exists in a previous group raises ValueError."""
        manager = DeviceManager()
        dev_a = MagicMock()
        dev_a.device_id = "meter_001"
        dev_b = MagicMock()
        dev_b.device_id = "meter_002"
        manager.register_group([dev_a, dev_b])

        dev_c = MagicMock()
        dev_c.device_id = "meter_001"  # Collision with first group

        with pytest.raises(ValueError, match="already registered"):
            manager.register_group([dev_c])

    def test_register_distinct_ids_ok(self):
        """Registering devices with distinct IDs should not raise."""
        manager = DeviceManager()
        for i in range(5):
            dev = MagicMock()
            dev.device_id = f"ok_{i}"
            manager.register(dev)

        assert manager.standalone_count == 5


# ======================== 4. DeviceConfig reconnect_interval Validation ========================


class TestDeviceConfigReconnectInterval:
    """Verify that DeviceConfig rejects reconnect_interval <= 0."""

    def test_reconnect_interval_zero_raises(self):
        """reconnect_interval=0 should raise ConfigurationError."""
        with pytest.raises(ConfigurationError, match="reconnect_interval"):
            DeviceConfig(device_id="dev1", reconnect_interval=0)

    def test_reconnect_interval_negative_raises(self):
        """reconnect_interval=-1 should raise ConfigurationError."""
        with pytest.raises(ConfigurationError, match="reconnect_interval"):
            DeviceConfig(device_id="dev1", reconnect_interval=-1)

    def test_reconnect_interval_negative_float_raises(self):
        """reconnect_interval=-0.5 should raise ConfigurationError."""
        with pytest.raises(ConfigurationError, match="reconnect_interval"):
            DeviceConfig(device_id="dev1", reconnect_interval=-0.5)

    def test_reconnect_interval_positive_ok(self):
        """reconnect_interval > 0 should succeed."""
        config = DeviceConfig(device_id="dev1", reconnect_interval=3.0)
        assert config.reconnect_interval == 3.0

    def test_reconnect_interval_small_positive_ok(self):
        """reconnect_interval=0.1 (small but positive) should succeed."""
        config = DeviceConfig(device_id="dev1", reconnect_interval=0.1)
        assert config.reconnect_interval == 0.1

    def test_reconnect_interval_default_ok(self):
        """Default reconnect_interval (5.0) should succeed."""
        config = DeviceConfig(device_id="dev1")
        assert config.reconnect_interval == 5.0


# ======================== 5. WriteRule min/max Cross-Validation ========================


class TestWriteRuleValidation:
    """Verify that WriteRule rejects min_value > max_value."""

    def test_min_greater_than_max_raises(self):
        """min_value=100, max_value=50 should raise ValueError."""
        with pytest.raises(ValueError, match="min_value must be <= max_value"):
            WriteRule(register_name="p_ref", min_value=100, max_value=50)

    def test_min_greater_than_max_negative_range_raises(self):
        """min_value=-10, max_value=-20 should raise ValueError."""
        with pytest.raises(ValueError, match="min_value must be <= max_value"):
            WriteRule(register_name="q_ref", min_value=-10, max_value=-20)

    def test_min_equals_max_ok(self):
        """min_value == max_value should be allowed (single valid value)."""
        rule = WriteRule(register_name="fixed_val", min_value=50.0, max_value=50.0)
        assert rule.min_value == 50.0
        assert rule.max_value == 50.0

    def test_min_less_than_max_ok(self):
        """Normal range min_value < max_value should succeed."""
        rule = WriteRule(register_name="p_ref", min_value=0, max_value=1000)
        assert rule.min_value == 0
        assert rule.max_value == 1000

    def test_both_none_ok(self):
        """Both min_value and max_value as None should succeed (no bounds)."""
        rule = WriteRule(register_name="unrestricted")
        assert rule.min_value is None
        assert rule.max_value is None

    def test_only_min_set_ok(self):
        """Only min_value set (max_value=None) should succeed."""
        rule = WriteRule(register_name="lower_bound", min_value=0)
        assert rule.min_value == 0
        assert rule.max_value is None

    def test_only_max_set_ok(self):
        """Only max_value set (min_value=None) should succeed."""
        rule = WriteRule(register_name="upper_bound", max_value=500)
        assert rule.min_value is None
        assert rule.max_value == 500
