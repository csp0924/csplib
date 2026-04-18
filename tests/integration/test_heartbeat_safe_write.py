# =============== v0.8.1 HeartbeatService Safe-Write Tests (Bug #1, #2) ===============
#
# Bug：HeartbeatService._send_heartbeats 在 mapping.target 路徑與 targets kwarg
# 路徑直接 `await target.write(value)`，未包覆例外。若 target 實作拋出非
# DeviceError 的例外（自訂 target 的 bug、網路異常等），整個 HeartbeatService
# 背景 task 會終止，違反「單一目標失敗不中斷整個心跳迴圈」的 fire-and-forget 語義。
#
# 修復：兩條路徑都要 catch Exception + log warning + continue。
#
# 測試策略：直接呼叫 _send_heartbeats()（避開 asyncio.sleep），用 pytest.raises
# / 序列斷言兩條路徑的容錯能力。

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

from csp_lib.integration.heartbeat import HeartbeatService
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import HeartbeatMapping


def _make_device(device_id: str, responsive: bool = True) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    dev.write = AsyncMock()
    return dev


class _RaisingTarget:
    """永遠拋 RuntimeError 的 target（模擬自訂 target 的 bug / 非 DeviceError 異常）"""

    def __init__(self, name: str) -> None:
        self._name = name
        self.call_count = 0

    async def write(self, value: int) -> None:
        self.call_count += 1
        raise RuntimeError(f"{self._name}: boom")

    @property
    def identity(self) -> str:
        return f"raising:{self._name}"


class _RecordingTarget:
    """記錄所有 write 呼叫值"""

    def __init__(self, name: str) -> None:
        self._name = name
        self.calls: list[int] = []

    async def write(self, value: int) -> None:
        self.calls.append(value)

    @property
    def identity(self) -> str:
        return f"record:{self._name}"


# ─────────────── Bug #1: mapping.target 路徑 ───────────────


class TestMappingTargetSafeWrite:
    """Bug #1：mapping.target 拋例外不應中斷 _send_heartbeats 迴圈"""

    async def test_raising_mapping_target_does_not_propagate(self):
        """單一 raising target 不應讓 _send_heartbeats 拋例外出去"""
        raising = _RaisingTarget("bad")
        mapping = HeartbeatMapping(point_name="hb", target=raising)
        svc = HeartbeatService(DeviceRegistry(), mappings=[mapping], interval=0.05)

        # 應不 raise（service 層必須包住 target 的任何例外）
        await svc._send_heartbeats()

        # target.write 仍被呼叫（確認執行了）
        assert raising.call_count == 1

    async def test_raising_target_does_not_block_subsequent_mapping_targets(self):
        """前面 mapping.target raise 後，後面的 mapping.target 仍應被寫入"""
        bad = _RaisingTarget("bad")
        good = _RecordingTarget("good")
        mappings = [
            HeartbeatMapping(point_name="hb1", target=bad),
            HeartbeatMapping(point_name="hb2", target=good),
        ]
        svc = HeartbeatService(DeviceRegistry(), mappings=mappings, interval=0.05)

        await svc._send_heartbeats()

        assert bad.call_count == 1, "前面的 raising target 應被呼叫過"
        assert len(good.calls) == 1, "後面的 good target 不應因為 bad 拋例外而被跳過"

    async def test_raising_target_does_not_block_independent_targets_kwarg(self):
        """mapping.target raise 後，獨立 targets kwarg 仍應被寫入"""
        bad = _RaisingTarget("bad")
        good = _RecordingTarget("good")
        mapping = HeartbeatMapping(point_name="hb", target=bad)
        svc = HeartbeatService(DeviceRegistry(), mappings=[mapping], targets=[good], interval=0.05)

        await svc._send_heartbeats()

        assert bad.call_count == 1
        assert len(good.calls) == 1, "獨立 targets kwarg 不應因 mapping.target 拋例外而被跳過"


# ─────────────── Bug #2: targets kwarg 路徑 ───────────────


class TestTargetsKwargSafeWrite:
    """Bug #2：targets kwarg 拋例外不應中斷 _send_heartbeats 迴圈"""

    async def test_raising_target_in_targets_kwarg_does_not_propagate(self):
        """targets kwarg 中的 raising target 不應讓 _send_heartbeats 拋例外"""
        raising = _RaisingTarget("bad")
        svc = HeartbeatService(DeviceRegistry(), targets=[raising], interval=0.05)

        # 應不 raise
        await svc._send_heartbeats()

        assert raising.call_count == 1

    async def test_raising_target_does_not_block_subsequent_targets_kwarg(self):
        """前面 targets[i] raise 後，後面 targets[i+1] 仍應被寫入"""
        bad = _RaisingTarget("bad")
        good = _RecordingTarget("good")
        svc = HeartbeatService(DeviceRegistry(), targets=[bad, good], interval=0.05)

        await svc._send_heartbeats()

        assert bad.call_count == 1
        assert len(good.calls) == 1, "後面的 good target 不應因前面 target 拋例外而被跳過"

    async def test_raising_target_does_not_block_capability_path(self):
        """targets kwarg raise 後，能力發現路徑仍應被寫入"""
        bad = _RaisingTarget("bad")
        # 建立有 HEARTBEAT 能力的 responsive 設備
        dev = _make_device("pcs1")
        dev.has_capability = MagicMock(return_value=True)
        dev.resolve_point = MagicMock(return_value="hb_point")

        reg = DeviceRegistry()
        # 手動模擬能力發現 (avoid full registration API)
        reg.get_responsive_devices_with_capability = MagicMock(return_value=[dev])  # type: ignore[method-assign]

        svc = HeartbeatService(reg, targets=[bad], use_capability=True, interval=0.05)
        await svc._send_heartbeats()

        assert bad.call_count == 1
        # capability 路徑仍應觸發 device.write
        dev.write.assert_awaited_once()
        assert dev.write.await_args[0][0] == "hb_point"
