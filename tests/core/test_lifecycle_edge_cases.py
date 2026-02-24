import pytest

from csp_lib.core.lifecycle import AsyncLifecycleMixin


class TrackingService(AsyncLifecycleMixin):
    def __init__(self):
        self.start_count = 0
        self.stop_count = 0

    async def _on_start(self):
        self.start_count += 1

    async def _on_stop(self):
        self.stop_count += 1


class FailingStartService(AsyncLifecycleMixin):
    async def _on_start(self):
        raise RuntimeError("start failed")


class FailingStopService(AsyncLifecycleMixin):
    async def _on_stop(self):
        raise RuntimeError("stop failed")


class TestLifecycleEdgeCases:
    @pytest.mark.asyncio
    async def test_double_start_calls_on_start_twice(self):
        svc = TrackingService()
        await svc.start()
        await svc.start()
        assert svc.start_count == 2

    @pytest.mark.asyncio
    async def test_double_stop_calls_on_stop_twice(self):
        svc = TrackingService()
        await svc.start()
        await svc.stop()
        await svc.stop()
        assert svc.stop_count == 2

    @pytest.mark.asyncio
    async def test_start_failure_still_allows_stop(self):
        svc = FailingStartService()
        with pytest.raises(RuntimeError):
            await svc.start()
        # stop should still work
        await svc.stop()

    @pytest.mark.asyncio
    async def test_context_manager_stop_failure_propagates(self):
        svc = FailingStopService()
        with pytest.raises(RuntimeError, match="stop failed"):
            async with svc:
                pass
