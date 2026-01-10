# =============== Modbus Pymodbus Client ===============
#
# pymodbus 非同步客戶端實作
#
# 特性：
#   - 只支援非同步操作
#   - retries=0 (不重試)
#   - TCP 和 RTU 模式
#   - 支援 pymodbus 3.10.0+ 版本 (slave → device_id)

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..config import ModbusRtuConfig, ModbusTcpConfig
from ..exceptions import ModbusError
from .base import AsyncModbusClientBase
from .compat import slave_kwarg

if TYPE_CHECKING:
    from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient


# ========== Lazy Import for Optional Dependency ==========
# pymodbus 為 optional dependency，僅在實際使用時才載入

_AsyncModbusTcpClient: type[AsyncModbusTcpClient] | None = None
_AsyncModbusSerialClient: type[AsyncModbusSerialClient] | None = None


def _ensure_pymodbus_imported() -> None:
    """
    確保 pymodbus 已載入

    使用模組層級變數快取，只執行一次實際 import。
    若 pymodbus 未安裝則拋出清晰的錯誤訊息。
    """
    global _AsyncModbusTcpClient, _AsyncModbusSerialClient

    if _AsyncModbusTcpClient is not None:
        return  # 已載入，直接返回

    try:
        from pymodbus.client import (
            AsyncModbusSerialClient,
            AsyncModbusTcpClient,
        )

        _AsyncModbusTcpClient = AsyncModbusTcpClient
        _AsyncModbusSerialClient = AsyncModbusSerialClient
    except ImportError as e:
        raise ImportError(
            "Pymodbus client requires 'pymodbus' package. "
            "Install with: uv pip install csp_lib[modbus]"
        ) from e


class PymodbusTcpClient(AsyncModbusClientBase):
    """
    pymodbus TCP 非同步客戶端

    使用 pymodbus 庫實作 Modbus TCP 通訊。
    所有操作皆為非同步 (async/await)。

    支援 pymodbus >= 3.0.0，自動適配 3.10.0+ API 變更。

    Args:
        config: TCP 連線設定

    使用範例：
        >>> config = ModbusTcpConfig(host="192.168.1.100")
        >>> async with PymodbusTcpClient(config) as client:
        ...     registers = await client.read_holding_registers(0, 10)
    """

    def __init__(self, config: ModbusTcpConfig) -> None:
        self._config = config
        self._client: AsyncModbusTcpClient | None = None

    def _get_client(self) -> AsyncModbusTcpClient:
        """取得或建立 pymodbus 客戶端"""
        if self._client is None:
            _ensure_pymodbus_imported()
            assert _AsyncModbusTcpClient is not None  # for type checker

            self._client = _AsyncModbusTcpClient(
                host=self._config.host,
                port=self._config.port,
                timeout=self._config.timeout,
                retries=0,  # 不重試
            )
        return self._client

    async def connect(self) -> None:
        """建立 TCP 連線"""
        client = self._get_client()
        if not client.connected:
            connected = await client.connect()
            if not connected:
                raise ModbusError(
                    f"無法連線到 {self._config.host}:{self._config.port}"
                )

    async def disconnect(self) -> None:
        """斷開 TCP 連線"""
        if self._client is not None:
            self._client.close()

    def is_connected(self) -> bool:
        """檢查連線狀態"""
        return self._client is not None and self._client.connected

    # ========== 讀取操作 ==========

    async def read_coils(self, address: int, count: int) -> list[bool]:
        """讀取線圈狀態 (FC 0x01)"""
        client = self._get_client()
        response = await client.read_coils(
            address=address,
            count=count,
            **slave_kwarg(self._config.unit_id),
        )
        if response.isError():
            raise ModbusError(f"讀取線圈失敗: {response}")
        return list(response.bits[:count])

    async def read_discrete_inputs(self, address: int, count: int) -> list[bool]:
        """讀取離散輸入 (FC 0x02)"""
        client = self._get_client()
        response = await client.read_discrete_inputs(
            address=address,
            count=count,
            **slave_kwarg(self._config.unit_id),
        )
        if response.isError():
            raise ModbusError(f"讀取離散輸入失敗: {response}")
        return list(response.bits[:count])

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        """讀取保持暫存器 (FC 0x03)"""
        client = self._get_client()
        response = await client.read_holding_registers(
            address=address,
            count=count,
            **slave_kwarg(self._config.unit_id),
        )
        if response.isError():
            raise ModbusError(f"讀取保持暫存器失敗: {response}")
        return list(response.registers)

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        """讀取輸入暫存器 (FC 0x04)"""
        client = self._get_client()
        response = await client.read_input_registers(
            address=address,
            count=count,
            **slave_kwarg(self._config.unit_id),
        )
        if response.isError():
            raise ModbusError(f"讀取輸入暫存器失敗: {response}")
        return list(response.registers)

    # ========== 寫入操作 ==========

    async def write_single_coil(self, address: int, value: bool) -> None:
        """寫入單一線圈 (FC 0x05)"""
        client = self._get_client()
        response = await client.write_coil(
            address=address,
            value=value,
            **slave_kwarg(self._config.unit_id),
        )
        if response.isError():
            raise ModbusError(f"寫入線圈失敗: {response}")

    async def write_single_register(self, address: int, value: int) -> None:
        """寫入單一暫存器 (FC 0x06)"""
        client = self._get_client()
        response = await client.write_register(
            address=address,
            value=value,
            **slave_kwarg(self._config.unit_id),
        )
        if response.isError():
            raise ModbusError(f"寫入暫存器失敗: {response}")

    async def write_multiple_coils(self, address: int, values: list[bool]) -> None:
        """寫入多個線圈 (FC 0x0F)"""
        client = self._get_client()
        response = await client.write_coils(
            address=address,
            values=values,
            **slave_kwarg(self._config.unit_id),
        )
        if response.isError():
            raise ModbusError(f"寫入多個線圈失敗: {response}")

    async def write_multiple_registers(self, address: int, values: list[int]) -> None:
        """寫入多個暫存器 (FC 0x10)"""
        client = self._get_client()
        response = await client.write_registers(
            address=address,
            values=values,
            **slave_kwarg(self._config.unit_id),
        )
        if response.isError():
            raise ModbusError(f"寫入多個暫存器失敗: {response}")


