# =============== Test Leader Gate Behaviour Across Managers ===============
#
# Wave 2a：跨 Manager 的 leader_gate 行為契約測試。
#
# 對 `test_leader_gate.py`（單元 Protocol / AlwaysLeaderGate）的補充，
# 這裡驗證「有注入 leader_gate 時，各 Manager 在非 leader 時不做 side-effect」：
#
#   E.3  UnifiedDeviceManager.leader_gate → _on_start 守門
#   E.6  WriteCommandManager.leader_gate → execute 早期拒絕（repository.create 零呼叫）
#   E.7  StateSyncManager.leader_gate → 5 handler 全部早退
#   E.8  ScheduleService.leader_gate → _poll_once 不被呼叫；中途升格恢復
#
# 注意：
#   - asyncio_mode=auto → async test 不加 decorator
#   - 用 AsyncMock 模擬 async I/O；MagicMock 模擬同步 API
#   - 重用 ``test_leader_gate.ToggleLeaderGate`` 作為可切換 gate

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.core.errors import NotLeaderError
from csp_lib.equipment.alarm import AlarmDefinition, AlarmEvent, AlarmEventType, AlarmLevel
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
from csp_lib.equipment.transport import WriteResult, WriteStatus
from csp_lib.manager import UnifiedConfig, UnifiedDeviceManager
from csp_lib.manager.base import AlwaysLeaderGate
from csp_lib.manager.command.manager import WriteCommandManager
from csp_lib.manager.command.schema import CommandSource, WriteCommand
from csp_lib.manager.schedule.config import ScheduleServiceConfig
from csp_lib.manager.schedule.factory import StrategyFactory
from csp_lib.manager.schedule.service import ScheduleService
from csp_lib.manager.state.sync import StateSyncManager
from tests.helpers import wait_for_condition
from tests.manager.test_leader_gate import ToggleLeaderGate

# ================ 共用 helper ================


class _FakeAsyncDevice:
    """最小 device fake，支援 on/emit（同步 handler 註冊 + async emit）。"""

    def __init__(self, device_id: str = "lg_dev_01") -> None:
        self.device_id = device_id
        self._handlers: dict[str, list] = {}
        self.write = AsyncMock(return_value=WriteResult(status=WriteStatus.SUCCESS, point_name="p1", value=1))

    def on(self, event: str, handler):
        self._handlers.setdefault(event, []).append(handler)

        def _cancel() -> None:
            if handler in self._handlers.get(event, []):
                self._handlers[event].remove(handler)

        return _cancel

    async def emit(self, event: str, payload) -> None:
        for h in list(self._handlers.get(event, [])):
            await h(payload)


def _mock_redis() -> MagicMock:
    """Redis client mock：所有 method 均為 AsyncMock 以便 await。"""
    redis = MagicMock()
    redis.hset = AsyncMock()
    redis.set = AsyncMock()
    redis.sadd = AsyncMock()
    redis.srem = AsyncMock()
    redis.publish = AsyncMock()
    redis.expire = AsyncMock()
    return redis


def _mock_command_repo() -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.update_status = AsyncMock()
    return repo


# ================ E.3 UnifiedDeviceManager.leader_gate ================


