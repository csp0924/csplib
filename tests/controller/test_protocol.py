# =============== Controller Protocol Tests ===============
#
# 測試 GridControllerProtocol、StrategyAwareGridControllerProtocol 與 GridControllerBase

import pytest

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.protocol import (
    GridControllerBase,
    GridControllerProtocol,
    StrategyAwareGridControllerProtocol,
)

# =============== GridControllerProtocol Tests ===============


class TestGridControllerProtocol:
    """GridControllerProtocol 協定測試（僅 start/stop 生命週期介面）"""

    def test_is_runtime_checkable(self):
        """Protocol 應標記為 @runtime_checkable"""
        assert (
            hasattr(GridControllerProtocol, "__protocol_attrs__")
            or hasattr(GridControllerProtocol, "__callable_proto_members_only__")
            or callable(getattr(GridControllerProtocol, "_is_runtime_protocol", None))
        )

        class Dummy:
            pass

        result = isinstance(Dummy(), GridControllerProtocol)
        assert result is False

    def test_conforming_class_passes_isinstance(self):
        """實作 start/stop 的類別應通過 isinstance 檢查"""

        class ConformingController:
            async def start(self):
                pass

            async def stop(self):
                pass

        controller = ConformingController()
        assert isinstance(controller, GridControllerProtocol)

    def test_missing_start_fails_isinstance(self):
        """缺少 start 的類別不應通過 isinstance 檢查"""

        class MissingStart:
            async def stop(self):
                pass

        controller = MissingStart()
        assert not isinstance(controller, GridControllerProtocol)

    def test_missing_stop_fails_isinstance(self):
        """缺少 stop 的類別不應通過 isinstance 檢查"""

        class MissingStop:
            async def start(self):
                pass

        controller = MissingStop()
        assert not isinstance(controller, GridControllerProtocol)

    def test_empty_class_fails_isinstance(self):
        """空類別不應通過 isinstance 檢查"""

        class EmptyClass:
            pass

        assert not isinstance(EmptyClass(), GridControllerProtocol)

    def test_set_strategy_not_required(self):
        """v0.9.x 後 set_strategy 已移至 StrategyAwareGridControllerProtocol，
        只實作 start/stop 仍應滿足 GridControllerProtocol。"""

        class LifecycleOnly:
            async def start(self):
                pass

            async def stop(self):
                pass

        assert isinstance(LifecycleOnly(), GridControllerProtocol)

    def test_protocol_has_expected_methods(self):
        """Protocol 應定義 start, stop 方法（不包含 set_strategy）"""
        assert hasattr(GridControllerProtocol, "start")
        assert hasattr(GridControllerProtocol, "stop")


# =============== StrategyAwareGridControllerProtocol Tests ===============


class TestStrategyAwareGridControllerProtocol:
    """StrategyAwareGridControllerProtocol 擴充協定測試（start/stop + set_strategy）"""

    def test_conforming_class_passes_isinstance(self):
        """實作所有三個方法的類別應通過 isinstance 檢查"""

        class ConformingController:
            def set_strategy(self, strategy):
                pass

            async def start(self):
                pass

            async def stop(self):
                pass

        controller = ConformingController()
        assert isinstance(controller, StrategyAwareGridControllerProtocol)
        # 同時也必須符合 base protocol
        assert isinstance(controller, GridControllerProtocol)

    def test_missing_set_strategy_fails(self):
        """只有 start/stop 的類別不應通過 StrategyAware 檢查"""

        class LifecycleOnly:
            async def start(self):
                pass

            async def stop(self):
                pass

        controller = LifecycleOnly()
        assert not isinstance(controller, StrategyAwareGridControllerProtocol)
        # 但仍符合 base protocol
        assert isinstance(controller, GridControllerProtocol)

    def test_partial_implementation_fails_isinstance(self):
        """只實作 set_strategy 不實作生命週期的類別不應通過檢查"""

        class PartialController:
            def set_strategy(self, strategy):
                pass

        controller = PartialController()
        assert not isinstance(controller, StrategyAwareGridControllerProtocol)

    def test_non_callable_attributes_pass_isinstance(self):
        """runtime_checkable Protocol 只檢查屬性存在性"""

        class NonCallableAttrs:
            set_strategy = "not a method"
            start = "not a method"
            stop = "not a method"

        controller = NonCallableAttrs()
        assert isinstance(controller, StrategyAwareGridControllerProtocol)

    def test_protocol_has_expected_methods(self):
        """StrategyAware 協定應定義 set_strategy, start, stop"""
        assert hasattr(StrategyAwareGridControllerProtocol, "set_strategy")
        assert hasattr(StrategyAwareGridControllerProtocol, "start")
        assert hasattr(StrategyAwareGridControllerProtocol, "stop")


