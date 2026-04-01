"""Tests for CommandProcessor Protocol and pipeline integration."""

import pytest

from csp_lib.controller.core import Command, CommandProcessor, StrategyContext

# ─── Helper processors for pipeline tests ───


class ScaleProcessor:
    """Multiplies p_target by a given factor."""

    def __init__(self, factor: float) -> None:
        self._factor = factor

    async def process(self, command: Command, context: StrategyContext) -> Command:
        return command.with_p(command.p_target * self._factor)


class OffsetProcessor:
    """Adds a fixed offset to p_target."""

    def __init__(self, offset: float) -> None:
        self._offset = offset

    async def process(self, command: Command, context: StrategyContext) -> Command:
        return command.with_p(command.p_target + self._offset)


class QScaleProcessor:
    """Multiplies q_target by a given factor."""

    def __init__(self, factor: float) -> None:
        self._factor = factor

    async def process(self, command: Command, context: StrategyContext) -> Command:
        return command.with_q(command.q_target * self._factor)


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


class TestCommandProcessorPipeline:
    """Tests for chaining multiple CommandProcessors in a pipeline.

    Mirrors how SystemController applies post_protection_processors:
        for processor in processors:
            command = await processor.process(command, context)
    """

    @staticmethod
    async def _run_pipeline(
        processors: list[CommandProcessor],
        command: Command,
        context: StrategyContext | None = None,
    ) -> Command:
        """Simulate the SystemController processor pipeline loop."""
        ctx = context or StrategyContext()
        result = command
        for proc in processors:
            result = await proc.process(result, ctx)
        return result

    @pytest.mark.asyncio
    async def test_empty_pipeline_returns_original_command(self):
        """An empty processor list must return the original command unchanged."""
        cmd = Command(p_target=500.0, q_target=100.0)
        result = await self._run_pipeline([], cmd)

        assert result.p_target == pytest.approx(500.0)
        assert result.q_target == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_pipeline_chaining_output_feeds_into_next(self):
        """Output of processor A feeds into processor B.

        Pipeline: Scale(×2) → Offset(+50)
        Input:  p=100
        After Scale:  p=200
        After Offset: p=250
        """
        processors: list[CommandProcessor] = [ScaleProcessor(2.0), OffsetProcessor(50.0)]
        cmd = Command(p_target=100.0, q_target=0.0)
        result = await self._run_pipeline(processors, cmd)

        assert result.p_target == pytest.approx(250.0)

    @pytest.mark.asyncio
    async def test_pipeline_order_matters(self):
        """Processor order must affect the result: Scale→Offset ≠ Offset→Scale.

        Order A: Scale(×2) → Offset(+50)  →  (100×2)+50 = 250
        Order B: Offset(+50) → Scale(×2)  →  (100+50)×2 = 300
        """
        cmd = Command(p_target=100.0, q_target=0.0)

        result_a = await self._run_pipeline([ScaleProcessor(2.0), OffsetProcessor(50.0)], cmd)
        result_b = await self._run_pipeline([OffsetProcessor(50.0), ScaleProcessor(2.0)], cmd)

        assert result_a.p_target == pytest.approx(250.0)
        assert result_b.p_target == pytest.approx(300.0)
        assert result_a.p_target != pytest.approx(result_b.p_target)
