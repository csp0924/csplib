# =============== Core - Resilience ===============
#
# 通用韌性模組
#
# 提供跨層共用的斷路器與重試策略：
#   - CircuitState: 斷路器狀態列舉
#   - CircuitBreaker: 通用斷路器
#   - RetryPolicy: 重試策略配置

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum


class CircuitState(Enum):
    """斷路器狀態"""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    通用斷路器

    狀態轉換：
        CLOSED → 連續失敗達閾值 → OPEN
        OPEN → 冷卻時間過後 → HALF_OPEN
        HALF_OPEN → 成功 → CLOSED
        HALF_OPEN → 失敗 → OPEN

    Args:
        threshold: 連續失敗次數達到此值後觸發斷路器
        cooldown: 斷路器開啟後的冷卻時間 (秒)
        max_cooldown: 指數退避的最大冷卻時間 (秒)
        backoff_factor: 指數退避的倍率
    """

    def __init__(
        self,
        threshold: int,
        cooldown: float,
        max_cooldown: float = 300.0,
        backoff_factor: float = 2.0,
    ) -> None:
        self._threshold = threshold
        self._cooldown = cooldown
        self._max_cooldown = max_cooldown
        self._backoff_factor = backoff_factor
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0
        self._current_cooldown: float = cooldown

    def _compute_cooldown(self) -> float:
        """計算帶指數退避 + jitter 的冷卻時間（進入 OPEN 時呼叫一次）"""
        exponent = min(self._consecutive_failures, 5)
        base = self._cooldown * (self._backoff_factor**exponent)
        base = min(base, self._max_cooldown)
        jitter = 0.8 + 0.4 * random.random()  # noqa: S311
        return base * jitter

    @property
    def state(self) -> CircuitState:
        """取得目前狀態 (含自動 OPEN → HALF_OPEN 轉換)"""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._current_cooldown:
                self._state = CircuitState.HALF_OPEN
        return self._state

    @property
    def failure_count(self) -> int:
        """目前連續失敗次數"""
        return self._failure_count

    def record_success(self) -> None:
        """記錄成功：重置斷路器"""
        self._failure_count = 0
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """記錄失敗：累計失敗次數，達閾值時開啟斷路器"""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self._threshold:
            self._consecutive_failures += 1
            self._current_cooldown = self._compute_cooldown()
            self._state = CircuitState.OPEN

    def reset(self) -> None:
        """手動重置斷路器"""
        self._failure_count = 0
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._last_failure_time = 0.0

    def allows_request(self) -> bool:
        """是否允許請求通過"""
        return self.state != CircuitState.OPEN


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """
    重試策略配置

    Args:
        max_retries: 最大重試次數
        base_delay: 基礎延遲 (秒)
        exponential_base: 指數退避的基數
    """

    max_retries: int = 3
    base_delay: float = 1.0
    exponential_base: float = 2.0

    def get_delay(self, attempt: int) -> float:
        """計算第 N 次重試的延遲時間"""
        return self.base_delay * (self.exponential_base**attempt)


__all__ = [
    "CircuitState",
    "CircuitBreaker",
    "RetryPolicy",
]