# =============== GridControllerBase Tests ===============


class TestGridControllerBase:
    """GridControllerBase ABC 測試"""

    def test_is_abstract_class(self):
        """GridControllerBase 應為抽象類別，無法直接實例化"""
        with pytest.raises(TypeError, match="abstract method"):
            GridControllerBase()

    def test_has_abstract_build_context(self):
        """應有抽象方法 _build_context"""
        assert "_build_context" in GridControllerBase.__abstractmethods__

    def test_has_abstract_send_command(self):
        """應有抽象方法 _send_command"""
        assert "_send_command" in GridControllerBase.__abstractmethods__

    def test_concrete_subclass_can_be_instantiated(self):
        """實作所有抽象方法後可以實例化"""

        class ConcreteController(GridControllerBase):
            def _build_context(self) -> StrategyContext:
                return StrategyContext()

            async def _send_command(self, command: Command) -> None:
                pass

        controller = ConcreteController()
        assert isinstance(controller, GridControllerBase)

    def test_partial_subclass_cannot_be_instantiated(self):
        """只實作部分抽象方法時無法實例化"""

        class PartialController(GridControllerBase):
            def _build_context(self) -> StrategyContext:
                return StrategyContext()

            # missing _send_command

        with pytest.raises(TypeError):
            PartialController()

    def test_concrete_subclass_build_context_returns_value(self):
        """_build_context 實作應回傳 StrategyContext"""

        class ConcreteController(GridControllerBase):
            def _build_context(self) -> StrategyContext:
                return StrategyContext(soc=85.0)

            async def _send_command(self, command: Command) -> None:
                pass

        controller = ConcreteController()
        ctx = controller._build_context()
        assert isinstance(ctx, StrategyContext)
        assert ctx.soc == 85.0

    async def test_concrete_subclass_send_command(self):
        """_send_command 實作應能接收 Command"""
        sent_commands: list[Command] = []

        class ConcreteController(GridControllerBase):
            def _build_context(self) -> StrategyContext:
                return StrategyContext()

            async def _send_command(self, command: Command) -> None:
                sent_commands.append(command)

        controller = ConcreteController()
        cmd = Command(p_target=100.0, q_target=50.0)
        await controller._send_command(cmd)

        assert len(sent_commands) == 1
        assert sent_commands[0].p_target == 100.0
        assert sent_commands[0].q_target == 50.0

    def test_abstract_methods_count(self):
        """應恰好有 2 個抽象方法"""
        assert len(GridControllerBase.__abstractmethods__) == 2

    def test_is_subclass_of_abc(self):
        """GridControllerBase 應為 ABC 的子類別"""
        from abc import ABC

        assert issubclass(GridControllerBase, ABC)


# =============== Protocol & Base Interaction Tests ===============


class TestProtocolAndBaseInteraction:
    """Protocol 與 Base 交互測試"""

    def test_base_subclass_satisfies_strategy_aware_protocol_when_complete(self):
        """繼承 GridControllerBase 並實作 set_strategy/start/stop 時應滿足 StrategyAware Protocol"""

        class FullController(GridControllerBase):
            def _build_context(self) -> StrategyContext:
                return StrategyContext()

            async def _send_command(self, command: Command) -> None:
                pass

            def set_strategy(self, strategy) -> None:
                pass

            async def start(self) -> None:
                pass

            async def stop(self) -> None:
                pass

        controller = FullController()
        assert isinstance(controller, StrategyAwareGridControllerProtocol)
        assert isinstance(controller, GridControllerProtocol)
        assert isinstance(controller, GridControllerBase)

    def test_base_subclass_with_only_lifecycle_satisfies_base_protocol(self):
        """僅實作 start/stop 的 base 子類別符合 GridControllerProtocol 但不符合 StrategyAware"""

        class LifecycleController(GridControllerBase):
            def _build_context(self) -> StrategyContext:
                return StrategyContext()

            async def _send_command(self, command: Command) -> None:
                pass

            async def start(self) -> None:
                pass

            async def stop(self) -> None:
                pass

        controller = LifecycleController()
        assert isinstance(controller, GridControllerBase)
        assert isinstance(controller, GridControllerProtocol)
        assert not isinstance(controller, StrategyAwareGridControllerProtocol)
