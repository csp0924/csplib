# =============== Test LeaderGate ===============
#
# LeaderGate Protocol / AlwaysLeaderGate 單元測試。
#
# 測試覆蓋：
#   - AlwaysLeaderGate.is_leader 恆為 True
#   - AlwaysLeaderGate.wait_until_leader 立即完成
#   - isinstance(..., LeaderGate) runtime_checkable 驗證
#   - 自製 Mock LeaderGate：is_leader=False 時 wait_until_leader 阻塞；
#     切換為 True 後釋放；CancelledError 向上拋。

from __future__ import annotations

import asyncio

import pytest

from csp_lib.manager.base import AlwaysLeaderGate, LeaderGate


async def _wait_for_condition(pred, timeout: float = 2.0, interval: float = 0.01) -> None:
    """輪詢斷言（bug-lesson async-test-state-race）。"""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if pred():
            return
        await asyncio.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


class TestAlwaysLeaderGate:
    """AlwaysLeaderGate no-op 實作測試。"""

    def test_is_leader_true(self) -> None:
        """is_leader 恆為 True。"""
        gate = AlwaysLeaderGate()
        assert gate.is_leader is True

    async def test_wait_until_leader_returns_immediately(self) -> None:
        """wait_until_leader 應立即完成（不阻塞）。"""
        gate = AlwaysLeaderGate()
        # 用 wait_for timeout 保險——正常情況下 <<< 0.5s
        await asyncio.wait_for(gate.wait_until_leader(), timeout=0.5)

    def test_is_instance_of_leader_gate(self) -> None:
        """runtime_checkable: AlwaysLeaderGate 應被識別為 LeaderGate。"""
        gate = AlwaysLeaderGate()
        assert isinstance(gate, LeaderGate) is True


# ================ Mock LeaderGate（is_leader 可切換）================


class ToggleLeaderGate:
    """測試用 LeaderGate：可手動切換 is_leader，並以 Event 喚醒 waiter。"""

    def __init__(self, initial: bool = False) -> None:
        self._leader = initial
        self._event = asyncio.Event()
        if initial:
            self._event.set()

    @property
    def is_leader(self) -> bool:
        return self._leader

    async def wait_until_leader(self) -> None:
        await self._event.wait()

    def promote(self) -> None:
        self._leader = True
        self._event.set()

    def demote(self) -> None:
        self._leader = False
        self._event.clear()


class TestToggleLeaderGateProtocolConformance:
    """驗證自製 gate 也結構性滿足 LeaderGate Protocol。"""

    def test_is_leader_gate_protocol(self) -> None:
        gate = ToggleLeaderGate(initial=False)
        assert isinstance(gate, LeaderGate) is True


class TestToggleLeaderGateSemantics:
    """非 leader 時 wait 阻塞；切換後釋放；cancel 時 raise。"""

    async def test_wait_blocks_when_not_leader(self) -> None:
        """is_leader=False 時 wait_until_leader 阻塞至 promote。"""
        gate = ToggleLeaderGate(initial=False)

        task = asyncio.create_task(gate.wait_until_leader())
        # 驗證 task 處於阻塞：用 wait_for 短 timeout 斷言必然 timeout
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=0.05)
        assert not task.done(), "應阻塞直到 promote"

        gate.promote()

        # 輪詢等待 task 完成（避免 race）
        await _wait_for_condition(lambda: task.done(), timeout=1.0)
        assert gate.is_leader is True
        # 取結果（應為 None 且無例外）
        assert task.result() is None

    async def test_wait_returns_immediately_when_already_leader(self) -> None:
        """初始即 leader 時 wait_until_leader 立即完成。"""
        gate = ToggleLeaderGate(initial=True)
        await asyncio.wait_for(gate.wait_until_leader(), timeout=0.5)

    async def test_wait_can_be_cancelled(self) -> None:
        """非 leader 時取消 wait_until_leader 應 raise CancelledError。"""
        gate = ToggleLeaderGate(initial=False)
        task = asyncio.create_task(gate.wait_until_leader())
        # 驗證 task 處於阻塞（用 wait_for timeout 而非 sleep+assert）
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=0.05)
        assert not task.done()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
