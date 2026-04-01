"""Tests for CircuitBreaker state transitions and RetryPolicy backoff.

Covers: CLOSED->OPEN, OPEN->HALF_OPEN, HALF_OPEN->CLOSED/OPEN,
allows_request, reset, and RetryPolicy delay calculation.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Generator

import pytest

from csp_lib.core.resilience import CircuitBreaker, CircuitState, RetryPolicy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeClock:
    """Deterministic clock for testing time-dependent code."""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@contextlib.contextmanager
def _patched_monotonic(clock: _FakeClock) -> Generator[None]:
    """Temporarily replace time.monotonic with a deterministic fake clock."""
    original = time.monotonic
    time.monotonic = clock  # type: ignore[assignment]
    try:
        yield
    finally:
        time.monotonic = original


# ---------------------------------------------------------------------------
# CircuitBreaker — state transitions
# ---------------------------------------------------------------------------


class TestCircuitBreakerStateTransitions:
    """Verify the full state machine: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""

    def test_initial_state_is_closed(self) -> None:
        cb = CircuitBreaker(threshold=3, cooldown=5.0)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_closed_to_open_after_threshold_failures(self) -> None:
        """N consecutive failures should transition CLOSED -> OPEN."""
        cb = CircuitBreaker(threshold=3, cooldown=5.0)
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_blocks_requests(self) -> None:
        """OPEN state should reject requests."""
        cb = CircuitBreaker(threshold=1, cooldown=999.0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allows_request() is False

    def test_open_to_half_open_after_cooldown(self) -> None:
        """After cooldown expires (with backoff), state transitions OPEN -> HALF_OPEN."""
        clock = _FakeClock()
        # backoff_factor=1.0 disables exponential growth for predictable testing
        cb = CircuitBreaker(threshold=1, cooldown=10.0, backoff_factor=1.0, max_cooldown=15.0)
        with _patched_monotonic(clock):
            cb.record_failure()
            assert cb.state == CircuitState.OPEN

            # With jitter ±20%, effective cooldown is 8-12s. Advance past max.
            clock.advance(15.0)
            assert cb.state == CircuitState.HALF_OPEN
            assert cb.allows_request() is True

    def test_half_open_to_closed_on_success(self) -> None:
        """Success in HALF_OPEN -> CLOSED."""
        clock = _FakeClock()
        cb = CircuitBreaker(threshold=1, cooldown=1.0, backoff_factor=1.0, max_cooldown=2.0)
        with _patched_monotonic(clock):
            cb.record_failure()
            clock.advance(2.0)
            assert cb.state == CircuitState.HALF_OPEN

            cb.record_success()
            assert cb.state == CircuitState.CLOSED
            assert cb.failure_count == 0

    def test_half_open_to_open_on_failure(self) -> None:
        """Failure in HALF_OPEN -> OPEN again."""
        clock = _FakeClock()
        cb = CircuitBreaker(threshold=1, cooldown=1.0, backoff_factor=1.0, max_cooldown=2.0)
        with _patched_monotonic(clock):
            cb.record_failure()
            clock.advance(2.0)
            assert cb.state == CircuitState.HALF_OPEN

            cb.record_failure()
            assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self) -> None:
        """record_success resets counter, preventing premature OPEN."""
        cb = CircuitBreaker(threshold=3, cooldown=5.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        # One more failure should NOT open (count reset)
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_reset_returns_to_closed(self) -> None:
        """Manual reset() clears state to CLOSED."""
        cb = CircuitBreaker(threshold=1, cooldown=999.0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.allows_request() is True

    def test_allows_request_in_closed_state(self) -> None:
        cb = CircuitBreaker(threshold=5, cooldown=5.0)
        assert cb.allows_request() is True

    @pytest.mark.parametrize("threshold", [1, 5, 10])
    def test_exact_threshold_opens_circuit(self, threshold: int) -> None:
        """Circuit opens at exactly the threshold count."""
        cb = CircuitBreaker(threshold=threshold, cooldown=5.0)
        for _ in range(threshold - 1):
            cb.record_failure()
            assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# RetryPolicy — backoff calculation
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    """Verify exponential backoff delay calculation."""

    def test_default_values(self) -> None:
        rp = RetryPolicy()
        assert rp.max_retries == 3
        assert rp.base_delay == 1.0
        assert rp.exponential_base == 2.0

    def test_get_delay_attempt_zero(self) -> None:
        rp = RetryPolicy(base_delay=1.0, exponential_base=2.0)
        assert rp.get_delay(0) == pytest.approx(1.0)

    def test_get_delay_attempt_one(self) -> None:
        rp = RetryPolicy(base_delay=1.0, exponential_base=2.0)
        assert rp.get_delay(1) == pytest.approx(2.0)

    def test_get_delay_attempt_two(self) -> None:
        rp = RetryPolicy(base_delay=1.0, exponential_base=2.0)
        assert rp.get_delay(2) == pytest.approx(4.0)

    @pytest.mark.parametrize(
        ("attempt", "expected"),
        [(0, 0.5), (1, 1.5), (2, 4.5)],
    )
    def test_custom_base_delay_and_exponential(self, attempt: int, expected: float) -> None:
        rp = RetryPolicy(base_delay=0.5, exponential_base=3.0)
        assert rp.get_delay(attempt) == pytest.approx(expected)

    def test_frozen_dataclass(self) -> None:
        """RetryPolicy is frozen — attributes cannot be mutated."""
        rp = RetryPolicy()
        with pytest.raises(AttributeError):
            rp.max_retries = 10  # type: ignore[misc]
