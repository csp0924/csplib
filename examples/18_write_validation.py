"""
Example 18: Write Validation Rules — 寫入前驗證鏈

學習目標：
  - WriteValidationRule Protocol：跨層寫入驗證合約
  - 內建 RangeRule：min/max 範圍檢查（含 NaN/Inf guard）
  - WriteCommandManager 注入 validation_rules（Sequence 全域 / Mapping per-point）
  - Clamp vs Reject 語意差異
  - Custom rule 實作（Protocol 結構相容）

情境：
  - PCS 寫入 active_power（kW），安全範圍 [-100, 100]，超範圍 reject
  - PCS 寫入 voltage_setpoint（V），軟限制 [380, 420]，超範圍 clamp
  - 所有 point 共用：NaN/Inf sentinel 必須 reject（安全保護）

Run:
  uv run python examples/18_write_validation.py
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

from csp_lib.core import get_logger
from csp_lib.equipment.transport import (
    RangeRule,
    ValidationResult,
    WriteResult,
    WriteStatus,
    WriteValidationRule,
)
from csp_lib.manager import InMemoryCommandRepository, WriteCommandManager
from csp_lib.manager.command.schema import CommandStatus, WriteCommand

logger = get_logger(__name__)


# -------------------------------------------------------------------
# 1. Mock device — 正式使用時請替換為 AsyncModbusDevice
# -------------------------------------------------------------------


class MockPCS:
    """簡單的 mock 設備，模擬寫入成功。"""

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self.write = AsyncMock(
            side_effect=lambda name, value, verify: WriteResult(
                status=WriteStatus.SUCCESS,
                point_name=name,
                value=value,
            )
        )


# -------------------------------------------------------------------
# 2. Custom validation rule — 滿足 WriteValidationRule Protocol
# -------------------------------------------------------------------


class BlacklistRule:
    """黑名單 rule — 禁止某些 sentinel value（示範 custom rule）。

    結構相容 WriteValidationRule Protocol：只要有
    ``apply(point_name, value) -> ValidationResult`` 方法即可。
    """

    def __init__(self, blacklist: set[Any]) -> None:
        self._blacklist = blacklist

    def apply(self, point_name: str, value: Any) -> ValidationResult:
        if value in self._blacklist:
            return ValidationResult.reject(value, f"value {value!r} is blacklisted")
        return ValidationResult.accept(value)


# -------------------------------------------------------------------
# 3. Scenarios
# -------------------------------------------------------------------


async def scenario_per_point_rules() -> None:
    """Mapping[str, Rule] — 不同 point 不同規則。"""
    logger.info("=" * 60)
    logger.info("Scenario 1: per-point rules (Mapping)")
    logger.info("=" * 60)

    rules: dict[str, WriteValidationRule] = {
        "active_power": RangeRule(min_value=-100, max_value=100, clamp=False),
        "voltage_setpoint": RangeRule(min_value=380, max_value=420, clamp=True),
    }

    manager = WriteCommandManager(
        repository=InMemoryCommandRepository(),
        validation_rules=rules,
    )
    manager.subscribe(MockPCS("pcs_001"))

    # 3-1. active_power 超上限 → reject
    cmd = WriteCommand(device_id="pcs_001", point_name="active_power", value=150)
    result = await manager.execute(cmd)
    logger.info(f"  active_power=150 → status={result.status.value}, reason={result.error_message!r}")
    assert result.status == WriteStatus.VALIDATION_FAILED

    # 3-2. voltage_setpoint 超上限 → clamp 到 420
    cmd = WriteCommand(device_id="pcs_001", point_name="voltage_setpoint", value=450)
    result = await manager.execute(cmd)
    logger.info(f"  voltage_setpoint=450 → status={result.status.value}, value={result.value}")
    assert result.status == WriteStatus.SUCCESS
    assert result.value == 420  # clamped

    # 3-3. 未列名的 point → pass-through
    cmd = WriteCommand(device_id="pcs_001", point_name="heartbeat", value=1)
    result = await manager.execute(cmd)
    logger.info(f"  heartbeat=1（未列規則）→ status={result.status.value}")
    assert result.status == WriteStatus.SUCCESS


async def scenario_global_chain() -> None:
    """Sequence[Rule] — 每條 rule 對所有 point 套用，鏈式累積 effective_value。"""
    logger.info("=" * 60)
    logger.info("Scenario 2: global rule chain (Sequence)")
    logger.info("=" * 60)

    rules: list[WriteValidationRule] = [
        BlacklistRule(blacklist={-1, 9999}),  # 先擋 sentinel
        RangeRule(min_value=0, max_value=100, clamp=True),  # 再 clamp 到範圍
    ]
    manager = WriteCommandManager(
        repository=InMemoryCommandRepository(),
        validation_rules=rules,
    )
    manager.subscribe(MockPCS("pcs_002"))

    # 黑名單 sentinel 先被擋
    cmd = WriteCommand(device_id="pcs_002", point_name="sp", value=9999)
    result = await manager.execute(cmd)
    logger.info(f"  sp=9999 (sentinel) → status={result.status.value}, reason={result.error_message!r}")
    assert result.status == WriteStatus.VALIDATION_FAILED

    # 通過黑名單後再被 clamp
    cmd = WriteCommand(device_id="pcs_002", point_name="sp", value=150)
    result = await manager.execute(cmd)
    logger.info(f"  sp=150 → status={result.status.value}, clamped to {result.value}")
    assert result.status == WriteStatus.SUCCESS
    assert result.value == 100


async def scenario_nan_inf_guard() -> None:
    """NaN / Inf 永遠 reject — 對照 bug-lesson numerical-safety-layered。"""
    logger.info("=" * 60)
    logger.info("Scenario 3: NaN / Inf guard")
    logger.info("=" * 60)

    manager = WriteCommandManager(
        repository=InMemoryCommandRepository(),
        # 即使 clamp=True，NaN/Inf 仍 reject（不會被夾成 min/max）
        validation_rules=[RangeRule(min_value=0, max_value=100, clamp=True)],
    )
    manager.subscribe(MockPCS("pcs_003"))

    for bad in (float("nan"), float("inf"), float("-inf")):
        cmd = WriteCommand(device_id="pcs_003", point_name="sp", value=bad)
        result = await manager.execute(cmd)
        logger.info(f"  sp={bad!r} → status={result.status.value}, reason={result.error_message!r}")
        assert result.status == WriteStatus.VALIDATION_FAILED


async def scenario_audit_trail() -> None:
    """驗證失敗仍寫入完整稽核 — 觀察 repository 中的 VALIDATION_FAILED 記錄。"""
    logger.info("=" * 60)
    logger.info("Scenario 4: audit trail for rejected writes")
    logger.info("=" * 60)

    repo = InMemoryCommandRepository()
    manager = WriteCommandManager(
        repository=repo,
        validation_rules=[RangeRule(min_value=0, max_value=100, clamp=False)],
    )
    manager.subscribe(MockPCS("pcs_004"))

    cmd = WriteCommand(device_id="pcs_004", point_name="sp", value=500)
    await manager.execute(cmd)

    record = await repo.get(cmd.command_id)
    assert record is not None
    assert record.status == CommandStatus.VALIDATION_FAILED
    logger.info(f"  CommandRecord status      = {record.status.value}")
    logger.info(f"  CommandRecord error_msg   = {record.error_message}")
    logger.info(f"  CommandRecord result      = {record.result}")
    logger.info("  ✔ 拒絕的指令完整留存，供後續稽核 / 告警對照")


async def main() -> None:
    await scenario_per_point_rules()
    await scenario_global_chain()
    await scenario_nan_inf_guard()
    await scenario_audit_trail()
    logger.info("所有情境執行完畢 ✔")


if __name__ == "__main__":
    asyncio.run(main())
