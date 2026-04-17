"""Tests for WritePipeline — validator chain, WriteRule clamp/reject, writable gate."""

from unittest.mock import MagicMock

from csp_lib.modbus.types.numeric import UInt16
from csp_lib.modbus_gateway.config import (
    GatewayRegisterDef,
    GatewayServerConfig,
    WriteRule,
)
from csp_lib.modbus_gateway.errors import RegisterNotWritableError, WriteRejectedError
from csp_lib.modbus_gateway.pipeline import WritePipeline
from csp_lib.modbus_gateway.register_map import GatewayRegisterMap

# ===========================================================================
# Helpers
# ===========================================================================


def _make_pipeline(
    register_defs: list[GatewayRegisterDef] | None = None,
    write_rules: dict[str, WriteRule] | None = None,
) -> tuple[WritePipeline, GatewayRegisterMap]:
    """Create a WritePipeline with a backing GatewayRegisterMap.

    v0.7.3 SEC-006: 預設 HOLDING register 加 writable=True，
    確保既有寫入測試不會因 writable gate 全部被拒。
    """
    cfg = GatewayServerConfig(host="127.0.0.1", port=502, register_space_size=1000)
    if register_defs is None:
        register_defs = [
            GatewayRegisterDef(name="power", address=0, data_type=UInt16(), initial_value=0, writable=True),
            GatewayRegisterDef(name="voltage", address=10, data_type=UInt16(), initial_value=0, writable=True),
        ]
    rmap = GatewayRegisterMap(cfg, register_defs)
    pipeline = WritePipeline(rmap, write_rules=write_rules)
    return pipeline, rmap


# ===========================================================================
# Basic write processing
# ===========================================================================


class TestPipelineBasicWrite:
    def test_write_updates_register(self):
        pipeline, rmap = _make_pipeline()
        # Write raw value 500 to address 0 (power register)
        changes = pipeline.process_write(0, [500])
        assert rmap.get_value("power") == 500
        assert len(changes) == 1
        assert changes[0] == ("power", 0, 500)

    def test_write_to_unregistered_address_returns_empty(self):
        pipeline, _ = _make_pipeline()
        # Address 50 has no register
        changes = pipeline.process_write(50, [123])
        assert changes == []

    def test_write_same_value_no_change(self):
        pipeline, rmap = _make_pipeline()
        rmap.set_value("power", 100)
        # Write same value
        changes = pipeline.process_write(0, [100])
        assert changes == []  # no change detected


# ===========================================================================
# WriteRule: clamp mode
# ===========================================================================


class TestPipelineWriteRuleClamp:
    def test_clamp_below_min(self):
        rules = {"power": WriteRule(register_name="power", min_value=10, max_value=1000, clamp=True)}
        pipeline, rmap = _make_pipeline(write_rules=rules)
        changes = pipeline.process_write(0, [5])  # below min
        assert rmap.get_value("power") == 10  # clamped to min
        assert len(changes) == 1

    def test_clamp_above_max(self):
        rules = {"power": WriteRule(register_name="power", min_value=0, max_value=500, clamp=True)}
        pipeline, rmap = _make_pipeline(write_rules=rules)
        pipeline.process_write(0, [999])  # above max
        assert rmap.get_value("power") == 500  # clamped to max

    def test_clamp_within_range_no_change(self):
        rules = {"power": WriteRule(register_name="power", min_value=0, max_value=1000, clamp=True)}
        pipeline, rmap = _make_pipeline(write_rules=rules)
        pipeline.process_write(0, [250])
        assert rmap.get_value("power") == 250


# ===========================================================================
# WriteRule: reject mode
# ===========================================================================


