# =============== CommandRouter NO_CHANGE Tests (v0.8.0 WI-V080-004) ===============
#
# 覆蓋 CommandRouter 對 Command 軸為 NO_CHANGE 時的 skip 寫入行為：
#   - 單軸 NO_CHANGE：另一軸照寫
#   - 雙軸 NO_CHANGE：完全不寫
#   - trait 廣播模式 + NO_CHANGE：整軸廣播被跳過
#   - transform 不會套用在 NO_CHANGE 上
#   - None 值維持既有 skip 行為（與 NO_CHANGE 無衝突）

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command
from csp_lib.controller.core.command import NO_CHANGE
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


class TestCommandRouterNoChangeDeviceIdMode:
    """device_id 模式下的 NO_CHANGE 行為"""

    async def test_p_no_change_q_float_only_q_written(self):
        """p_target=NO_CHANGE + q_target=100.0 → 只寫 Q，不寫 P"""
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
        await router.route(Command(p_target=NO_CHANGE, q_target=100.0))

        # 只有 q_set 被寫，p_set 完全未觸發
        dev.write.assert_awaited_once_with("q_set", 100.0)

    async def test_both_no_change_no_writes(self):
        """雙軸皆 NO_CHANGE → 設備 write 完全不被呼叫"""
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
        await router.route(Command(p_target=NO_CHANGE, q_target=NO_CHANGE))
        dev.write.assert_not_called()

    async def test_p_float_q_no_change_only_p_written(self):
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
        dev.write.assert_awaited_once_with("p_set", 50.0)

    async def test_transform_not_applied_to_no_change(self):
        """即使 mapping 有 transform，NO_CHANGE 也不會被 transform（直接 skip）"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        transform_called: list[object] = []

        def spy_transform(v: float) -> float:
            transform_called.append(v)
            return v * 2

        router = CommandRouter(
            reg,
            [
                CommandMapping(
                    command_field="p_target",
                    point_name="p_set",
                    device_id="pcs1",
                    transform=spy_transform,
                )
            ],
        )
        await router.route(Command(p_target=NO_CHANGE, q_target=10.0))

        assert transform_called == [], "Transform 不得對 NO_CHANGE 被呼叫"
        dev.write.assert_not_called()


class TestCommandRouterNoChangeTraitMode:
    """trait 廣播模式下的 NO_CHANGE"""

    async def test_trait_broadcast_no_change_skips_all_devices(self):
        """trait 模式下若 field 為 NO_CHANGE，所有 trait 內設備皆不被寫入"""
        reg = DeviceRegistry()
        d1 = _make_device("pcs1")
        d2 = _make_device("pcs2")
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", trait="pcs")],
        )
        await router.route(Command(p_target=NO_CHANGE, q_target=0.0))

        d1.write.assert_not_called()
        d2.write.assert_not_called()

    async def test_trait_broadcast_p_no_change_q_float_only_q_broadcasts(self):
        reg = DeviceRegistry()
        d1 = _make_device("pcs1")
        d2 = _make_device("pcs2")
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        router = CommandRouter(
            reg,
            [
                CommandMapping(command_field="p_target", point_name="p_set", trait="pcs"),
                CommandMapping(command_field="q_target", point_name="q_set", trait="pcs"),
            ],
        )
        await router.route(Command(p_target=NO_CHANGE, q_target=-50.0))

        d1.write.assert_awaited_once_with("q_set", -50.0)
        d2.write.assert_awaited_once_with("q_set", -50.0)


class TestCommandRouterNoChangeEdgeCases:
    """邊緣案例"""

    async def test_none_field_and_no_change_coexist(self):
        """Command 欄位 None（例如自訂 field）照 skip；NO_CHANGE 也 skip — 兩者互不干擾"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        router = CommandRouter(
            reg,
            [
                # 指向不存在欄位 → getattr 回 None → skip
                CommandMapping(command_field="ghost_field", point_name="ghost", device_id="pcs1"),
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
        )
        await router.route(Command(p_target=NO_CHANGE, q_target=0.0))
        dev.write.assert_not_called()

    async def test_no_change_respects_protected_device_skip(self):
        """即使 mapping 是 p=float，device is_protected → 仍 skip（NO_CHANGE 路徑不變）"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", protected=True)
        reg.register(dev)

        router = CommandRouter(
            reg,
            [CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
        )
        await router.route(Command(p_target=100.0, q_target=NO_CHANGE))
        # p 是 float 但設備 protected → 不寫；q 是 NO_CHANGE → 不寫
        dev.write.assert_not_called()


@pytest.mark.parametrize(
    "p, q, expect_p_written, expect_q_written",
    [
        (NO_CHANGE, NO_CHANGE, False, False),
        (0.0, NO_CHANGE, True, False),
        (NO_CHANGE, 0.0, False, True),
        (100.0, -50.0, True, True),
    ],
)
async def test_matrix_no_change_combinations(p, q, expect_p_written, expect_q_written):
    """NO_CHANGE / float 所有組合的參數化驗證"""
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
    await router.route(Command(p_target=p, q_target=q))

    written_points = {call.args[0] for call in dev.write.await_args_list}
    assert ("p_set" in written_points) is expect_p_written
    assert ("q_set" in written_points) is expect_q_written
