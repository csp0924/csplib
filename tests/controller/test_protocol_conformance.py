# =============== Controller Protocol Conformance Tests ===============
#
# 驗證具體 controller 實作是否結構性滿足 GridControllerProtocol。
# 特別確認 mode-based 的 SystemController（不實作 set_strategy）
# 在 v0.9.x 後仍滿足簡化後的生命週期協定。

from __future__ import annotations

from csp_lib.controller.protocol import (
    GridControllerProtocol,
    StrategyAwareGridControllerProtocol,
)
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.system_controller import (
    SystemController,
    SystemControllerConfig,
)


class TestSystemControllerConformance:
    """SystemController 對 GridControllerProtocol 的結構性一致性測試"""

    def _make_controller(self) -> SystemController:
        registry = DeviceRegistry()
        config = SystemControllerConfig()
        return SystemController(registry, config)

    def test_system_controller_satisfies_grid_controller_protocol(self):
        """SystemController 實例應結構性滿足 GridControllerProtocol（start/stop）"""
        controller = self._make_controller()
        assert isinstance(controller, GridControllerProtocol)

    def test_system_controller_has_lifecycle_methods(self):
        """SystemController 應具備 start/stop 方法（來自 AsyncLifecycleMixin）"""
        controller = self._make_controller()
        assert callable(getattr(controller, "start", None))
        assert callable(getattr(controller, "stop", None))

    def test_system_controller_does_not_satisfy_strategy_aware_protocol(self):
        """SystemController 不實作 set_strategy（使用 mode-based API），
        因此不應滿足 StrategyAwareGridControllerProtocol。"""
        controller = self._make_controller()
        assert not isinstance(controller, StrategyAwareGridControllerProtocol)
        # 確認確實沒有 set_strategy 屬性
        assert not hasattr(controller, "set_strategy")

    def test_system_controller_has_mode_based_api(self):
        """SystemController 應提供 mode-based 的策略管理 API 取代 set_strategy"""
        controller = self._make_controller()
        assert callable(getattr(controller, "register_mode", None))
        assert callable(getattr(controller, "set_base_mode", None))
