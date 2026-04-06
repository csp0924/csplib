# =============== Modbus Server - Simulation Server ===============
#
# pymodbus TCP server 封裝 + tick loop

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from csp_lib.core import AsyncLifecycleMixin, get_logger
from csp_lib.core.errors import ConfigurationError
from csp_lib.modbus._pymodbus import (
    ensure_pymodbus_server,
    get_BaseModbusDataBlock,
    get_ModbusDeviceContext,
    get_ModbusServerContext,
    get_ModbusTcpServer,
)

from .config import ServerConfig

if TYPE_CHECKING:
    from .microgrid import MicrogridSimulator
    from .simulator.base import BaseDeviceSimulator

logger = get_logger(__name__)


def _ensure_pymodbus_imported() -> None:
    """確保 pymodbus server 相關模組已載入 (backward-compat wrapper)."""
    ensure_pymodbus_server()


class SimulatorDataBlock:
    """
    自訂 Modbus DataBlock

    橋接 pymodbus datastore 與 RegisterBlock。
    寫入時偵測 writable points 並呼叫 simulator.on_write()。

    pymodbus 3.12 的 BaseModbusDataBlock 要求 values, address, default_value 屬性。
    透過 _create_datablock() 工廠函式建立繼承版本。
    """

    def __init__(self, simulator: BaseDeviceSimulator) -> None:
        self._simulator = simulator
        self._block = simulator.register_block
        # pymodbus 需要這些屬性
        self.address = 0
        self.default_value = 0
        self.values = self._block.registers

    def reset(self) -> None:
        pass

    def getValues(self, address: int, count: int = 1) -> list[int]:
        return self._block.get_raw(address, count)

    def setValues(self, address: int, values: list[int]) -> None:
        # 先記錄受影響 points 的舊值
        affected = self._block.find_affected_points(address, len(values))
        old_values = {}
        for point in affected:
            old_values[point.name] = self._block.get_value(point.name)

        # 寫入 raw registers
        self._block.set_raw(address, values)

        # 觸發 on_write 回調
        for point in affected:
            new_value = self._block.get_value(point.name)
            old_value = old_values[point.name]
            if old_value != new_value:
                self._simulator.on_write(point.name, old_value, new_value)


class SimulationServer(AsyncLifecycleMixin):
    """
    Modbus TCP 模擬伺服器

    封裝 pymodbus TCP server，提供：
    - 多設備模擬器管理（per unit_id）
    - 定期 tick loop 呼叫所有 simulator 的 update()
    - 支援 MicrogridSimulator 聯動模式
    - AsyncLifecycleMixin 生命週期管理
    """

    def __init__(self, config: ServerConfig | None = None) -> None:
        self._config = config or ServerConfig()
        self._simulators: dict[int, BaseDeviceSimulator] = {}
        self._microgrid: MicrogridSimulator | None = None
        self._server: Any = None
        self._tick_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def config(self) -> ServerConfig:
        return self._config

    @property
    def simulators(self) -> dict[int, BaseDeviceSimulator]:
        return dict(self._simulators)

    @property
    def is_running(self) -> bool:
        return self._running

    def add_simulator(self, simulator: BaseDeviceSimulator) -> None:
        """註冊設備模擬器"""
        if simulator.unit_id in self._simulators:
            raise ConfigurationError(f"Unit ID {simulator.unit_id} already registered")
        self._simulators[simulator.unit_id] = simulator

    def set_microgrid(self, microgrid: MicrogridSimulator) -> None:
        """
        設定 MicrogridSimulator 聯動模式

        自動註冊所有 microgrid 中的 simulators。
        Tick loop 將呼叫 microgrid.update() 而非個別 simulator.update()。
        """
        self._microgrid = microgrid
        for sim in microgrid.all_simulators:
            if sim.unit_id not in self._simulators:
                self._simulators[sim.unit_id] = sim

    async def _on_start(self) -> None:
        """啟動 server"""
        _ensure_pymodbus_imported()

        # 建立 per-simulator datablock 和 context
        slaves = {}
        for unit_id, sim in self._simulators.items():
            data_block = _create_datablock(sim)
            # ModbusDeviceContext: di=discrete inputs, co=coils, hr=holding registers, ir=input registers
            slave_ctx = get_ModbusDeviceContext()(  # type: ignore[misc]
                di=data_block,
                co=data_block,
                hr=data_block,
                ir=data_block,
            )
            slaves[unit_id] = slave_ctx

        if not slaves:
            logger.warning("No simulators registered, server will start with empty context")
            data_block = _create_empty_pymodbus_block()
            slaves[0] = get_ModbusDeviceContext()(di=data_block, co=data_block, hr=data_block, ir=data_block)  # type: ignore[misc]

        server_ctx = get_ModbusServerContext()(devices=slaves, single=False)  # type: ignore[misc]

        self._server = get_ModbusTcpServer()(  # type: ignore[misc]
            context=server_ctx,
            address=(self._config.host, self._config.port),
        )

        # 啟動 server（背景執行）
        await self._server.serve_forever(background=True)
        self._running = True

        # 啟動 tick loop
        self._tick_task = asyncio.create_task(self._tick_loop())

        logger.info(f"SimulationServer started on {self._config.host}:{self._config.port}")

    async def _on_stop(self) -> None:
        """停止 server"""
        self._running = False

        # 取消 tick loop
        if self._tick_task is not None:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
            self._tick_task = None

        # 關閉 server
        if self._server is not None:
            await self._server.shutdown()
            self._server = None

        logger.info("SimulationServer stopped")

    async def _tick_loop(self) -> None:
        """定期 tick loop"""
        interval = self._config.tick_interval
        try:
            while self._running:
                await self._tick(interval)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    async def _tick(self, interval: float) -> None:
        """執行一次 tick"""
        if self._microgrid is not None:
            await self._microgrid.update(interval)
        else:
            for sim in self._simulators.values():
                await sim.update()

    async def serve(self) -> None:
        """持續運行直到被停止"""
        try:
            while self._running:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass


def _create_datablock(simulator: BaseDeviceSimulator) -> Any:
    """建立繼承 BaseModbusDataBlock 的 SimulatorDataBlock

    注意: pymodbus 3.12 的 ModbusDeviceContext 在呼叫 datablock 前會
    自動 address += 1，因此 datablock 內需要 address -= 1 來補償。
    """
    wrapper = SimulatorDataBlock(simulator)

    class _PymodbusDataBlock(get_BaseModbusDataBlock()):  # type: ignore[misc]
        def __init__(self) -> None:
            self.address = 0
            self.default_value = 0
            self.values = wrapper._block.registers

        def reset(self) -> None:
            wrapper.reset()

        def getValues(self, address: int, count: int = 1) -> list[int]:
            return wrapper.getValues(address - 1, count)

        def setValues(self, address: int, values: list[int]) -> None:
            wrapper.setValues(address - 1, values)

    return _PymodbusDataBlock()


def _create_empty_pymodbus_block() -> Any:
    """建立空的 pymodbus DataBlock"""

    class _EmptyBlock(get_BaseModbusDataBlock()):  # type: ignore[misc]
        def __init__(self) -> None:
            self.address = 0
            self.default_value = 0
            self.values = [0] * 100

        def reset(self) -> None:
            pass

        def getValues(self, address: int, count: int = 1) -> list[int]:
            return [0] * count

        def setValues(self, address: int, values: list[int]) -> None:
            pass

    return _EmptyBlock()


__all__ = ["SimulationServer", "SimulatorDataBlock"]
