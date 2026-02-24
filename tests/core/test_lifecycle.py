# =============== Core Tests - Lifecycle ===============
#
# AsyncLifecycleMixin 單元測試

import pytest

from csp_lib.core.lifecycle import AsyncLifecycleMixin


class ConcreteService(AsyncLifecycleMixin):
    """測試用的具體服務類別"""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def _on_start(self) -> None:
        self.started = True

    async def _on_stop(self) -> None:
        self.stopped = True


class TestAsyncLifecycleMixin:
    """AsyncLifecycleMixin 測試"""

    @pytest.mark.asyncio
    async def test_start_calls_on_start(self):
        svc = ConcreteService()
        assert not svc.started
        await svc.start()
        assert svc.started

    @pytest.mark.asyncio
    async def test_stop_calls_on_stop(self):
        svc = ConcreteService()
        assert not svc.stopped
        await svc.stop()
        assert svc.stopped

    @pytest.mark.asyncio
    async def test_context_manager(self):
        svc = ConcreteService()
        async with svc as s:
            assert s is svc
            assert svc.started
            assert not svc.stopped
        assert svc.stopped

    @pytest.mark.asyncio
    async def test_default_on_start_on_stop_are_noop(self):
        """未覆寫 _on_start/_on_stop 時不報錯"""
        svc = AsyncLifecycleMixin()
        await svc.start()
        await svc.stop()

    @pytest.mark.asyncio
    async def test_context_manager_stops_on_exception(self):
        """即使 block 內拋出例外，__aexit__ 仍會呼叫 stop"""
        svc = ConcreteService()
        with pytest.raises(RuntimeError):
            async with svc:
                raise RuntimeError("test error")
        assert svc.stopped
