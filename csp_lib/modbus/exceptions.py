# =============== Modbus Exceptions ===============
#
# Modbus 模組例外類型定義
#
# 例外繼承結構：
#   ModbusError (基礎)
#   ├── ModbusEncodeError (編碼錯誤)
#   ├── ModbusDecodeError (解碼錯誤)
#   ├── ModbusConfigError (設定錯誤)
#   ├── ModbusCircuitBreakerError (斷路器開啟)
#   └── ModbusQueueFullError (請求佇列已滿)

from __future__ import annotations


class ModbusError(Exception):
    """
    Modbus 基礎例外

    所有 Modbus 相關例外的父類別，方便統一捕捉。

    Attributes:
        address: Modbus 暫存器起始位址
        unit_id: 設備位址 (slave ID)
        function_code: Modbus 功能碼 (e.g., "FC03")
    """

    def __init__(
        self,
        message: str = "",
        *,
        address: int | None = None,
        unit_id: int | None = None,
        function_code: str | None = None,
    ) -> None:
        self.address = address
        self.unit_id = unit_id
        self.function_code = function_code
        context_parts: list[str] = []
        if address is not None:
            context_parts.append(f"addr={address}")
        if unit_id is not None:
            context_parts.append(f"unit={unit_id}")
        if function_code is not None:
            context_parts.append(f"fc={function_code}")
        full_msg = f"{message} [{', '.join(context_parts)}]" if context_parts else message
        super().__init__(full_msg)


class ModbusEncodeError(ModbusError):
    """
    編碼錯誤

    當編碼過程失敗時拋出，常見原因：
    - 值超出資料類型允許範圍 (e.g., int16 超過 32767)
    - 類型不符 (e.g., 傳入字串給數值類型)
    """


class ModbusDecodeError(ModbusError):
    """
    解碼錯誤

    當解碼過程失敗時拋出，常見原因：
    - 暫存器資料長度不足
    - 資料格式錯誤 (e.g., 無效的 IEEE 754 格式)
    """


class ModbusConfigError(ModbusError):
    """
    設定錯誤

    當設定參數無效時拋出，常見原因：
    - 無效的連線參數 (e.g., 負的 port 號)
    - 無效的資料類型參數 (e.g., bit_width 非 16 的倍數)
    """


class ModbusCircuitBreakerError(ModbusError):
    """
    斷路器開啟錯誤

    當某個 unit_id 的斷路器處於 OPEN 狀態時拋出，
    表示該設備連續失敗次數已達閾值，暫時停止請求。

    Attributes:
        unit_id: 觸發斷路器的設備位址
    """

    def __init__(self, unit_id: int, message: str | None = None) -> None:
        super().__init__(message or f"Circuit breaker is open for unit_id={unit_id}", unit_id=unit_id)


class ModbusQueueFullError(ModbusError):
    """
    請求佇列已滿錯誤

    當請求佇列達到 max_queue_size 上限時拋出。
    """


__all__ = [
    "ModbusError",
    "ModbusEncodeError",
    "ModbusDecodeError",
    "ModbusConfigError",
    "ModbusCircuitBreakerError",
    "ModbusQueueFullError",
]
