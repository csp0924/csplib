# =============== v0.8.1 CommandRouter last_written Tests ===============
#
# 涵蓋 Feature spec AC2 / AC3：
#   - AC2：NO_CHANGE 軸不更新 _last_written；既有值保留（業務值不被覆蓋）
#   - AC3：is_fallback=True 仍更新 _last_written（router 不特別對待 fallback）
#
# 其他公開 API 驗證：
#   - try_write_single(device_id, point_name, value) -> bool
#     成功回 True，失敗 / 跳過回 False，僅成功才 update last_written
#   - get_last_written(device_id) 回 shallow copy
#   - get_tracked_device_ids() 多設備追蹤
#   - trait broadcast 對多設備分別 update last_written
#   - 寫入失敗（DeviceError）不 update；protected / unresponsive / 不存在 都回 False
#
# 這是 feature spec 的核心測試，其他檔案都建築在此之上（尤其 CommandRefreshService）

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

from csp_lib.controller.core import Command
from csp_lib.controller.core.command import NO_CHANGE
from csp_lib.core.errors import DeviceError
from csp_lib.integration.command_router import CommandRouter
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CommandMapping


def _make_device(device_id: str, responsive: bool = True, protected: bool = False) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    dev.write = AsyncMock()
    return dev


# ─────────────── AC2: NO_CHANGE 保留業務值 ───────────────


class TestNoChangePreservesLastWritten:
    """AC2：NO_CHANGE 不建立 / 不覆蓋 last_written 條目"""

    async def test_no_change_does_not_create_entry(self):
        """首次 route：p=50.0, q=NO_CHANGE → last_written 只含 p_set，無 q_set"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        router = CommandRouter(
            reg,
            [
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
                CommandMapping(command_field="q_target", point_name="q_set", device_id="pcs1"),
            ],
        )
        await router.route(Command(p_target=50.0, q_target=NO_CHANGE))

        snapshot = router.get_last_written("pcs1")
        assert snapshot == {"p_set": 50.0}, "NO_CHANGE 軸不應建立 entry"

    async def test_no_change_does_not_overwrite_existing_entry(self):
        """AC2 核心：先寫 q=30.0，再送 p=60.0, q=NO_CHANGE → q_set 應保留 30.0"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        router = CommandRouter(
            reg,
            [
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
                CommandMapping(command_field="q_target", point_name="q_set", device_id="pcs1"),
            ],
        )

        # 第一次 route：建立 p=10, q=30
        await router.route(Command(p_target=10.0, q_target=30.0))
        assert router.get_last_written("pcs1") == {"p_set": 10.0, "q_set": 30.0}

        # 第二次 route：p=60, q=NO_CHANGE → q_set 應仍為 30.0（不被清除）
        await router.route(Command(p_target=60.0, q_target=NO_CHANGE))
        snapshot = router.get_last_written("pcs1")
        assert snapshot == {"p_set": 60.0, "q_set": 30.0}, "NO_CHANGE 不得清除既有 last_written 值"


# ─────────────── AC3: is_fallback 仍 update ───────────────


class TestFallbackUpdatesLastWritten:
    """AC3：is_fallback=True 的 Command 仍寫入且更新 last_written"""

    async def test_fallback_command_updates_last_written(self):
        """AC3：Command(0, 0, is_fallback=True) → last_written[p]=0, last_written[q]=0"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        router = CommandRouter(
            reg,
            [
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
                CommandMapping(command_field="q_target", point_name="q_set", device_id="pcs1"),
            ],
        )
        await router.route(Command(p_target=0.0, q_target=0.0, is_fallback=True))

        snapshot = router.get_last_written("pcs1")
        assert snapshot == {"p_set": 0.0, "q_set": 0.0}
        # CommandRefreshService 下輪仍會看見 0.0 並重送（reconciler 不特殊對待 fallback）

    async def test_fallback_after_real_command_overwrites(self):
        """AC3：先寫 p=100，再送 fallback(0,0) → last_written 變 0（正常覆蓋語義）"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        router = CommandRouter(
            reg,
            [
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
                CommandMapping(command_field="q_target", point_name="q_set", device_id="pcs1"),
            ],
        )
        await router.route(Command(p_target=100.0, q_target=50.0))
        await router.route(Command(p_target=0.0, q_target=0.0, is_fallback=True))

        assert router.get_last_written("pcs1") == {"p_set": 0.0, "q_set": 0.0}


