# =============== Integration - System Command Orchestrator ===============
#
# 系統級指令編排器
#
# 定義多步驟、多設備的指令序列，支援：
#   - 有序步驟群組（先啟動 MBMS，再啟動 PCS）
#   - 步驟間延遲與健康檢查
#   - 失敗時中止整個序列
#
# 架構：
#   Trigger (Redis / API)
#        ↓
#   SystemCommandOrchestrator.execute("system_start")
#        ↓
#   Step 1: group="mbms", action="start"
#        ↓ delay + check
#   Step 2: group="pcs", action="start"
#        ↓
#   Result: SUCCESS / ABORTED

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from csp_lib.core import get_logger

if TYPE_CHECKING:
    from .registry import DeviceRegistry

logger = get_logger("csp_lib.integration.orchestrator")


# ========== Schema ==========


@dataclass(frozen=True)
class StepCheck:
    """
    步驟間健康/就緒檢查

    在步驟完成後輪詢設備屬性，直到全部通過或超時。

    Attributes:
        trait: 依 trait 選擇要檢查的設備（與 device_ids 二擇一）
        device_ids: 依 ID 選擇要檢查的設備
        check: 設備上要檢查的布林屬性名稱
        timeout: 最大等待時間（秒）
        poll_interval: 輪詢間隔（秒）
    """

    trait: str | None = None
    device_ids: list[str] | None = None
    check: str = "is_responsive"
    timeout: float = 10.0
    poll_interval: float = 0.5


@dataclass(frozen=True)
class CommandStep:
    """
    系統指令序列中的單一步驟

    Attributes:
        action: 設備動作名稱（如 "start"、"stop"）
        trait: 依 trait 選擇目標設備（與 device_ids 二擇一）
        device_ids: 依 ID 選擇目標設備
        params: 動作參數
        delay_before: 執行前延遲（秒）
        check_after: 步驟完成後的健康檢查
        description: 人類可讀描述
    """

    action: str
    trait: str | None = None
    device_ids: list[str] | None = None
    params: dict[str, Any] = field(default_factory=dict)
    delay_before: float = 0.0
    check_after: StepCheck | None = None
    description: str = ""


@dataclass(frozen=True)
class SystemCommand:
    """
    具名系統級指令，由有序步驟組成

    Attributes:
        name: 指令名稱（如 "system_start"、"system_stop"）
        steps: 步驟列表（依序執行）
        description: 人類可讀描述
    """

    name: str
    steps: list[CommandStep] = field(default_factory=list)
    description: str = ""


# ========== Result ==========


@dataclass
class StepResult:
    """
    單一步驟的執行結果

    Attributes:
        step_index: 步驟索引
        description: 步驟描述
        status: 執行狀態 ("success" | "failed" | "check_failed" | "skipped")
        device_results: 各設備的執行結果 (device_id → "success" | 錯誤訊息)
        check_passed: 健康檢查是否通過
        error_message: 錯誤訊息
    """

    step_index: int
    description: str
    status: str
    device_results: dict[str, str] = field(default_factory=dict)
    check_passed: bool | None = None
    error_message: str | None = None


@dataclass
class SystemCommandResult:
    """
    整個系統指令的執行結果

    Attributes:
        command_name: 指令名稱
        status: 執行狀態 ("success" | "aborted")
        step_results: 各步驟的結果
        aborted_at_step: 中止時的步驟索引
        error_message: 錯誤訊息
    """

    command_name: str
    status: str
    step_results: list[StepResult] = field(default_factory=list)
    aborted_at_step: int | None = None
    error_message: str | None = None


# ========== Orchestrator ==========


