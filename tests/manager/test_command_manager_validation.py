# =============== Tests: WriteCommandManager validation_rules ===============
#
# 涵蓋 C-P2 整合：Sequence / Mapping 驗證鏈、clamp / reject、leader gate 優先序、
# VALIDATION_FAILED repository 寫入、regression (None = 舊行為)
#
# **不得** import modbus_gateway（Layer 5 → Layer 8 違規）。
# modbus_gateway.WriteRule 的結構相容性由 tests/modbus_gateway/ 自家測試負責。

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from csp_lib.core.errors import NotLeaderError
from csp_lib.equipment.transport import RangeRule, ValidationResult, WriteResult, WriteStatus
from csp_lib.manager.base import AlwaysLeaderGate, LeaderGate
from csp_lib.manager.command.manager import WriteCommandManager
from csp_lib.manager.command.schema import CommandStatus, WriteCommand


class MockDevice:
    def __init__(self, device_id: str, return_value: Any = 100) -> None:
        self.device_id = device_id
        self.write = AsyncMock(
            return_value=WriteResult(
                status=WriteStatus.SUCCESS,
                point_name="setpoint",
                value=return_value,
            )
        )


class MockRepository:
    def __init__(self) -> None:
        self.create = AsyncMock(return_value="rec_1")
        self.update_status = AsyncMock(return_value=True)
        self.get = AsyncMock(return_value=None)
        self.list_by_device = AsyncMock(return_value=[])


class NeverLeaderGate:
    """Test helper：永遠回 False。"""

    @property
    def is_leader(self) -> bool:
        return False


# ============== Regression：validation_rules=None 等同舊行為 ==============


class TestNoRulesRegression:
    async def test_default_none_passes_through(self) -> None:
        repo = MockRepository()
        manager = WriteCommandManager(repo)  # 舊呼叫形式
        device = MockDevice("d1")
        manager.subscribe(device)

        cmd = WriteCommand(device_id="d1", point_name="sp", value=999)
        result = await manager.execute(cmd)

        assert result.status == WriteStatus.SUCCESS
        device.write.assert_awaited_once_with(name="sp", value=999, verify=False)

    async def test_empty_sequence_same_as_none(self) -> None:
        repo = MockRepository()
        manager = WriteCommandManager(repo, validation_rules=[])
        device = MockDevice("d1")
        manager.subscribe(device)

        cmd = WriteCommand(device_id="d1", point_name="sp", value=42)
        result = await manager.execute(cmd)
        assert result.status == WriteStatus.SUCCESS


# ============== Sequence 全域 rule：套所有 point ==============


class TestSequenceGlobalRules:
    async def test_sequence_rule_rejects(self) -> None:
        repo = MockRepository()
        rules = [RangeRule(min_value=0, max_value=100, clamp=False)]
        manager = WriteCommandManager(repo, validation_rules=rules)
        device = MockDevice("d1")
        manager.subscribe(device)

        cmd = WriteCommand(device_id="d1", point_name="sp", value=150)
        result = await manager.execute(cmd)

        assert result.status == WriteStatus.VALIDATION_FAILED
        assert result.value == 150  # reject 時保留原值
        assert "above max" in result.error_message
        device.write.assert_not_awaited()  # 關鍵：不能碰到設備
        # 驗證 DB 稽核：先 create pending，再 update_status(VALIDATION_FAILED)
        repo.create.assert_awaited_once()
        repo.update_status.assert_awaited_once()
        update_args = repo.update_status.await_args
        assert update_args.args[1] == CommandStatus.VALIDATION_FAILED

    async def test_sequence_rule_clamps_and_writes(self) -> None:
        repo = MockRepository()
        rules = [RangeRule(min_value=0, max_value=100, clamp=True)]
        manager = WriteCommandManager(repo, validation_rules=rules)
        device = MockDevice("d1")
        manager.subscribe(device)

        cmd = WriteCommand(device_id="d1", point_name="sp", value=150)
        result = await manager.execute(cmd)

        assert result.status == WriteStatus.SUCCESS
        # 傳給 device.write 的 value 應是 clamp 後的 100
        device.write.assert_awaited_once_with(name="sp", value=100, verify=False)

    async def test_chain_stops_at_first_reject(self) -> None:
        """鏈中多條 rule，第一條 reject 後面不跑。"""
        repo = MockRepository()
        second_rule_called = {"hit": False}

        class Spy:
            def apply(self, point_name: str, value: Any) -> ValidationResult:
                second_rule_called["hit"] = True
                return ValidationResult.accept(value)

        rules = [RangeRule(min_value=0, max_value=10, clamp=False), Spy()]
        manager = WriteCommandManager(repo, validation_rules=rules)
        manager.subscribe(MockDevice("d1"))

        cmd = WriteCommand(device_id="d1", point_name="sp", value=999)
        result = await manager.execute(cmd)
        assert result.status == WriteStatus.VALIDATION_FAILED
        assert second_rule_called["hit"] is False

    async def test_chain_clamp_accumulates(self) -> None:
        """多條 clamp rule 串接，effective_value 沿鏈累積。"""
        repo = MockRepository()
        rules = [
            RangeRule(min_value=0, max_value=200, clamp=True),  # 500 → 200
            RangeRule(min_value=0, max_value=100, clamp=True),  # 200 → 100
        ]
        manager = WriteCommandManager(repo, validation_rules=rules)
        device = MockDevice("d1")
        manager.subscribe(device)

        cmd = WriteCommand(device_id="d1", point_name="sp", value=500)
        result = await manager.execute(cmd)
        assert result.status == WriteStatus.SUCCESS
        device.write.assert_awaited_once_with(name="sp", value=100, verify=False)


