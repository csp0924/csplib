# =============== Modes / Protection API NO_CHANGE Serialization Tests (v0.8.0 WI-V080-004) ===============
#
# 驗證 GUI API 對 ``Command(p_target=NO_CHANGE)`` 的 JSON 序列化：
#   - /api/protection 回傳 ``p_target: null`` 不會 crash
#   - _serialize_target 單元測試（float / NO_CHANGE / None-ish）
#
# 採用既有 GUI conftest 的 client fixture 搭配 protection_guard._last_result 注入。

from __future__ import annotations

import pytest

from csp_lib.controller.core import Command
from csp_lib.controller.core.command import NO_CHANGE
from csp_lib.controller.system.protection import ProtectionResult
from csp_lib.gui.api.modes import _serialize_target

# =============== _serialize_target 單元 ===============


class TestSerializeTarget:
    """_serialize_target helper: float → float；NO_CHANGE → None"""

    def test_float_returns_float(self):
        assert _serialize_target(100.0) == 100.0

    def test_zero_float_returns_zero(self):
        """0.0 是合法 setpoint 不能混淆為 NO_CHANGE"""
        assert _serialize_target(0.0) == 0.0

    def test_negative_float(self):
        assert _serialize_target(-50.5) == -50.5

    def test_no_change_returns_none(self):
        assert _serialize_target(NO_CHANGE) is None


# =============== /api/protection 端點 NO_CHANGE 序列化 ===============


@pytest.mark.asyncio
class TestProtectionApiNoChange:
    """/api/protection 回應 NO_CHANGE 軸以 JSON null 輸出，不 crash"""

    async def test_protection_status_with_no_change_p(self, client, mock_system_controller):
        """保護結果 protected_command.p_target=NO_CHANGE → JSON null"""
        # 注入 protection result
        result = ProtectionResult(
            original_command=Command(p_target=100.0, q_target=50.0),
            protected_command=Command(p_target=NO_CHANGE, q_target=50.0),
            triggered_rules=["test_rule"],
        )
        mock_system_controller.protection_guard._last_result = result

        resp = await client.get("/api/protection")
        assert resp.status_code == 200
        data = resp.json()

        assert data["was_modified"] is True
        assert data["triggered_rules"] == ["test_rule"]
        assert data["original_command"]["p_target"] == 100.0
        assert data["original_command"]["q_target"] == 50.0
        # NO_CHANGE 軸 JSON null
        assert data["protected_command"]["p_target"] is None
        assert data["protected_command"]["q_target"] == 50.0

    async def test_protection_status_with_no_change_both_axes(self, client, mock_system_controller):
        result = ProtectionResult(
            original_command=Command(p_target=NO_CHANGE, q_target=NO_CHANGE),
            protected_command=Command(p_target=NO_CHANGE, q_target=NO_CHANGE),
        )
        mock_system_controller.protection_guard._last_result = result

        resp = await client.get("/api/protection")
        assert resp.status_code == 200
        data = resp.json()

        assert data["original_command"]["p_target"] is None
        assert data["original_command"]["q_target"] is None
        assert data["protected_command"]["p_target"] is None
        assert data["protected_command"]["q_target"] is None

    async def test_protection_status_pure_float_unaffected(self, client, mock_system_controller):
        """純 float 命令不受 NO_CHANGE 編碼邏輯影響"""
        result = ProtectionResult(
            original_command=Command(p_target=200.0, q_target=-30.0),
            protected_command=Command(p_target=150.0, q_target=-30.0),
            triggered_rules=["soc_limit"],
        )
        mock_system_controller.protection_guard._last_result = result

        resp = await client.get("/api/protection")
        assert resp.status_code == 200
        data = resp.json()

        assert data["original_command"]["p_target"] == 200.0
        assert data["protected_command"]["p_target"] == 150.0
        assert data["was_modified"] is True

    async def test_protection_status_no_data_when_unset(self, client, mock_system_controller):
        """未執行過保護時 /api/protection 回傳 {status: no_data}，不觸發 NO_CHANGE 路徑"""
        # 清空 last_result
        mock_system_controller.protection_guard._last_result = None

        resp = await client.get("/api/protection")
        assert resp.status_code == 200
        assert resp.json() == {"status": "no_data"}
