# =============== v0.8.1 HeartbeatService New API Tests ===============
#
# 涵蓋 Feature spec AC4（新 API 路徑整合測試）：
#   - HeartbeatService 支援 mapping.value_generator + mapping.target 新路徑
#   - 舊 mode kwarg 路徑不變（smoke regression）
#   - 新舊混用於不同 mapping 時各自獨立（per-mapping generator cache）
#   - targets kwarg：獨立 target 列表（不經 registry/mapping）
#
# 測試策略：
#   - 用 asyncio.sleep + interval=0.05 讓 service 跑幾個 tick
#   - 驗證 write 的 call_args 序列（ToggleGenerator 應產生 1,0,1,...）
#   - 對 legacy 路徑跑一次 smoke test 確認未回歸

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from csp_lib.integration.heartbeat import HeartbeatService
from csp_lib.integration.heartbeat_generators import ConstantGenerator, ToggleGenerator
from csp_lib.integration.heartbeat_targets import HeartbeatTarget
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import HeartbeatMapping, HeartbeatMode


def _make_device(device_id: str, responsive: bool = True) -> MagicMock:
    """最小 heartbeat mock device"""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    dev.write = AsyncMock()
    return dev


class _RecordingTarget:
    """測試用 HeartbeatTarget：記錄所有 write 呼叫與 identity"""

    def __init__(self, name: str) -> None:
        self._name = name
        self.calls: list[int] = []

    async def write(self, value: int) -> None:
        self.calls.append(value)

    @property
    def identity(self) -> str:
        return f"record:{self._name}"


# ─────────────── 新 API：mapping.value_generator + mapping.target ───────────────


class TestNewApiMappingPath:
    """AC4：HeartbeatService 在 mapping.target 路徑使用 mapping.value_generator"""

    async def test_uses_value_generator_on_target_path(self):
        """AC4：mapping.target + mapping.value_generator → write 序列為 generator 產生的值"""
        target = _RecordingTarget("t1")
        mapping = HeartbeatMapping(
            point_name="hb",
            value_generator=ToggleGenerator(),
            target=target,
        )
        # registry 裡沒設備也沒關係 — target 路徑不經 registry
        svc = HeartbeatService(DeviceRegistry(), mappings=[mapping], interval=0.05)

        await svc.start()
        # 等至少 3 個 tick
        await asyncio.sleep(0.18)
        await svc.stop()

        # ToggleGenerator 首呼叫回 1，再呼叫 0 → 序列為 [1, 0, 1, ...]
        assert len(target.calls) >= 3
        assert target.calls[0] == 1
        assert target.calls[1] == 0
        assert target.calls[2] == 1

    async def test_uses_constant_generator_on_target_path(self):
        """AC4：ConstantGenerator 應持續輸出固定值"""
        target = _RecordingTarget("t_const")
        mapping = HeartbeatMapping(
            point_name="hb",
            value_generator=ConstantGenerator(value=7),
            target=target,
        )
        svc = HeartbeatService(DeviceRegistry(), mappings=[mapping], interval=0.05)
        await svc.start()
        await asyncio.sleep(0.15)
        await svc.stop()

        assert len(target.calls) >= 2
        assert all(v == 7 for v in target.calls)

    async def test_target_without_value_generator_uses_default_toggle(self):
        """AC4：mapping.target 未指定 value_generator，應以 mapping.mode 建立預設 generator

        這驗證了 _resolve_generator 的 fallback 邏輯（per-mapping cache）。
        mapping.mode=TOGGLE 為預設，應看到 1,0,1,... 交替。
        """
        target = _RecordingTarget("t_default")
        mapping = HeartbeatMapping(
            point_name="hb",
            target=target,
        )
        # mapping.mode 預設 TOGGLE，value_generator 為 None → 應 cache 一個 ToggleGenerator
        svc = HeartbeatService(DeviceRegistry(), mappings=[mapping], interval=0.05)
        await svc.start()
        await asyncio.sleep(0.18)
        await svc.stop()

        assert len(target.calls) >= 3
        assert target.calls[0] == 1
        assert target.calls[1] == 0  # 若每 tick 重建 generator 會永遠是 1（已知 bug 防呆）
        assert target.calls[2] == 1


# ─────────────── Legacy smoke regression ───────────────


class TestLegacyPathSmoke:
    """AC4：舊 API 路徑（device_id + mode kwarg）行為不變"""

    async def test_legacy_device_id_toggle_still_works(self):
        """舊 device_id 模式 + TOGGLE：設備應收到 1, 0, 1, ... 序列"""
        dev = _make_device("pcs_01")
        reg = DeviceRegistry()
        reg.register(dev, traits=["pcs"])

        mapping = HeartbeatMapping(
            point_name="hb",
            device_id="pcs_01",
            mode=HeartbeatMode.TOGGLE,
        )
        svc = HeartbeatService(reg, mappings=[mapping], interval=0.05)
        await svc.start()
        await asyncio.sleep(0.18)
        await svc.stop()

        # 舊路徑走 _counters + _next_value_for_mapping；序列應為 1, 0, 1
        assert dev.write.await_count >= 3
        call_values = [c.args[1] for c in dev.write.await_args_list]
        assert call_values[0] == 1
        assert call_values[1] == 0


# ─────────────── 新舊混用 ───────────────


