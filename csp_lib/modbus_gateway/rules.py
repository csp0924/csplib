"""
Composable write rules for the Modbus Gateway write pipeline.

Provides four frozen-dataclass implementations of the ``WriteRule`` protocol:

- ``RangeRule`` — clamp or reject values outside [min, max]
- ``AllowedValuesRule`` — accept only explicitly listed values
- ``StepRule`` — quantise values to a fixed step size
- ``CompositeRule`` — chain multiple rules in order (short-circuits on rejection)
"""

from __future__ import annotations

from dataclasses import dataclass

from csp_lib.core import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RangeRule:
    """Reject or clamp values outside an allowed range.

    When ``clamp`` is False (default), out-of-range values are rejected.
    When ``clamp`` is True, values are clamped to the nearest bound.

    Attributes:
        min_value: Minimum acceptable value (None means no lower bound).
        max_value: Maximum acceptable value (None means no upper bound).
        clamp: If True, clamp instead of rejecting out-of-range values.
    """

    min_value: float | None = None
    max_value: float | None = None
    clamp: bool = False

    def apply(self, register_name: str, value: float) -> tuple[float, bool]:
        """Apply range check to the proposed value.

        Args:
            register_name: Logical name of the target register.
            value: The proposed write value.

        Returns:
            Tuple of (possibly_clamped_value, rejected).
        """
        if self.min_value is not None and value < self.min_value:
            if self.clamp:
                logger.debug("RangeRule clamp: {}={} -> {} (min)", register_name, value, self.min_value)
                return self.min_value, False
            logger.debug("RangeRule reject: {}={} < min={}", register_name, value, self.min_value)
            return value, True

        if self.max_value is not None and value > self.max_value:
            if self.clamp:
                logger.debug("RangeRule clamp: {}={} -> {} (max)", register_name, value, self.max_value)
                return self.max_value, False
            logger.debug("RangeRule reject: {}={} > max={}", register_name, value, self.max_value)
            return value, True

        return value, False


@dataclass(frozen=True, slots=True)
class AllowedValuesRule:
    """Accept only values that belong to an explicit allow-set.

    The ``allowed`` field is stored as a ``frozenset`` for immutability.
    Callers may pass any iterable (set, list, tuple); ``__post_init__``
    converts it to ``frozenset`` automatically.

    Attributes:
        allowed: The set of acceptable values.
    """

    allowed: frozenset[float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed", frozenset(self.allowed))

    def apply(self, register_name: str, value: float) -> tuple[float, bool]:
        """Accept the value only if it is in the allowed set.

        Args:
            register_name: Logical name of the target register.
            value: The proposed write value.

        Returns:
            Tuple of (value, rejected). The value is never transformed.
        """
        if value not in self.allowed:
            logger.debug("AllowedValuesRule reject: {}={} not in {}", register_name, value, self.allowed)
            return value, True
        return value, False


@dataclass(frozen=True, slots=True)
class StepRule:
    """Quantise values to the nearest multiple of a fixed step.

    This rule never rejects; it always snaps the value to the closest
    step boundary.

    Attributes:
        step: Step size (must be > 0).
        precision: Decimal places to round the quantised result (must be >= 0).
    """

    step: float
    precision: int = 10

    def __post_init__(self) -> None:
        if self.step <= 0:
            raise ValueError(f"step must be > 0, got {self.step}")
        if self.precision < 0:
            raise ValueError(f"precision must be >= 0, got {self.precision}")

    def apply(self, register_name: str, value: float) -> tuple[float, bool]:
        """Quantise *value* to the nearest step multiple.

        Args:
            register_name: Logical name of the target register.
            value: The proposed write value.

        Returns:
            Tuple of (quantised_value, False). StepRule never rejects.
        """
        quantized = round(round(value / self.step) * self.step, self.precision)
        if quantized != value:
            logger.debug("StepRule quantise: {}={} -> {}", register_name, value, quantized)
        return quantized, False


@dataclass(frozen=True, slots=True)
class CompositeRule:
    """Chain multiple rules; short-circuit on the first rejection.

    The ``rules`` field is stored as a ``tuple`` for immutability.
    Callers may pass any iterable; ``__post_init__`` converts it.

    Attributes:
        rules: Ordered sequence of rules to apply.
    """

    rules: tuple  # type: ignore[type-arg]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", tuple(self.rules))

    def apply(self, register_name: str, value: float) -> tuple[float, bool]:
        """Apply each rule in order, returning early on rejection.

        Args:
            register_name: Logical name of the target register.
            value: The proposed write value.

        Returns:
            Tuple of (possibly_transformed_value, rejected).
        """
        for rule in self.rules:
            value, rejected = rule.apply(register_name, value)
            if rejected:
                return value, True
        return value, False


__all__ = [
    "AllowedValuesRule",
    "CompositeRule",
    "RangeRule",
    "StepRule",
]