# ─────────────── 寫入失敗不 update ───────────────


class TestFailureDoesNotUpdate:
    """DeviceError / unresponsive / protected / 不存在 皆不 update last_written"""

    async def test_device_error_does_not_update(self):
        """寫入 raise DeviceError → last_written 保留上次成功值"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
        )

        # 首次成功寫入
        await router.route(Command(p_target=100.0))
        assert router.get_last_written("pcs1") == {"p_set": 100.0}

        # 改成 raise DeviceError 的 side_effect
        dev.write = AsyncMock(side_effect=DeviceError("pcs1", "write failed"))
        await router.route(Command(p_target=999.0))

        # last_written 應保留 100.0，未被 999.0 覆蓋
        assert router.get_last_written("pcs1") == {"p_set": 100.0}

    async def test_try_write_single_returns_false_on_device_error(self):
        """try_write_single 遇 DeviceError 回 False"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        dev.write = AsyncMock(side_effect=DeviceError("pcs1", "err"))
        reg.register(dev)

        router = CommandRouter(reg, mappings=[])
        result = await router.try_write_single("pcs1", "p_set", 123.0)
        assert result is False
        assert router.get_last_written("pcs1") == {}

    async def test_try_write_single_unknown_device_returns_false(self):
        """不存在的 device_id → False，不建立 entry"""
        reg = DeviceRegistry()
        router = CommandRouter(reg, mappings=[])

        result = await router.try_write_single("ghost", "p_set", 1.0)
        assert result is False
        assert router.get_last_written("ghost") == {}

    async def test_try_write_single_protected_device_returns_false(self):
        """protected device → False，不寫入"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", protected=True)
        reg.register(dev)
        router = CommandRouter(reg, mappings=[])

        result = await router.try_write_single("pcs1", "p_set", 1.0)
        assert result is False
        dev.write.assert_not_awaited()
        assert router.get_last_written("pcs1") == {}

    async def test_try_write_single_unresponsive_device_returns_false(self):
        """unresponsive device → False"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", responsive=False)
        reg.register(dev)
        router = CommandRouter(reg, mappings=[])

        result = await router.try_write_single("pcs1", "p_set", 1.0)
        assert result is False
        dev.write.assert_not_awaited()
        assert router.get_last_written("pcs1") == {}

    async def test_try_write_single_success_returns_true_and_updates(self):
        """寫入成功 → True，且更新 last_written"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)
        router = CommandRouter(reg, mappings=[])

        result = await router.try_write_single("pcs1", "p_set", 77.0)
        assert result is True
        assert router.get_last_written("pcs1") == {"p_set": 77.0}
        dev.write.assert_awaited_once_with("p_set", 77.0)


# ─────────────── Bug #3: try_write_single NO_CHANGE 防呆 ───────────────


class TestTryWriteSingleRejectsNoChange:
    """Bug #3：try_write_single 應在 value 為 NO_CHANGE sentinel 時 early-return

    若不擋：外部誤傳會把 sentinel 寫入設備並進 _last_written，
    CommandRefreshService 後續會週期性把 sentinel 當 desired-state 重送。
    """

    async def test_no_change_early_returns_false_without_write(self):
        """try_write_single(NO_CHANGE) → 回 False、不呼叫 device.write、不 record"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)
        router = CommandRouter(reg, mappings=[])

        result = await router.try_write_single("pcs1", "p_set", NO_CHANGE)

        assert result is False, "NO_CHANGE 應被拒寫"
        dev.write.assert_not_awaited()
        assert router.get_last_written("pcs1") == {}

    async def test_no_change_does_not_overwrite_existing_last_written(self):
        """先成功寫 p=100，再直接傳 NO_CHANGE → last_written 應保留 100（不被污染）"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)
        router = CommandRouter(reg, mappings=[])

        ok = await router.try_write_single("pcs1", "p_set", 100.0)
        assert ok is True
        assert router.get_last_written("pcs1") == {"p_set": 100.0}

        # 直接 bypass route() 傳 NO_CHANGE sentinel
        result = await router.try_write_single("pcs1", "p_set", NO_CHANGE)

        assert result is False
        # last_written 不得被 NO_CHANGE sentinel 覆蓋
        assert router.get_last_written("pcs1") == {"p_set": 100.0}

    async def test_no_change_does_not_track_device(self):
        """若 device 先前未被寫入過，NO_CHANGE 不應讓它進 tracked set"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)
        router = CommandRouter(reg, mappings=[])

        await router.try_write_single("pcs1", "p_set", NO_CHANGE)

        assert router.get_tracked_device_ids() == frozenset()