class TestPipelineWriteRuleReject:
    def test_reject_below_min(self):
        rules = {"power": WriteRule(register_name="power", min_value=10, max_value=1000, clamp=False)}
        pipeline, rmap = _make_pipeline(write_rules=rules)
        changes = pipeline.process_write(0, [5])  # below min
        # Rejected: register not updated (stays 0)
        assert rmap.get_value("power") == 0
        assert changes == []

    def test_reject_above_max(self):
        rules = {"power": WriteRule(register_name="power", min_value=0, max_value=500, clamp=False)}
        pipeline, rmap = _make_pipeline(write_rules=rules)
        changes = pipeline.process_write(0, [999])  # above max
        assert rmap.get_value("power") == 0  # not updated
        assert changes == []

    def test_accept_within_range(self):
        rules = {"power": WriteRule(register_name="power", min_value=0, max_value=1000, clamp=False)}
        pipeline, rmap = _make_pipeline(write_rules=rules)
        changes = pipeline.process_write(0, [250])
        assert rmap.get_value("power") == 250
        assert len(changes) == 1


# ===========================================================================
# WriteRule: one-sided bounds
# ===========================================================================


class TestPipelineWriteRuleOneSided:
    def test_min_only(self):
        rules = {"power": WriteRule(register_name="power", min_value=10, clamp=True)}
        pipeline, rmap = _make_pipeline(write_rules=rules)
        pipeline.process_write(0, [5])
        assert rmap.get_value("power") == 10  # clamped

    def test_max_only(self):
        rules = {"power": WriteRule(register_name="power", max_value=500, clamp=True)}
        pipeline, rmap = _make_pipeline(write_rules=rules)
        pipeline.process_write(0, [999])
        assert rmap.get_value("power") == 500  # clamped


# ===========================================================================
# Validator chain
# ===========================================================================


class TestPipelineValidatorChain:
    def test_validator_accept(self):
        pipeline, rmap = _make_pipeline()
        validator = MagicMock()
        validator.validate.return_value = True
        pipeline.add_validator(validator)
        changes = pipeline.process_write(0, [100])
        validator.validate.assert_called_once_with("power", 100)
        assert rmap.get_value("power") == 100
        assert len(changes) == 1

    def test_validator_reject(self):
        pipeline, rmap = _make_pipeline()
        validator = MagicMock()
        validator.validate.return_value = False
        pipeline.add_validator(validator)
        changes = pipeline.process_write(0, [100])
        assert rmap.get_value("power") == 0  # not updated
        assert changes == []

    def test_multiple_validators_first_rejects(self):
        """If the first validator rejects, the second should not be called."""
        pipeline, rmap = _make_pipeline()
        v1 = MagicMock()
        v1.validate.return_value = False
        v2 = MagicMock()
        v2.validate.return_value = True
        pipeline.add_validator(v1)
        pipeline.add_validator(v2)
        changes = pipeline.process_write(0, [100])
        v1.validate.assert_called_once()
        v2.validate.assert_not_called()
        assert changes == []

    def test_validator_runs_before_rule(self):
        """Validator rejects -> WriteRule is never reached."""
        rules = {"power": WriteRule(register_name="power", min_value=0, max_value=1000, clamp=True)}
        pipeline, rmap = _make_pipeline(write_rules=rules)
        validator = MagicMock()
        validator.validate.return_value = False
        pipeline.add_validator(validator)
        changes = pipeline.process_write(0, [500])
        assert changes == []
        assert rmap.get_value("power") == 0


# ===========================================================================
# Hook management
# ===========================================================================


class TestPipelineHooks:
    def test_add_hook(self):
        pipeline, _ = _make_pipeline()
        hook = MagicMock()
        pipeline.add_hook(hook)
        assert hook in pipeline.hooks

    def test_hooks_list_is_copy(self):
        pipeline, _ = _make_pipeline()
        hook = MagicMock()
        pipeline.add_hook(hook)
        hooks_copy = pipeline.hooks
        hooks_copy.clear()
        assert len(pipeline.hooks) == 1  # original not affected


# ===========================================================================
# v0.7.3 SEC-006: writable gate
# ===========================================================================


