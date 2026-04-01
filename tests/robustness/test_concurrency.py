"""Concurrency stress tests for DeviceRegistry, DeviceEventEmitter, and RuntimeParameters.

Uses threading.Thread for true-threaded scenarios and asyncio.gather for async scenarios.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

from csp_lib.core.runtime_params import RuntimeParameters
from csp_lib.equipment.device.events import DeviceEventEmitter
from csp_lib.integration.registry import DeviceRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_device(device_id: str) -> MagicMock:
    """Create a minimal mock device with required attributes."""
    dev = MagicMock()
    dev.device_id = device_id
    dev.is_responsive = True
    dev.has_capability = MagicMock(return_value=False)
    return dev


# ---------------------------------------------------------------------------
# DeviceRegistry — threaded concurrency
# ---------------------------------------------------------------------------


class TestDeviceRegistryConcurrency:
    """Concurrent register/get_devices_by_trait must not raise RuntimeError."""

    def test_concurrent_register_and_query(self) -> None:
        """10 threads register devices while 10 threads query by trait — no crash."""
        registry = DeviceRegistry()
        errors: list[Exception] = []
        barrier = threading.Barrier(20)

        def register_worker(idx: int) -> None:
            try:
                barrier.wait(timeout=5)
                dev = _make_mock_device(f"dev_{idx}")
                registry.register(dev, traits=["pcs"])
            except ValueError:
                pass  # duplicate device_id is expected if indices collide
            except Exception as exc:
                errors.append(exc)

        def query_worker() -> None:
            try:
                barrier.wait(timeout=5)
                for _ in range(50):
                    registry.get_devices_by_trait("pcs")
                    _ = registry.all_devices
            except Exception as exc:
                errors.append(exc)

        threads: list[threading.Thread] = []
        for i in range(10):
            threads.append(threading.Thread(target=register_worker, args=(i,)))
        for _ in range(10):
            threads.append(threading.Thread(target=query_worker))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert all(not t.is_alive() for t in threads), "Some threads did not finish in time"

        assert errors == [], f"Concurrent access raised: {errors}"

    def test_concurrent_register_and_unregister(self) -> None:
        """Concurrent register + unregister should not corrupt internal state."""
        registry = DeviceRegistry()
        errors: list[Exception] = []
        barrier = threading.Barrier(20)

        # Pre-register half the devices
        for i in range(10):
            registry.register(_make_mock_device(f"pre_{i}"), traits=["meter"])

        def register_worker(idx: int) -> None:
            try:
                barrier.wait(timeout=5)
                dev = _make_mock_device(f"new_{idx}")
                registry.register(dev, traits=["meter"])
            except ValueError:
                pass
            except Exception as exc:
                errors.append(exc)

        def unregister_worker(idx: int) -> None:
            try:
                barrier.wait(timeout=5)
                registry.unregister(f"pre_{idx}")
            except Exception as exc:
                errors.append(exc)

        threads: list[threading.Thread] = []
        for i in range(10):
            threads.append(threading.Thread(target=register_worker, args=(i,)))
        for i in range(10):
            threads.append(threading.Thread(target=unregister_worker, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert all(not t.is_alive() for t in threads), "Some threads did not finish in time"

        assert errors == [], f"Concurrent access raised: {errors}"


# ---------------------------------------------------------------------------
# DeviceEventEmitter — async concurrency
# ---------------------------------------------------------------------------


class TestDeviceEventEmitterConcurrency:
    """Concurrent on() + emit() must not crash or lose events."""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_concurrent_emit_and_on(self) -> None:
        """Concurrent emit + on registration should not crash."""
        emitter = DeviceEventEmitter(max_queue_size=10000)
        await emitter.start()
        received: list[int] = []

        async def handler(payload: int) -> None:
            received.append(payload)

        # Register a base handler so emit actually enqueues
        emitter.on("test", handler)

        async def emitter_task() -> None:
            for i in range(100):
                emitter.emit("test", i)

        async def register_task() -> None:
            for _ in range(50):
                emitter.on("test", handler)
                await asyncio.sleep(0)

        await asyncio.gather(emitter_task(), register_task())

        # Give worker time to drain
        await asyncio.sleep(0.5)
        await emitter.stop()

        # We should have received events (exact count depends on timing)
        assert len(received) > 0

    @pytest.mark.asyncio
    async def test_emit_without_start_does_not_crash(self) -> None:
        """Emitting without starting the worker should not raise (and not enqueue)."""
        emitter = DeviceEventEmitter()

        async def handler(payload: object) -> None:
            pass  # pragma: no cover

        emitter.on("test", handler)
        emitter.emit("test", "data")
        # emit() skips enqueue when not running — this is by design (graceful stop feature)
        assert emitter.queue_size == 0

    @pytest.mark.asyncio
    async def test_emit_no_listeners_skips_enqueue(self) -> None:
        """Emitting to an event with no listeners should not enqueue."""
        emitter = DeviceEventEmitter()
        emitter.emit("no_listeners", "data")
        assert emitter.queue_size == 0


# ---------------------------------------------------------------------------
# RuntimeParameters — threaded concurrency
# ---------------------------------------------------------------------------


class TestRuntimeParametersConcurrency:
    """Concurrent set/get/snapshot must produce consistent state."""

    def test_concurrent_set_get_snapshot(self) -> None:
        """10 writers + 10 readers + snapshot must not raise or corrupt state."""
        params = RuntimeParameters(counter=0)
        errors: list[Exception] = []
        barrier = threading.Barrier(21)

        def writer(idx: int) -> None:
            try:
                barrier.wait(timeout=5)
                for i in range(100):
                    params.set(f"key_{idx}", i)
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                barrier.wait(timeout=5)
                for _ in range(100):
                    params.get("counter")
                    params.snapshot()
            except Exception as exc:
                errors.append(exc)

        threads: list[threading.Thread] = []
        for i in range(10):
            threads.append(threading.Thread(target=writer, args=(i,)))
        for _ in range(10):
            threads.append(threading.Thread(target=reader))
        threads.append(threading.Thread(target=reader))  # extra reader to make 21

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert all(not t.is_alive() for t in threads), "Some threads did not finish in time"

        assert errors == [], f"Concurrent access raised: {errors}"

    def test_concurrent_update_and_snapshot_consistency(self) -> None:
        """Snapshot returns a consistent (non-torn) view of parameters."""
        params = RuntimeParameters(a=0, b=0)
        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def writer() -> None:
            try:
                barrier.wait(timeout=5)
                for i in range(500):
                    # Always update a and b together to the same value
                    params.update({"a": i, "b": i})
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                barrier.wait(timeout=5)
                for _ in range(500):
                    snap = params.snapshot()
                    # Within a snapshot, a and b should be equal
                    # (update is atomic within lock)
                    if snap["a"] != snap["b"]:
                        errors.append(ValueError(f"Torn read: a={snap['a']}, b={snap['b']}"))
            except Exception as exc:
                errors.append(exc)

        t_w = threading.Thread(target=writer)
        t_r = threading.Thread(target=reader)
        t_w.start()
        t_r.start()
        t_w.join(timeout=10)
        t_r.join(timeout=10)
        assert not t_w.is_alive(), "writer thread did not finish in time"
        assert not t_r.is_alive(), "reader thread did not finish in time"

        assert errors == [], f"Concurrent access raised: {errors}"

    def test_observer_called_on_concurrent_set(self) -> None:
        """Observer callbacks fire correctly under concurrent writes."""
        params = RuntimeParameters()
        changes: list[str] = []
        lock = threading.Lock()

        def observer(key: str, old: object, new: object) -> None:
            with lock:
                changes.append(key)

        params.on_change(observer)

        def writer(idx: int) -> None:
            for i in range(50):
                params.set(f"k{idx}", i)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert all(not t.is_alive() for t in threads), "Some threads did not finish in time"

        # Each writer writes 50 times; first write always triggers (old=None != 0)
        # Subsequent writes trigger when value changes
        assert len(changes) > 0
