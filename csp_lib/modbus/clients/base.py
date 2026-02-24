# =============== Modbus Clients - Base ===============
#
# Client 抽象基底類別
#
# 提供 AsyncModbusClientBase 作為 pymodbus 非同步客戶端的基底類別

from __future__ import annotations

from abc import ABC, abstractmethod


class AsyncModbusClientBase(ABC):
    """
    Modbus 非同步客戶端抽象介面

    定義所有非同步 Modbus 客戶端必須實作的方法。
    pymodbus TCP 與 RTU 客戶端皆繼承此類別。

    Note:
        所有讀寫方法皆接受 unit_id 參數，由呼叫端（設備層級）提供。
        這使得多個設備可以共用同一個 Client 連線。

    使用範例：
        >>> class MyClient(AsyncModbusClientBase):
        ...     async def connect(self) -> None:
        ...         # 實作連線邏輯
        ...         pass
    """

    @abstractmethod
    async def connect(self) -> None:
        """建立連線"""

    @abstractmethod
    async def disconnect(self) -> None:
        """斷開連線"""

    @abstractmethod
    async def is_connected(self) -> bool:
        """檢查連線狀態"""

    # ========== 讀取操作 ==========

    @abstractmethod
    async def read_coils(self, address: int, count: int, unit_id: int = 1) -> list[bool]:
        """
        讀取線圈狀態 (Function Code 0x01)

        Args:
            address: 起始位址
            count: 讀取數量
            unit_id: 設備位址 (Slave ID)

        Returns:
            布林值列表
        """

    @abstractmethod
    async def read_discrete_inputs(self, address: int, count: int, unit_id: int = 1) -> list[bool]:
        """
        讀取離散輸入 (Function Code 0x02)

        Args:
            address: 起始位址
            count: 讀取數量
            unit_id: 設備位址 (Slave ID)

        Returns:
            布林值列表
        """

    @abstractmethod
    async def read_holding_registers(self, address: int, count: int, unit_id: int = 1) -> list[int]:
        """
        讀取保持暫存器 (Function Code 0x03)

        Args:
            address: 起始位址
            count: 讀取數量
            unit_id: 設備位址 (Slave ID)

        Returns:
            暫存器值列表 (每個為 0-65535)
        """

    @abstractmethod
    async def read_input_registers(self, address: int, count: int, unit_id: int = 1) -> list[int]:
        """
        讀取輸入暫存器 (Function Code 0x04)

        Args:
            address: 起始位址
            count: 讀取數量
            unit_id: 設備位址 (Slave ID)

        Returns:
            暫存器值列表 (每個為 0-65535)
        """

    # ========== 寫入操作 ==========

    @abstractmethod
    async def write_single_coil(self, address: int, value: bool, unit_id: int = 1) -> None:
        """
        寫入單一線圈 (Function Code 0x05)

        Args:
            address: 線圈位址
            value: 布林值
            unit_id: 設備位址 (Slave ID)
        """

    @abstractmethod
    async def write_single_register(self, address: int, value: int, unit_id: int = 1) -> None:
        """
        寫入單一暫存器 (Function Code 0x06)

        Args:
            address: 暫存器位址
            value: 暫存器值 (0-65535)
            unit_id: 設備位址 (Slave ID)
        """

    @abstractmethod
    async def write_multiple_coils(self, address: int, values: list[bool], unit_id: int = 1) -> None:
        """
        寫入多個線圈 (Function Code 0x0F)

        Args:
            address: 起始位址
            values: 布林值列表
            unit_id: 設備位址 (Slave ID)
        """

    @abstractmethod
    async def write_multiple_registers(self, address: int, values: list[int], unit_id: int = 1) -> None:
        """
        寫入多個暫存器 (Function Code 0x10)

        Args:
            address: 起始位址
            values: 暫存器值列表
            unit_id: 設備位址 (Slave ID)
        """

    # ========== Context Manager ==========

    async def __aenter__(self) -> AsyncModbusClientBase:
        """非同步 Context Manager 進入"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """非同步 Context Manager 離開"""
        await self.disconnect()


__all__ = ["AsyncModbusClientBase"]
