"""Pipeline E：SystemCommandOrchestrator + MockDeviceProtocol（DeviceProtocol 鬆綁驗證）

驗證 SystemCommandOrchestrator 不依賴 AsyncModbusDevice。orchestrator 透過
``execute_action`` 觸發設備動作；MockDeviceProtocol 在 conftest 裡已暴露
``execute_action`` AsyncMock，回傳 success ActionResult。

注意：本檔刻意 **不 import** ``AsyncModbusDevice``。
"""

from __future__ import annotations

from csp_lib.integration.orchestrator import (
    CommandStep,
    SystemCommand,
    SystemCommandOrchestrator,
)
from csp_lib.integration.registry import DeviceRegistry


class TestOrchestratorAcceptsMockDeviceProtocol:
    async def test_execute_calls_execute_action_on_mock_device(self, mock_device_protocol) -> None:
        """register MockDevice → orchestrator.execute() → MockDevice.execute_action 被呼叫。"""
        reg = DeviceRegistry()
        reg.register(mock_device_protocol)

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="boot",
                steps=[
                    CommandStep(
                        action="start",
                        device_ids=[mock_device_protocol.device_id],
                        params={"mode": "auto"},
                    )
                ],
            )
        )

        result = await orch.execute("boot")
        assert result.status == "success"

        mock_device_protocol.execute_action.assert_awaited_once_with("start", mode="auto")

    async def test_execute_with_trait_targets_multiple_mock_devices(self, make_mock_device_protocol) -> None:
        """trait 路徑：所有匹配的 MockDevice 都被觸發 execute_action。"""
        dev1 = make_mock_device_protocol("mock_pcs_1")
        dev2 = make_mock_device_protocol("mock_pcs_2")
        reg = DeviceRegistry()
        reg.register(dev1, traits=["pcs"])
        reg.register(dev2, traits=["pcs"])

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="start_all",
                steps=[CommandStep(action="start", trait="pcs")],
            )
        )

        result = await orch.execute("start_all")
        assert result.status == "success"

        dev1.execute_action.assert_awaited_once_with("start")
        dev2.execute_action.assert_awaited_once_with("start")

    async def test_execute_skips_device_without_execute_action(self, make_mock_device_protocol, monkeypatch) -> None:
        """若 MockDevice 沒有 ``execute_action``（移除掉），orchestrator 應記錄
        'action not supported' 而非崩潰。"""
        dev = make_mock_device_protocol("dev_no_action")
        # 移除 execute_action 屬性，模擬非 ActionDevice 的純 DeviceProtocol
        # MagicMock auto-attrs 仍會自動產生屬性，因此用 monkeypatch 直接 setattr None
        monkeypatch.setattr(dev, "execute_action", None, raising=False)

        reg = DeviceRegistry()
        reg.register(dev)

        orch = SystemCommandOrchestrator(reg)
        orch.register(
            SystemCommand(
                name="cmd",
                steps=[CommandStep(action="start", device_ids=[dev.device_id])],
            )
        )

        result = await orch.execute("cmd")
        # 全部設備都不支援 action → 整體 success（沒人 fail）
        # device_results 應記錄 'action not supported'
        assert result.status == "success"
        step_result = result.step_results[0]
        assert step_result.device_results.get(dev.device_id) == "action not supported"