class TestMixedNewAndLegacyMappings:
    """AC4：同一 HeartbeatService 內新舊 mapping 並存，各自獨立計數"""

    async def test_new_and_legacy_mapping_coexist(self):
        """一個 mapping 用新 API (target+value_generator)，另一個用舊 API — 各自獨立"""
        # 新 API mapping
        target = _RecordingTarget("new")
        new_mapping = HeartbeatMapping(
            point_name="hb_new",
            value_generator=ToggleGenerator(),
            target=target,
        )

        # 舊 API mapping（device_id 路徑）
        dev = _make_device("pcs_01")
        reg = DeviceRegistry()
        reg.register(dev)
        legacy_mapping = HeartbeatMapping(
            point_name="hb_legacy",
            device_id="pcs_01",
            mode=HeartbeatMode.TOGGLE,
        )

        svc = HeartbeatService(reg, mappings=[new_mapping, legacy_mapping], interval=0.05)
        await svc.start()
        await asyncio.sleep(0.18)
        await svc.stop()

        # 新 API target 收到 [1, 0, 1, ...]
        assert len(target.calls) >= 3
        assert target.calls[0] == 1
        assert target.calls[1] == 0

        # 舊 API device 也收到 [1, 0, 1, ...]，兩者不會互相污染狀態
        assert dev.write.await_count >= 3
        legacy_values = [c.args[1] for c in dev.write.await_args_list]
        assert legacy_values[0] == 1
        assert legacy_values[1] == 0


# ─────────────── targets kwarg：獨立 target 列表 ───────────────


class TestTargetsKwarg:
    """AC4：HeartbeatService(..., targets=[...]) 獨立 target 路徑"""

    async def test_standalone_targets_via_kwarg(self):
        """AC4：targets kwarg 傳入的 target 不經 mapping，以預設 ToggleGenerator 產生值"""
        t1 = _RecordingTarget("a")
        t2 = _RecordingTarget("b")
        svc = HeartbeatService(
            DeviceRegistry(),
            mappings=None,
            interval=0.05,
            targets=[t1, t2],
        )
        await svc.start()
        await asyncio.sleep(0.18)
        await svc.stop()

        # 兩個 target 都應收到多次 write，序列為 [1, 0, 1, ...]
        assert len(t1.calls) >= 3
        assert len(t2.calls) >= 3
        assert t1.calls[0] == 1
        assert t1.calls[1] == 0  # per-identity key 隔離 → 各自獨立序列
        assert t2.calls[0] == 1
        assert t2.calls[1] == 0

    async def test_targets_kwarg_coexists_with_mappings(self):
        """AC4：targets kwarg 與 mappings 同時設定，兩路徑皆被處理"""
        t = _RecordingTarget("standalone")
        dev = _make_device("pcs_01")
        reg = DeviceRegistry()
        reg.register(dev)
        mapping = HeartbeatMapping(point_name="hb", device_id="pcs_01", mode=HeartbeatMode.TOGGLE)

        svc = HeartbeatService(
            reg,
            mappings=[mapping],
            interval=0.05,
            targets=[t],
        )
        await svc.start()
        await asyncio.sleep(0.15)
        await svc.stop()

        assert len(t.calls) >= 2
        assert dev.write.await_count >= 2

    async def test_targets_is_heartbeat_target_protocol(self):
        """AC4：確認 _RecordingTarget 結構等同 HeartbeatTarget（測試本身的 Protocol 守衛）"""
        t = _RecordingTarget("x")
        assert isinstance(t, HeartbeatTarget)


# ─────────────── reset_counters 含新 cache ───────────────


class TestResetCountersIncludesNewCache:
    """AC4：reset_counters 應同時清除 legacy _counters 與新 generator cache

    注意：外部傳入的 mapping.value_generator 不入 cache（走第 222 行 early return），
    因此 reset_counters 不會影響外部 generator 狀態。cache 僅在 target 模式但
    mapping.value_generator 為 None 時，由 _resolve_generator 根據 mapping.mode
    建立預設 generator 並 cache。此測試驗證「cache 中的 generator 在 reset_counters
    後被 reset」。
    """

    async def test_reset_clears_cached_default_generator(self):
        """mapping.target 設但未指定 value_generator → generator 入 cache，reset 後清空"""
        target = _RecordingTarget("r_cache")
        # target 設，但 value_generator 未設 → HeartbeatService 會建立並 cache 預設 ToggleGenerator
        mapping = HeartbeatMapping(
            point_name="hb",
            target=target,
        )
        svc = HeartbeatService(DeviceRegistry(), mappings=[mapping], interval=0.05)

        await svc.start()
        await asyncio.sleep(0.15)
        await svc.stop()

        # 至少跑了 2 次（1, 0）
        assert len(target.calls) >= 2
        # cache 中應有一個 generator（mapping 的 id 為 key）
        assert len(svc._mapping_generator_cache) == 1

        # reset_counters 清除 cache generator state
        svc.reset_counters()
        target.calls.clear()

        # 重新啟動，cached generator state 已被 reset → 首次應回 1
        await svc.start()
        await asyncio.sleep(0.08)
        await svc.stop()

        assert len(target.calls) >= 1
        assert target.calls[0] == 1, f"reset 後首次 next 應回 1，實際：{target.calls[0]}"

    async def test_reset_clears_targets_generator(self):
        """targets kwarg 路徑的共用 _targets_generator 也應被 reset"""
        t = _RecordingTarget("shared")
        svc = HeartbeatService(DeviceRegistry(), targets=[t], interval=0.05)

        await svc.start()
        await asyncio.sleep(0.15)
        await svc.stop()

        assert len(t.calls) >= 2

        svc.reset_counters()
        t.calls.clear()

        await svc.start()
        await asyncio.sleep(0.08)
        await svc.stop()

        assert len(t.calls) >= 1
        assert t.calls[0] == 1, f"_targets_generator reset 後首次應回 1，實際：{t.calls[0]}"