# ============== Mapping per-point rule ==============


class TestMappingPerPointRules:
    async def test_mapping_hit(self) -> None:
        repo = MockRepository()
        rules = {"active_power": RangeRule(min_value=0, max_value=100)}
        manager = WriteCommandManager(repo, validation_rules=rules)
        manager.subscribe(MockDevice("d1"))

        cmd = WriteCommand(device_id="d1", point_name="active_power", value=150)
        result = await manager.execute(cmd)
        assert result.status == WriteStatus.VALIDATION_FAILED

    async def test_mapping_miss_passes_through(self) -> None:
        """point_name 未在 Mapping 中 → 不套驗證。"""
        repo = MockRepository()
        rules = {"active_power": RangeRule(min_value=0, max_value=100)}
        manager = WriteCommandManager(repo, validation_rules=rules)
        device = MockDevice("d1")
        manager.subscribe(device)

        cmd = WriteCommand(device_id="d1", point_name="other_point", value=9999)
        result = await manager.execute(cmd)
        assert result.status == WriteStatus.SUCCESS
        device.write.assert_awaited_once_with(name="other_point", value=9999, verify=False)


# ============== Leader gate 優先序 ==============


class TestLeaderGateVsValidation:
    async def test_not_leader_skips_validation(self) -> None:
        """非 leader 時 validation 鏈不該被觸發（leader gate 早期拒絕優先）。"""
        repo = MockRepository()
        rule_called = {"hit": False}

        class Spy:
            def apply(self, point_name: str, value: Any) -> ValidationResult:
                rule_called["hit"] = True
                return ValidationResult.accept(value)

        gate: LeaderGate = NeverLeaderGate()
        manager = WriteCommandManager(repo, leader_gate=gate, validation_rules=[Spy()])
        manager.subscribe(MockDevice("d1"))

        cmd = WriteCommand(device_id="d1", point_name="sp", value=1)
        with pytest.raises(NotLeaderError):
            await manager.execute(cmd)

        assert rule_called["hit"] is False
        repo.create.assert_not_awaited()  # leader gate 在 repository.create 之前擋

    async def test_leader_runs_validation(self) -> None:
        repo = MockRepository()
        manager = WriteCommandManager(
            repo,
            leader_gate=AlwaysLeaderGate(),
            validation_rules=[RangeRule(min_value=0, max_value=100, clamp=False)],
        )
        manager.subscribe(MockDevice("d1"))

        cmd = WriteCommand(device_id="d1", point_name="sp", value=9999)
        result = await manager.execute(cmd)
        assert result.status == WriteStatus.VALIDATION_FAILED


# ============== Device 未找到優先序 ==============


class TestLegacyTupleRuleGuard:
    """Rule 若誤回 tuple（例：WriteRule.apply 未經 adapter 包裝）必須被 runtime guard 擋住。"""

    async def test_legacy_tuple_rule_raises_typeerror(self) -> None:
        class LegacyTupleRule:
            """Simulates modbus_gateway.WriteRule.apply() legacy tuple interface."""

            def apply(self, point_name: str, value: Any) -> tuple[Any, bool]:  # type: ignore[override]
                return value, False

        repo = MockRepository()
        manager = WriteCommandManager(repo, validation_rules=[LegacyTupleRule()])
        manager.subscribe(MockDevice("d1"))

        cmd = WriteCommand(device_id="d1", point_name="sp", value=1)
        with pytest.raises(TypeError, match="must return ValidationResult"):
            await manager.execute(cmd)


class TestDeviceLookupVsValidation:
    async def test_unknown_device_reports_device_not_found_before_validation(self) -> None:
        """設備未註冊時應回 DEVICE_NOT_FOUND，不應該先跑驗證。

        設計意圖：validation 需要 point_name 與設備能力對齊，裝置不在就先跳。
        """
        repo = MockRepository()
        rule_called = {"hit": False}

        class Spy:
            def apply(self, point_name: str, value: Any) -> ValidationResult:
                rule_called["hit"] = True
                return ValidationResult.accept(value)

        manager = WriteCommandManager(repo, validation_rules=[Spy()])
        # 不註冊任何 device

        cmd = WriteCommand(device_id="missing", point_name="sp", value=1)
        result = await manager.execute(cmd)

        assert result.status == WriteStatus.WRITE_FAILED
        assert rule_called["hit"] is False