# RTU 客戶端單例管理：確保每個串口只有一個連線
# port -> (client, lock, ref_count)
_rtu_instances: dict[str, tuple[AsyncModbusSerialClient, asyncio.Lock, int]] = {}
_rtu_instances_lock = asyncio.Lock()


class PymodbusRtuClient(AsyncModbusClientBase):
    """
    pymodbus RTU 非同步客戶端

    使用 pymodbus 庫實作 Modbus RTU 通訊。
    採用 Singleton per port 模式，確保同一串口只有一個連線。
    共用的 asyncio.Lock 確保 RTU 通訊的原子性。

    支援 pymodbus >= 3.0.0，自動適配 3.10.0+ API 變更。

    Args:
        config: RTU 連線設定

    使用範例：
        >>> config = ModbusRtuConfig(port="COM1")
        >>> async with PymodbusRtuClient(config) as client:
        ...     registers = await client.read_holding_registers(0, 10)

    Note:
        同一串口的多個 PymodbusRtuClient 實例會共用：
        - 同一個 pymodbus AsyncModbusSerialClient
        - 同一個 asyncio.Lock
    """

    def __init__(self, config: ModbusRtuConfig) -> None:
        self._config = config
        self._port = config.port

    async def _get_shared_resources(
        self,
    ) -> tuple[AsyncModbusSerialClient, asyncio.Lock]:
        """
        取得共用的 pymodbus 客戶端和鎖

        使用 Singleton per port 模式，同一串口共用資源。
        """
        global _rtu_instances

        async with _rtu_instances_lock:
            if self._port in _rtu_instances:
                client, lock, ref_count = _rtu_instances[self._port]
                _rtu_instances[self._port] = (client, lock, ref_count + 1)
                return client, lock

            # 建立新的客戶端和鎖
            _ensure_pymodbus_imported()
            assert _AsyncModbusSerialClient is not None  # for type checker

            client = _AsyncModbusSerialClient(
                port=self._config.port,
                baudrate=self._config.baudrate,
                bytesize=self._config.bytesize,
                parity=self._config.parity.value,
                stopbits=self._config.stopbits,
                timeout=self._config.timeout,
                retries=0,  # 不重試
            )
            lock = asyncio.Lock()
            _rtu_instances[self._port] = (client, lock, 1)
            return client, lock

    async def _release_shared_resources(self) -> None:
        """釋放共用資源的參考計數"""
        global _rtu_instances

        async with _rtu_instances_lock:
            if self._port not in _rtu_instances:
                return

            client, lock, ref_count = _rtu_instances[self._port]
            if ref_count <= 1:
                # 最後一個使用者，關閉連線並移除
                if client.connected:
                    client.close()
                del _rtu_instances[self._port]
            else:
                _rtu_instances[self._port] = (client, lock, ref_count - 1)

    async def connect(self) -> None:
        """建立 RTU 連線"""
        client, lock = await self._get_shared_resources()
        async with lock:
            if not client.connected:
                connected = await client.connect()
                if not connected:
                    raise ModbusError(f"無法開啟串口 {self._config.port}")

    async def disconnect(self) -> None:
        """斷開 RTU 連線（釋放參考計數）"""
        await self._release_shared_resources()

    def is_connected(self) -> bool:
        """檢查連線狀態"""
        if self._port not in _rtu_instances:
            return False
        client, _, _ = _rtu_instances[self._port]
        return client.connected

    # ========== 讀取操作 (with shared lock) ==========

    async def read_coils(self, address: int, count: int) -> list[bool]:
        """讀取線圈狀態 (FC 0x01)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.read_coils(
                address=address,
                count=count,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"讀取線圈失敗: {response}")
            return list(response.bits[:count])

    async def read_discrete_inputs(self, address: int, count: int) -> list[bool]:
        """讀取離散輸入 (FC 0x02)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.read_discrete_inputs(
                address=address,
                count=count,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"讀取離散輸入失敗: {response}")
            return list(response.bits[:count])

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        """讀取保持暫存器 (FC 0x03)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.read_holding_registers(
                address=address,
                count=count,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"讀取保持暫存器失敗: {response}")
            return list(response.registers)

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        """讀取輸入暫存器 (FC 0x04)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.read_input_registers(
                address=address,
                count=count,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"讀取輸入暫存器失敗: {response}")
            return list(response.registers)

    # ========== 寫入操作 (with shared lock) ==========

    async def write_single_coil(self, address: int, value: bool) -> None:
        """寫入單一線圈 (FC 0x05)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.write_coil(
                address=address,
                value=value,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"寫入線圈失敗: {response}")

    async def write_single_register(self, address: int, value: int) -> None:
        """寫入單一暫存器 (FC 0x06)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.write_register(
                address=address,
                value=value,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"寫入暫存器失敗: {response}")

    async def write_multiple_coils(self, address: int, values: list[bool]) -> None:
        """寫入多個線圈 (FC 0x0F)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.write_coils(
                address=address,
                values=values,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"寫入多個線圈失敗: {response}")

    async def write_multiple_registers(self, address: int, values: list[int]) -> None:
        """寫入多個暫存器 (FC 0x10)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.write_registers(
                address=address,
                values=values,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"寫入多個暫存器失敗: {response}")


