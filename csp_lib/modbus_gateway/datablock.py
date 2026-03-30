"""
pymodbus DataBlock adapter for the Modbus Gateway.

橋接 pymodbus server thread 與 asyncio event loop：
- getValues(): 從 GatewayRegisterMap 讀取（thread-safe via Lock）
- setValues(): 經 WritePipeline 處理寫入，dispatch hooks 到 asyncio loop
- IR DataBlock 拒絕所有寫入

pymodbus 3.12+ 的 ModbusDeviceContext 在呼叫 datablock 前會
自動 address += 1，因此 getValues/setValues 內需要 address -= 1 來補償。
"""

from __future__ import annotations

import asyncio
from typing import Any

from csp_lib.core import get_logger

logger = get_logger(__name__)


def create_hr_datablock(
    register_map: Any,  # GatewayRegisterMap
    pipeline: Any,  # WritePipeline
    watchdog: Any,  # CommunicationWatchdog
    loop: asyncio.AbstractEventLoop,
) -> Any:
    """
    建立 Holding Register DataBlock（FC03 讀 / FC06,16 寫）。

    寫入時經 WritePipeline 處理，hooks 透過 loop.call_soon_threadsafe 派發。

    Returns:
        繼承 BaseModbusDataBlock 的實例
    """
    from csp_lib.modbus_server.server import _ensure_pymodbus_imported

    _ensure_pymodbus_imported()

    # 重新 import (lazy import 後才可用)
    from pymodbus.datastore.store import BaseModbusDataBlock as _Base

    class _HRDataBlock(_Base):  # type: ignore[misc]
        def __init__(self) -> None:
            self.address = 0
            self.default_value = 0
            self.values = register_map._hr_regs

        def reset(self) -> None:
            pass

        def validate(self, address: int, count: int = 1) -> bool:
            addr = address - 1  # pymodbus 3.12 offset compensation
            return 0 <= addr and addr + count <= len(register_map._hr_regs)

        def getValues(self, address: int, count: int = 1) -> list[int]:
            addr = address - 1  # pymodbus 3.12 offset compensation
            watchdog.touch()
            return register_map.get_hr_raw(addr, count)

        def setValues(self, address: int, values: list[int]) -> None:
            addr = address - 1  # pymodbus 3.12 offset compensation
            watchdog.touch()

            # Process write through pipeline (sync, in pymodbus thread)
            changes = pipeline.process_write(addr, values)

            # Dispatch async hooks via event loop
            if changes and pipeline.hooks:
                try:
                    if loop.is_running():
                        for name, old_val, new_val in changes:
                            loop.call_soon_threadsafe(
                                asyncio.ensure_future,
                                _dispatch_hooks(pipeline.hooks, name, old_val, new_val),
                            )
                except RuntimeError:
                    logger.warning("Event loop not running, skipping hook dispatch")

    return _HRDataBlock()


def create_ir_datablock(
    register_map: Any,  # GatewayRegisterMap
    watchdog: Any,  # CommunicationWatchdog
) -> Any:
    """
    建立 Input Register DataBlock（FC04 唯讀）。

    所有寫入靜默忽略。

    Returns:
        繼承 BaseModbusDataBlock 的實例
    """
    from csp_lib.modbus_server.server import _ensure_pymodbus_imported

    _ensure_pymodbus_imported()

    from pymodbus.datastore.store import BaseModbusDataBlock as _Base

    class _IRDataBlock(_Base):  # type: ignore[misc]
        def __init__(self) -> None:
            self.address = 0
            self.default_value = 0
            self.values = register_map._ir_regs

        def reset(self) -> None:
            pass

        def validate(self, address: int, count: int = 1) -> bool:
            addr = address - 1
            return 0 <= addr and addr + count <= len(register_map._ir_regs)

        def getValues(self, address: int, count: int = 1) -> list[int]:
            addr = address - 1
            watchdog.touch()
            return register_map.get_ir_raw(addr, count)

        def setValues(self, address: int, values: list[int]) -> None:
            # Input registers are read-only from EMS perspective
            pass

    return _IRDataBlock()


def create_empty_datablock() -> Any:
    """建立空的 DataBlock（用於 coils / discrete inputs）。"""
    from csp_lib.modbus_server.server import _ensure_pymodbus_imported

    _ensure_pymodbus_imported()

    from pymodbus.datastore.store import BaseModbusDataBlock as _Base

    class _EmptyDataBlock(_Base):  # type: ignore[misc]
        def __init__(self) -> None:
            self.address = 0
            self.default_value = 0
            self.values = [0]

        def reset(self) -> None:
            pass

        def validate(self, address: int, count: int = 1) -> bool:
            return True

        def getValues(self, address: int, count: int = 1) -> list[int]:
            return [0] * count

        def setValues(self, address: int, values: list[int]) -> None:
            pass

    return _EmptyDataBlock()


async def _dispatch_hooks(hooks: list[Any], name: str, old_val: Any, new_val: Any) -> None:
    """Dispatch all write hooks. Errors in individual hooks are logged but don't propagate."""
    for hook in hooks:
        try:
            await hook.on_write(name, old_val, new_val)
        except Exception:
            logger.opt(exception=True).warning(f"WriteHook {type(hook).__name__} failed for {name}")


__all__ = [
    "create_hr_datablock",
    "create_ir_datablock",
    "create_empty_datablock",
]