class TestPipelineWritableGate:
    """v0.7.3 SEC-006: WritePipeline 在 validator chain 前檢查 writable 旗標。

    修復前：所有 HOLDING register 預設可寫，EMS 可寫任意暫存器。
    修復後：writable=False（預設）的 HOLDING register 直接拒絕寫入。
    """

    def test_writable_false_rejects_write(self):
        """writable=False 的 register 應被拒絕，回傳空 changes list。"""
        regs = [
            GatewayRegisterDef(name="readonly_cmd", address=0, data_type=UInt16(), writable=False),
        ]
        pipeline, rmap = _make_pipeline(register_defs=regs)
        changes = pipeline.process_write(0, [500])
        assert changes == []
        # register 值不應被更新
        assert rmap.get_value("readonly_cmd") == 0

    def test_writable_false_still_returns_empty(self):
        """writable=False 拒絕寫入，回傳空 changes，register 保持初始值。"""
        regs = [
            GatewayRegisterDef(name="locked_reg", address=0, data_type=UInt16(), writable=False, initial_value=42),
        ]
        pipeline, rmap = _make_pipeline(register_defs=regs)
        changes = pipeline.process_write(0, [100])
        assert changes == []
        assert rmap.get_value("locked_reg") == 42  # 仍為初始值

    def test_writable_true_allows_write(self):
        """writable=True 的 register 正常寫入。"""
        regs = [
            GatewayRegisterDef(name="cmd", address=0, data_type=UInt16(), writable=True),
        ]
        pipeline, rmap = _make_pipeline(register_defs=regs)
        changes = pipeline.process_write(0, [500])
        assert len(changes) == 1
        assert rmap.get_value("cmd") == 500

    def test_writable_true_still_requires_validator_pass(self):
        """writable=True 但 validator 拒絕 → 仍然 reject。"""
        regs = [
            GatewayRegisterDef(name="cmd", address=0, data_type=UInt16(), writable=True),
        ]
        pipeline, rmap = _make_pipeline(register_defs=regs)
        validator = MagicMock()
        validator.validate.return_value = False
        pipeline.add_validator(validator)

        changes = pipeline.process_write(0, [500])
        assert changes == []
        assert rmap.get_value("cmd") == 0

    def test_register_not_writable_error_is_write_rejected_error(self):
        """RegisterNotWritableError 應是 WriteRejectedError 的子類。"""
        err = RegisterNotWritableError("test_reg", 100)
        assert isinstance(err, WriteRejectedError)
        assert err.register_name == "test_reg"
        assert err.address == 100

    def test_writable_gate_is_before_validators(self):
        """writable=False 應在 validator 之前被拒絕，validator 不被呼叫。"""
        regs = [
            GatewayRegisterDef(name="locked", address=0, data_type=UInt16(), writable=False),
        ]
        pipeline, _ = _make_pipeline(register_defs=regs)
        validator = MagicMock()
        validator.validate.return_value = True
        pipeline.add_validator(validator)

        pipeline.process_write(0, [100])
        # validator 不應被呼叫（writable gate 先攔截）
        validator.validate.assert_not_called()

    def test_mixed_writable_registers(self):
        """混合 writable=True/False 的 register，只有可寫的被更新。"""
        regs = [
            GatewayRegisterDef(name="writable_cmd", address=0, data_type=UInt16(), writable=True),
            GatewayRegisterDef(name="readonly_status", address=1, data_type=UInt16(), writable=False),
        ]
        pipeline, rmap = _make_pipeline(register_defs=regs)
        # 寫入跨兩個 register 的 range
        changes = pipeline.process_write(0, [500, 999])
        # 只有 writable_cmd 應被更新
        assert rmap.get_value("writable_cmd") == 500
        assert rmap.get_value("readonly_status") == 0
        assert len(changes) == 1
        assert changes[0][0] == "writable_cmd"