# ========== Shared TCP Client (for TCP-RS485 converters) ==========

# TCP 客戶端單例管理：同一 host:port 共用連線和鎖
# key: "host:port" -> (client, lock, ref_count)
_tcp_instances: dict[str, tuple[AsyncModbusTcpClient, asyncio.Lock, int]] = {}
_tcp_instances_lock = asyncio.Lock()


class SharedPymodbusTcpClient(AsyncModbusClientBase):
    """
    pymodbus TCP 共用連線客戶端

    專為 TCP-RS485 轉換器設計。同一 host:port 的多個設備共用：
    - 同一個 TCP 連線
    - 同一個 asyncio.Lock（確保 RS485 串列通訊）

    與 PymodbusTcpClient 的差異：
    - PymodbusTcpClient: 每個實例獨立連線，支援多工
    - SharedPymodbusTcpClient: 共用連線 + Lock，序列化存取

    使用場景：
        多個 Modbus 設備透過 TCP-RS485 轉換器連接，
        需要避免同時請求造成匯流排衝突。

    使用範例：
        >>> config = ModbusTcpConfig(host="192.168.1.12", unit_id=1)
        >>> async with SharedPymodbusTcpClient(config) as client:
        ...     registers = await client.read_holding_registers(0, 10)
    """

    def __init__(self, config: ModbusTcpConfig) -> None:
        self._config = config
        self._endpoint = f"{config.host}:{config.port}"

    async def _get_shared_resources(
        self,
    ) -> tuple[AsyncModbusTcpClient, asyncio.Lock]:
        """
        取得共用的 pymodbus 客戶端和鎖

        使用 Singleton per endpoint 模式，同一 host:port 共用資源。
        """
        global _tcp_instances

        async with _tcp_instances_lock:
            if self._endpoint in _tcp_instances:
                client, lock, ref_count = _tcp_instances[self._endpoint]
                _tcp_instances[self._endpoint] = (client, lock, ref_count + 1)
                return client, lock

            # 建立新的客戶端和鎖
            _ensure_pymodbus_imported()
            assert _AsyncModbusTcpClient is not None  # for type checker

            client = _AsyncModbusTcpClient(
                host=self._config.host,
                port=self._config.port,
                timeout=self._config.timeout,
                retries=0,  # 不重試
            )
            lock = asyncio.Lock()
            _tcp_instances[self._endpoint] = (client, lock, 1)
            return client, lock

    async def _release_shared_resources(self) -> None:
        """釋放共用資源的參考計數"""
        global _tcp_instances

        async with _tcp_instances_lock:
            if self._endpoint not in _tcp_instances:
                return

            client, lock, ref_count = _tcp_instances[self._endpoint]
            if ref_count <= 1:
                # 最後一個使用者，關閉連線並移除
                if client.connected:
                    client.close()
                del _tcp_instances[self._endpoint]
            else:
                _tcp_instances[self._endpoint] = (client, lock, ref_count - 1)

    async def connect(self) -> None:
        """建立 TCP 連線"""
        client, lock = await self._get_shared_resources()
        async with lock:
            if not client.connected:
                connected = await client.connect()
                if not connected:
                    raise ModbusError(f"無法連線到 {self._endpoint}")

    async def disconnect(self) -> None:
        """斷開 TCP 連線（釋放參考計數）"""
        await self._release_shared_resources()

    def is_connected(self) -> bool:
        """檢查連線狀態"""
        if self._endpoint not in _tcp_instances:
            return False
        client, _, _ = _tcp_instances[self._endpoint]
        return client.connected

    # ========== 讀取操作 (with shared lock) ==========

    async def read_coils(self, address: int, count: int) -> list[bool]:
        """讀取線圈狀態 (FC 0x01)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.read_coils(
                address=address,
                count=count,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"讀取線圈失敗: {response}")
            return list(response.bits[:count])

    async def read_discrete_inputs(self, address: int, count: int) -> list[bool]:
        """讀取離散輸入 (FC 0x02)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.read_discrete_inputs(
                address=address,
                count=count,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"讀取離散輸入失敗: {response}")
            return list(response.bits[:count])

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        """讀取保持暫存器 (FC 0x03)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.read_holding_registers(
                address=address,
                count=count,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"讀取保持暫存器失敗: {response}")
            return list(response.registers)

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        """讀取輸入暫存器 (FC 0x04)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.read_input_registers(
                address=address,
                count=count,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"讀取輸入暫存器失敗: {response}")
            return list(response.registers)

    # ========== 寫入操作 (with shared lock) ==========

    async def write_single_coil(self, address: int, value: bool) -> None:
        """寫入單一線圈 (FC 0x05)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.write_coil(
                address=address,
                value=value,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"寫入線圈失敗: {response}")

    async def write_single_register(self, address: int, value: int) -> None:
        """寫入單一暫存器 (FC 0x06)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.write_register(
                address=address,
                value=value,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"寫入暫存器失敗: {response}")

    async def write_multiple_coils(self, address: int, values: list[bool]) -> None:
        """寫入多個線圈 (FC 0x0F)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.write_coils(
                address=address,
                values=values,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"寫入多個線圈失敗: {response}")

    async def write_multiple_registers(self, address: int, values: list[int]) -> None:
        """寫入多個暫存器 (FC 0x10)"""
        client, lock = await self._get_shared_resources()
        async with lock:
            response = await client.write_registers(
                address=address,
                values=values,
                **slave_kwarg(self._config.unit_id),
            )
            if response.isError():
                raise ModbusError(f"寫入多個暫存器失敗: {response}")


__all__ = [
    "PymodbusTcpClient",
    "PymodbusRtuClient",
    "SharedPymodbusTcpClient",
]