class TestUnifiedManagerOnStartLeaderGate:
    """UnifiedDeviceManager._on_start 的 leader_gate 守門。"""

    async def test_leader_starts_device_manager(self) -> None:
        """注入 is_leader=True → device_manager.start() 被呼叫。"""
        gate = ToggleLeaderGate(initial=True)
        manager = UnifiedDeviceManager(UnifiedConfig(), leader_gate=gate)

        manager._device_manager.start = AsyncMock()  # type: ignore[method-assign]
        manager._device_manager.stop = AsyncMock()  # type: ignore[method-assign]

        await manager.start()
        try:
            manager._device_manager.start.assert_awaited_once()
        finally:
            await manager.stop()

    async def test_follower_skips_device_manager_start(self) -> None:
        """注入 is_leader=False → device_manager.start() 不被呼叫、無 raise。"""
        gate = ToggleLeaderGate(initial=False)
        manager = UnifiedDeviceManager(UnifiedConfig(), leader_gate=gate)

        manager._device_manager.start = AsyncMock()  # type: ignore[method-assign]
        manager._device_manager.stop = AsyncMock()  # type: ignore[method-assign]

        # 不應 raise
        await manager.start()
        try:
            manager._device_manager.start.assert_not_awaited()
        finally:
            await manager.stop()

    async def test_no_gate_behaves_like_legacy(self) -> None:
        """未注入 leader_gate → 行為與舊版相同（device_manager.start 被呼叫）。"""
        manager = UnifiedDeviceManager(UnifiedConfig())
        manager._device_manager.start = AsyncMock()  # type: ignore[method-assign]
        manager._device_manager.stop = AsyncMock()  # type: ignore[method-assign]

        await manager.start()
        try:
            manager._device_manager.start.assert_awaited_once()
        finally:
            await manager.stop()

    async def test_always_gate_starts(self) -> None:
        """AlwaysLeaderGate 作為 baseline → 正常 start。"""
        manager = UnifiedDeviceManager(UnifiedConfig(), leader_gate=AlwaysLeaderGate())
        manager._device_manager.start = AsyncMock()  # type: ignore[method-assign]
        manager._device_manager.stop = AsyncMock()  # type: ignore[method-assign]

        await manager.start()
        try:
            manager._device_manager.start.assert_awaited_once()
        finally:
            await manager.stop()


# ================ E.6 WriteCommandManager.leader_gate ================


class TestWriteCommandManagerLeaderGate:
    """WriteCommandManager.execute 的 leader_gate 早期拒絕。"""

    async def test_leader_execute_proceeds(self) -> None:
        """is_leader=True → execute 正常執行，repository.create 被呼叫。"""
        gate = ToggleLeaderGate(initial=True)
        repo = _mock_command_repo()
        manager = WriteCommandManager(repo, leader_gate=gate)
        device = _FakeAsyncDevice("leader_dev")
        manager.subscribe(device)

        cmd = WriteCommand(device_id="leader_dev", point_name="setpoint", value=42)
        result = await manager.execute(cmd)

        assert result.status == WriteStatus.SUCCESS
        repo.create.assert_awaited_once()

    async def test_follower_execute_raises_not_leader_error(self) -> None:
        """is_leader=False → raise NotLeaderError 且 repository.create 零呼叫（早期拒絕）。"""
        gate = ToggleLeaderGate(initial=False)
        repo = _mock_command_repo()
        manager = WriteCommandManager(repo, leader_gate=gate)
        device = _FakeAsyncDevice("follower_dev")
        manager.subscribe(device)

        cmd = WriteCommand(device_id="follower_dev", point_name="setpoint", value=42)
        with pytest.raises(NotLeaderError) as exc:
            await manager.execute(cmd)

        # operation 屬性應包含 device_id / point_name
        assert "follower_dev" in exc.value.operation
        assert "setpoint" in exc.value.operation

        # 關鍵：repository.create 不應被呼叫（side-effect 零）
        repo.create.assert_not_called()
        # device.write 也不應被呼叫
        device.write.assert_not_awaited()

    async def test_follower_execute_from_dict_also_raises(self) -> None:
        """is_leader=False 透過 execute_from_dict 委派路徑也應 raise NotLeaderError。"""
        gate = ToggleLeaderGate(initial=False)
        repo = _mock_command_repo()
        manager = WriteCommandManager(repo, leader_gate=gate)
        device = _FakeAsyncDevice("follower_dict")
        manager.subscribe(device)

        data = {"device_id": "follower_dict", "point_name": "sp", "value": 1}
        with pytest.raises(NotLeaderError):
            await manager.execute_from_dict(data, source=CommandSource.REDIS_PUBSUB)

        repo.create.assert_not_called()

    async def test_no_gate_baseline_unchanged(self) -> None:
        """leader_gate=None → baseline 行為不變。"""
        repo = _mock_command_repo()
        manager = WriteCommandManager(repo)  # no gate
        device = _FakeAsyncDevice("legacy_dev")
        manager.subscribe(device)

        cmd = WriteCommand(device_id="legacy_dev", point_name="p", value=1)
        result = await manager.execute(cmd)
        assert result.status == WriteStatus.SUCCESS
        repo.create.assert_awaited_once()

    async def test_always_gate_baseline(self) -> None:
        """AlwaysLeaderGate → 等同無 gate 的 baseline。"""
        repo = _mock_command_repo()
        manager = WriteCommandManager(repo, leader_gate=AlwaysLeaderGate())
        device = _FakeAsyncDevice("always_dev")
        manager.subscribe(device)

        cmd = WriteCommand(device_id="always_dev", point_name="p", value=1)
        result = await manager.execute(cmd)
        assert result.status == WriteStatus.SUCCESS


