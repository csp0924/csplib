# =============== Modbus Gateway - Protocol ===============
#
# Gateway 擴展協定介面
#
# 提供三個 @runtime_checkable Protocol：
#   - WriteValidator: 驗證 EMS 寫入請求
#   - WriteHook: 寫入後觸發的鉤子
#   - DataSyncSource: 外部資料來源同步介面

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

# Type alias for update callback used by DataSyncSource
UpdateRegisterCallback = Callable[[str, Any], Awaitable[None]]


@runtime_checkable
class WriteValidator(Protocol):
    """Validates an incoming EMS write request.

    Implementations inspect the register name and proposed value,
    returning ``True`` to accept or ``False`` to reject.

    Example:
        class RangeValidator:
            def validate(self, register_name: str, value: Any) -> bool:
                return 0 <= value <= 100
    """

    def validate(self, register_name: str, value: Any) -> bool:
        """Check whether the write should be accepted.

        Args:
            register_name: Logical name of the target register.
            value: The proposed write value (already decoded).

        Returns:
            True to accept the write, False to reject.
        """
        ...


@runtime_checkable
class WriteHook(Protocol):
    """Post-write hook triggered after a successful register write.

    Example:
        class LoggingHook:
            async def on_write(self, register_name: str, old_value: Any, new_value: Any) -> None:
                print(f"{register_name}: {old_value} -> {new_value}")
    """

    async def on_write(self, register_name: str, old_value: Any, new_value: Any) -> None:
        """Called after a register value has been updated.

        Args:
            register_name: Logical name of the written register.
            old_value: Previous value before the write.
            new_value: New value after the write.
        """
        ...


@runtime_checkable
class DataSyncSource(Protocol):
    """External data source that feeds register values into the gateway.

    Implementations receive an ``update_callback`` at start and use it
    to push new values into the gateway register space.

    Example:
        class PollingSource:
            async def start(self, update_callback: UpdateRegisterCallback) -> None:
                self._callback = update_callback
                # begin polling ...

            async def stop(self) -> None:
                # stop polling ...
    """

    async def start(self, update_callback: UpdateRegisterCallback) -> None:
        """Begin producing data and pushing it via *update_callback*.

        Args:
            update_callback: Async callable ``(register_name, value) -> None``
                used to update gateway registers.
        """
        ...

    async def stop(self) -> None:
        """Stop producing data and release resources."""
        ...


@runtime_checkable
class WriteRule(Protocol):
    """Composable write rule that can transform or reject a proposed value.

    Implementations inspect the register name and proposed value,
    returning a (possibly transformed) value and a rejection flag.

    Example:
        @dataclass(frozen=True, slots=True)
        class MyRule:
            threshold: float = 100.0

            def apply(self, register_name: str, value: float) -> tuple[float, bool]:
                if value > self.threshold:
                    return self.threshold, False  # clamp
                return value, False
    """

    def apply(self, register_name: str, value: float) -> tuple[float, bool]:
        """Apply this rule to a proposed write value.

        Args:
            register_name: Logical name of the target register (for logging).
            value: The proposed write value.

        Returns:
            Tuple of (possibly_transformed_value, rejected).
            If rejected is True, the value should be discarded.
        """
        ...


__all__ = [
    "DataSyncSource",
    "UpdateRegisterCallback",
    "WriteHook",
    "WriteRule",
    "WriteValidator",
]