# ─────────────── get_last_written shallow copy ───────────────


class TestGetLastWrittenShallowCopy:
    """AC2：get_last_written 回淺拷貝，外部修改不影響 router 內部"""

    async def test_returns_shallow_copy(self):
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)
        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
        )

        await router.route(Command(p_target=50.0))

        snapshot = router.get_last_written("pcs1")
        snapshot["p_set"] = 99999.0  # 外部污染
        snapshot["new_key"] = "junk"

        # 再取一次快照，應保持原值
        clean = router.get_last_written("pcs1")
        assert clean == {"p_set": 50.0}, "get_last_written 應回淺拷貝，外部污染不影響內部"

    async def test_empty_when_no_writes(self):
        """未寫入過的 device → 回空 dict"""
        reg = DeviceRegistry()
        router = CommandRouter(reg, mappings=[])
        assert router.get_last_written("any") == {}


# ─────────────── get_tracked_device_ids 多設備 ───────────────


class TestGetTrackedDeviceIds:
    """多台設備寫入後，tracked ids 應含所有有寫入的 device"""

    async def test_multiple_devices_tracked(self):
        reg = DeviceRegistry()
        d1 = _make_device("pcs1")
        d2 = _make_device("pcs2")
        reg.register(d1)
        reg.register(d2)

        router = CommandRouter(reg, mappings=[])
        await router.try_write_single("pcs1", "p_set", 10.0)
        await router.try_write_single("pcs2", "p_set", 20.0)

        tracked = router.get_tracked_device_ids()
        assert isinstance(tracked, frozenset)
        assert tracked == frozenset({"pcs1", "pcs2"})

    async def test_failed_write_not_tracked(self):
        """寫入失敗的 device 不應出現在 tracked"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        dev.write = AsyncMock(side_effect=DeviceError("pcs1", "err"))
        reg.register(dev)

        router = CommandRouter(reg, mappings=[])
        await router.try_write_single("pcs1", "p_set", 1.0)

        assert router.get_tracked_device_ids() == frozenset()

    async def test_no_writes_empty_set(self):
        reg = DeviceRegistry()
        router = CommandRouter(reg, mappings=[])
        assert router.get_tracked_device_ids() == frozenset()


# ─────────────── trait broadcast 多設備各自 update ───────────────


class TestTraitBroadcastUpdatesEachDevice:
    """trait 模式下多台設備應各自有 last_written 條目"""

    async def test_broadcast_updates_all_devices(self):
        reg = DeviceRegistry()
        d1 = _make_device("pcs1")
        d2 = _make_device("pcs2")
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", trait="pcs")],
        )
        await router.route(Command(p_target=42.0))

        assert router.get_last_written("pcs1") == {"p_set": 42.0}
        assert router.get_last_written("pcs2") == {"p_set": 42.0}

    async def test_broadcast_partial_failure_only_successful_tracked(self):
        """broadcast 時 d1 失敗、d2 成功 → 只 d2 進 last_written"""
        reg = DeviceRegistry()
        d1 = _make_device("pcs1")
        d1.write = AsyncMock(side_effect=DeviceError("pcs1", "err"))
        d2 = _make_device("pcs2")
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", trait="pcs")],
        )
        await router.route(Command(p_target=42.0))

        assert router.get_last_written("pcs1") == {}
        assert router.get_last_written("pcs2") == {"p_set": 42.0}