class TestNotLeaderError:
    """NotLeaderError 的屬性與字串格式（E.2）。"""

    def test_operation_attribute(self) -> None:
        err = NotLeaderError(operation="write_command(dev.p)", message="not leader")
        assert err.operation == "write_command(dev.p)"

    def test_default_message(self) -> None:
        err = NotLeaderError(operation="some_op")
        # __init__ 的 default message 是 "not leader"
        assert "not leader" in str(err)

    def test_str_format_brackets_operation(self) -> None:
        """str(err) 應為 ``[operation] message`` 格式。"""
        err = NotLeaderError(operation="xyz", message="denied")
        assert str(err) == "[xyz] denied"

    def test_is_exception_not_device_error(self) -> None:
        """刻意繼承 Exception（不是 DeviceError），不會被 device-scoped handler 誤吃。"""
        from csp_lib.core.errors import DeviceError

        err = NotLeaderError(operation="op")
        assert isinstance(err, Exception)
        assert not isinstance(err, DeviceError)


# ================ E.7 StateSyncManager.leader_gate ================


class TestStateSyncManagerLeaderGate:
    """StateSyncManager 5 個 handler 的 leader_gate 行為。"""

    def _build_alarm_payload(self, device_id: str = "ssm_dev", code: str = "A1") -> DeviceAlarmPayload:
        alarm_def = AlarmDefinition(code=code, name="x", level=AlarmLevel.ALARM)
        alarm_event = AlarmEvent(alarm=alarm_def, event_type=AlarmEventType.TRIGGERED)
        return DeviceAlarmPayload(device_id=device_id, alarm_event=alarm_event)

    async def test_leader_read_complete_writes_redis(self) -> None:
        """is_leader=True：read_complete → hset + publish 都被呼叫。"""
        gate = ToggleLeaderGate(initial=True)
        redis = _mock_redis()
        manager = StateSyncManager(redis, leader_gate=gate)
        device = _FakeAsyncDevice("ssm_leader")
        manager.subscribe(device)

        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(device_id="ssm_leader", values={"x": 1}, duration_ms=10.0),
        )

        redis.hset.assert_awaited_once()
        redis.publish.assert_awaited_once()

    async def test_follower_read_complete_skips_all_redis_ops(self) -> None:
        """is_leader=False：read_complete handler 早退，Redis 動作全零呼叫。"""
        gate = ToggleLeaderGate(initial=False)
        redis = _mock_redis()
        manager = StateSyncManager(redis, leader_gate=gate)
        device = _FakeAsyncDevice("ssm_follower")
        manager.subscribe(device)

        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(device_id="ssm_follower", values={"x": 1}, duration_ms=10.0),
        )

        redis.hset.assert_not_called()
        redis.set.assert_not_called()
        redis.publish.assert_not_called()
        redis.expire.assert_not_called()

    async def test_follower_connected_skips(self) -> None:
        gate = ToggleLeaderGate(initial=False)
        redis = _mock_redis()
        manager = StateSyncManager(redis, leader_gate=gate)
        device = _FakeAsyncDevice("conn_follower")
        manager.subscribe(device)

        await device.emit(EVENT_CONNECTED, ConnectedPayload(device_id="conn_follower"))

        redis.set.assert_not_called()
        redis.publish.assert_not_called()

    async def test_follower_disconnected_skips(self) -> None:
        gate = ToggleLeaderGate(initial=False)
        redis = _mock_redis()
        manager = StateSyncManager(redis, leader_gate=gate)
        device = _FakeAsyncDevice("disc_follower")
        manager.subscribe(device)

        await device.emit(
            EVENT_DISCONNECTED,
            DisconnectPayload(device_id="disc_follower", reason="t", consecutive_failures=1),
        )

        redis.set.assert_not_called()
        redis.publish.assert_not_called()

    async def test_follower_alarm_triggered_skips(self) -> None:
        gate = ToggleLeaderGate(initial=False)
        redis = _mock_redis()
        manager = StateSyncManager(redis, leader_gate=gate)
        device = _FakeAsyncDevice("atrig_follower")
        manager.subscribe(device)

        payload = self._build_alarm_payload("atrig_follower", "TRIG")
        await device.emit(EVENT_ALARM_TRIGGERED, payload)

        redis.sadd.assert_not_called()
        redis.publish.assert_not_called()

    async def test_follower_alarm_cleared_skips(self) -> None:
        gate = ToggleLeaderGate(initial=False)
        redis = _mock_redis()
        manager = StateSyncManager(redis, leader_gate=gate)
        device = _FakeAsyncDevice("aclr_follower")
        manager.subscribe(device)

        payload = self._build_alarm_payload("aclr_follower", "CLR")
        await device.emit(EVENT_ALARM_CLEARED, payload)

        redis.srem.assert_not_called()
        redis.publish.assert_not_called()

    def test_follower_subscribe_itself_does_not_touch_redis(self) -> None:
        """subscribe() 本身不受 leader 影響（只掛 handler，不做 Redis I/O）。"""
        gate = ToggleLeaderGate(initial=False)
        redis = _mock_redis()
        manager = StateSyncManager(redis, leader_gate=gate)
        device = _FakeAsyncDevice("sub_follower")

        manager.subscribe(device)

        # 5 個事件應全部註冊成功
        assert len(device._handlers.get(EVENT_READ_COMPLETE, [])) == 1
        assert len(device._handlers.get(EVENT_CONNECTED, [])) == 1
        assert len(device._handlers.get(EVENT_DISCONNECTED, [])) == 1
        assert len(device._handlers.get(EVENT_ALARM_TRIGGERED, [])) == 1
        assert len(device._handlers.get(EVENT_ALARM_CLEARED, [])) == 1

        # Redis 完全沒被碰
        redis.hset.assert_not_called()
        redis.set.assert_not_called()
        redis.sadd.assert_not_called()
        redis.publish.assert_not_called()

    async def test_no_gate_baseline(self) -> None:
        """leader_gate=None → baseline 行為不變（Redis 被呼叫）。"""
        redis = _mock_redis()
        manager = StateSyncManager(redis)  # no gate
        device = _FakeAsyncDevice("legacy_ssm")
        manager.subscribe(device)

        await device.emit(
            EVENT_READ_COMPLETE,
            ReadCompletePayload(device_id="legacy_ssm", values={"x": 1}, duration_ms=1.0),
        )

        redis.hset.assert_awaited_once()
        redis.publish.assert_awaited_once()