class SystemCommandOrchestrator:
    """
    系統級指令編排器

    將多步驟、多設備的指令序列編排為有序執行流程。
    每個步驟內的設備動作並行執行，步驟間支援延遲與健康檢查。
    任何步驟失敗則中止整個序列。

    Example::

        orchestrator = SystemCommandOrchestrator(registry)
        orchestrator.register(SystemCommand(
            name="system_start",
            steps=[
                CommandStep(action="start", trait="mbms",
                    check_after=StepCheck(trait="mbms", timeout=10.0)),
                CommandStep(action="start", trait="pcs", delay_before=2.0),
            ],
        ))
        result = await orchestrator.execute("system_start")
    """

    def __init__(self, registry: DeviceRegistry) -> None:
        self._registry = registry
        self._commands: dict[str, SystemCommand] = {}

    def register(self, command: SystemCommand) -> None:
        """註冊具名系統指令"""
        self._commands[command.name] = command
        logger.info(f"Registered system command: {command.name}")

    def unregister(self, name: str) -> None:
        """移除已註冊的系統指令"""
        if name in self._commands:
            del self._commands[name]

    async def execute(self, name: str) -> SystemCommandResult:
        """
        依名稱執行已註冊的系統指令

        Args:
            name: 系統指令名稱

        Returns:
            SystemCommandResult 執行結果

        Raises:
            KeyError: 指令未註冊
        """
        command = self._commands.get(name)
        if command is None:
            raise KeyError(f"System command '{name}' is not registered.")

        logger.info(f"Executing system command: {name}")
        step_results: list[StepResult] = []

        for i, step in enumerate(command.steps):
            step_result = await self._execute_step(i, step)
            step_results.append(step_result)

            if step_result.status in ("failed", "check_failed"):
                error_msg = f"Step {i} ({step.description or step.action}) failed: {step_result.error_message}"
                logger.error(f"System command '{name}' aborted: {error_msg}")
                return SystemCommandResult(
                    command_name=name,
                    status="aborted",
                    step_results=step_results,
                    aborted_at_step=i,
                    error_message=error_msg,
                )

        logger.info(f"System command '{name}' completed successfully.")
        return SystemCommandResult(
            command_name=name,
            status="success",
            step_results=step_results,
        )

    async def execute_from_dict(self, data: dict[str, Any]) -> SystemCommandResult:
        """
        從字典執行系統指令（用於 Redis 適配器整合）

        Args:
            data: 包含 "command_name" 或 "system_command" 的字典

        Returns:
            SystemCommandResult 執行結果
        """
        name = data.get("command_name") or data.get("system_command", "")
        return await self.execute(name)

    @property
    def registered_commands(self) -> list[str]:
        """已註冊的系統指令名稱列表"""
        return sorted(self._commands.keys())

    # ---- 內部方法 ----

    async def _execute_step(self, index: int, step: CommandStep) -> StepResult:
        """執行單一步驟"""
        desc = step.description or f"{step.action} (step {index})"

        # 1. 延遲
        if step.delay_before > 0:
            logger.debug(f"Step {index}: waiting {step.delay_before}s before execution")
            await asyncio.sleep(step.delay_before)

        # 2. 解析目標設備
        devices = self._resolve_devices(step.trait, step.device_ids)
        if not devices:
            return StepResult(
                step_index=index,
                description=desc,
                status="failed",
                error_message="No devices found for step",
            )

        # 3. 並行執行動作
        device_results: dict[str, str] = {}
        tasks = []
        device_ids_ordered = []
        for device in devices:
            device_ids_ordered.append(device.device_id)
            tasks.append(self._execute_device_action(device, step.action, step.params))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        has_failure = False
        failure_messages = []
        for device_id, result in zip(device_ids_ordered, results, strict=True):
            if isinstance(result, Exception):
                device_results[device_id] = str(result)
                has_failure = True
                failure_messages.append(f"{device_id}: {result}")
            elif result is not None and hasattr(result, "status"):
                # ActionResult from device.execute_action
                if result.status.value in ("success", "write_success"):
                    device_results[device_id] = "success"
                else:
                    error = result.error_message or result.status.value
                    device_results[device_id] = error
                    has_failure = True
                    failure_messages.append(f"{device_id}: {error}")
            else:
                device_results[device_id] = "success"

        if has_failure:
            error_msg = "; ".join(failure_messages)
            return StepResult(
                step_index=index,
                description=desc,
                status="failed",
                device_results=device_results,
                error_message=error_msg,
            )

        # 4. 健康檢查
        if step.check_after is not None:
            check_passed = await self._run_check(step.check_after)
            if not check_passed:
                return StepResult(
                    step_index=index,
                    description=desc,
                    status="check_failed",
                    device_results=device_results,
                    check_passed=False,
                    error_message=f"Health check '{step.check_after.check}' timed out after {step.check_after.timeout}s",
                )

        return StepResult(
            step_index=index,
            description=desc,
            status="success",
            device_results=device_results,
            check_passed=True if step.check_after is not None else None,
        )

    def _resolve_devices(self, trait: str | None, device_ids: list[str] | None) -> list:
        """解析目標設備（依 trait 或 device_ids）"""
        if trait is not None:
            return self._registry.get_devices_by_trait(trait)
        if device_ids is not None:
            devices = []
            for did in device_ids:
                device = self._registry.get_device(did)
                if device is not None:
                    devices.append(device)
                else:
                    logger.warning(f"Device '{did}' not found in registry, skipping.")
            return devices
        return []

    @staticmethod
    async def _execute_device_action(device: Any, action: str, params: dict[str, Any]) -> Any:
        """執行單一設備的動作"""
        return await device.execute_action(action, **params)

    async def _run_check(self, check: StepCheck) -> bool:
        """執行健康檢查，輪詢直到通過或超時"""
        devices = self._resolve_devices(check.trait, check.device_ids)
        if not devices:
            return True  # 無設備需檢查

        elapsed = 0.0
        while elapsed < check.timeout:
            all_passed = all(getattr(d, check.check, False) for d in devices)
            if all_passed:
                return True
            await asyncio.sleep(check.poll_interval)
            elapsed += check.poll_interval

        # 最終檢查
        return all(getattr(d, check.check, False) for d in devices)


__all__ = [
    "StepCheck",
    "CommandStep",
    "SystemCommand",
    "StepResult",
    "SystemCommandResult",
    "SystemCommandOrchestrator",
]
