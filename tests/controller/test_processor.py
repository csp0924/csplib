"""Tests for CommandProcessor Protocol."""

import pytest

from csp_lib.controller.core import Command, CommandProcessor, StrategyContext


class TestCommandProcessorProtocol:
    def test_conforming_class_isinstance(self):
        """A class with async process(command, context) -> Command satisfies the protocol."""

        class MyProcessor:
            async def process(self, command: Command, context: StrategyContext) -> Command:
                return command

        assert isinstance(MyProcessor(), CommandProcessor)

    def test_non_conforming_class_not_isinstance(self):
        """A class without process() does not satisfy the protocol."""

        class NotAProcessor:
            def do_something(self):
                pass

        assert not isinstance(NotAProcessor(), CommandProcessor)

    @pytest.mark.asyncio
    async def test_conforming_class_can_be_called(self):
        """Verify a conforming class can actually be awaited."""

        class Doubler:
            async def process(self, command: Command, context: StrategyContext) -> Command:
                return command.with_p(command.p_target * 2)

        proc = Doubler()
        cmd = Command(p_target=100.0, q_target=50.0)
        ctx = StrategyContext()
        result = await proc.process(cmd, ctx)
        assert result.p_target == pytest.approx(200.0)
        assert result.q_target == pytest.approx(50.0)