# ================ E.8 ScheduleService.leader_gate ================


class TestScheduleServiceLeaderGate:
    """ScheduleService._poll_loop 的 leader_gate 守門。"""

    def _make_config(self, **overrides) -> ScheduleServiceConfig:
        defaults = {"site_id": "site_lg", "poll_interval": 0.05}
        defaults.update(overrides)
        return ScheduleServiceConfig(**defaults)

    async def test_leader_calls_poll_once(self) -> None:
        """is_leader=True → 啟動後 repository.find_active_rules 會被呼叫。"""
        gate = ToggleLeaderGate(initial=True)
        repo = MagicMock()
        repo.find_active_rules = AsyncMock(return_value=[])
        factory = MagicMock(spec=StrategyFactory)
        mode_ctrl = AsyncMock()

        service = ScheduleService(self._make_config(), repo, factory, mode_ctrl, leader_gate=gate)
        await service.start()
        try:
            # 輪詢至少跑一輪
            await wait_for_condition(
                lambda: repo.find_active_rules.await_count >= 1,
                timeout=2.0,
                message="leader should poll at least once",
            )
        finally:
            await service.stop()

    async def test_follower_skips_poll_once(self) -> None:
        """is_leader=False → 輪詢迴圈仍跑，但 _poll_once 不被呼叫。

        負斷言做法：把 ``_poll_once`` 換成「被呼叫就立刻炸」的 AsyncMock，
        這樣若守門失敗，測試會立即 raise，不依賴 sleep 時序 race。
        同時用 wait_for_condition 等「迴圈存活」的正向訊號確認測試有跑到。
        """
        gate = ToggleLeaderGate(initial=False)
        repo = MagicMock()
        repo.find_active_rules = AsyncMock(return_value=[])
        factory = MagicMock(spec=StrategyFactory)
        mode_ctrl = AsyncMock()

        service = ScheduleService(self._make_config(poll_interval=0.02), repo, factory, mode_ctrl, leader_gate=gate)
        # 任何對 _poll_once 的呼叫都應立即 fail（守門應擋下）
        service._poll_once = AsyncMock(  # type: ignore[method-assign]
            side_effect=AssertionError("follower 不該呼叫 _poll_once")
        )

        await service.start()
        try:
            # 正向等待「迴圈 task 確實啟動且存活」，確認測試有跑到；
            # 期間若守門失效 → _poll_once 的 side_effect 會立即炸。
            await wait_for_condition(
                lambda: service._task is not None and not service._task.done(),
                timeout=2.0,
                message="poll loop task should start and stay alive",
            )
            # 再讓 event loop 跑幾輪給迴圈繞好幾次 poll_interval 的機會
            # （若守門失效，此時 _poll_once 一定已經被呼叫過並炸掉 side_effect）
            for _ in range(10):
                await asyncio.sleep(0.01)
            # 正向斷言：_poll_once 從未被呼叫
            service._poll_once.assert_not_called()
            # 迴圈仍存活
            assert not service._task.done(), "迴圈 task 不該提前結束"
        finally:
            await service.stop()

    async def test_promote_mid_run_resumes_polling(self) -> None:
        """起始為 follower，中途 promote → 下一輪 poll 自動恢復。

        負斷言（follower 期間不 poll）改用「被呼叫就炸」的 side_effect；
        升格後改回正常 AsyncMock，再用 wait_for_condition 等 poll 發生。
        """
        gate = ToggleLeaderGate(initial=False)
        repo = MagicMock()
        repo.find_active_rules = AsyncMock(return_value=[])
        factory = MagicMock(spec=StrategyFactory)
        mode_ctrl = AsyncMock()

        service = ScheduleService(
            self._make_config(poll_interval=0.02),
            repo,
            factory,
            mode_ctrl,
            leader_gate=gate,
        )

        # 階段 1：follower 期間，_poll_once 被呼叫就立即 fail
        follower_guard = AsyncMock(side_effect=AssertionError("follower 不該 poll"))
        service._poll_once = follower_guard  # type: ignore[method-assign]

        await service.start()
        try:
            # 等迴圈真的啟動，證明測試進入穩態
            await wait_for_condition(
                lambda: service._task is not None and not service._task.done(),
                timeout=2.0,
                message="loop task should be alive",
            )
            # 階段 2：替換回正常 AsyncMock，再 promote
            promoted_poll = AsyncMock()
            service._poll_once = promoted_poll  # type: ignore[method-assign]
            # follower_guard 至今應該都沒被呼叫（因為有守門）
            follower_guard.assert_not_called()

            gate.promote()

            # 等升格後至少一次 poll（輪詢條件斷言，抗 race）
            await wait_for_condition(
                lambda: promoted_poll.await_count >= 1,
                timeout=2.0,
                message="should poll after promote",
            )
        finally:
            await service.stop()

    async def test_no_gate_baseline(self) -> None:
        """leader_gate=None → baseline 行為不變（會 poll）。"""
        repo = MagicMock()
        repo.find_active_rules = AsyncMock(return_value=[])
        factory = MagicMock(spec=StrategyFactory)
        mode_ctrl = AsyncMock()

        service = ScheduleService(self._make_config(), repo, factory, mode_ctrl)
        await service.start()
        try:
            await wait_for_condition(
                lambda: repo.find_active_rules.await_count >= 1,
                timeout=2.0,
                message="baseline should poll",
            )
        finally:
            await service.stop()
