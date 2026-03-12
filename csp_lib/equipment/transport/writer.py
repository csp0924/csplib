# =============== Equipment IO - Writer ===============
#
# 驗證寫入器
#
# 提供寫入前驗證與寫後讀回確認

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from csp_lib.core import get_logger
from csp_lib.core.errors import ConfigurationError
from csp_lib.modbus.enums import FunctionCode
from csp_lib.modbus.exceptions import ModbusError

logger = get_logger(__name__)

if TYPE_CHECKING:
    from csp_lib.equipment.core.point import WritePoint
    from csp_lib.modbus import AsyncModbusClientBase


class WriteStatus(Enum):
    SUCCESS = "success"
    VALIDATION_FAILED = "validation_failed"
    WRITE_FAILED = "write_failed"
    VERIFICATION_FAILED = "verification_failed"


@dataclass(frozen=True)
class WriteResult:
    """寫入結果"""

    status: WriteStatus
    point_name: str
    value: Any
    error_message: str = ""


class ValidatedWriter:
    """
    驗證寫入器

    提供寫入前驗證與可選的寫後讀回確認。

    Attributes:
        client: Modbus 客戶端
        address_offset: 位址偏移（PLC 1-based: offset=1）
    """

    def __init__(self, client: AsyncModbusClientBase, unit_id: int = 1, address_offset: int = 0):
        self._client = client
        self._unit_id = unit_id
        self._address_offset = address_offset

    async def write(self, point: WritePoint, value: Any, verify: bool = False) -> WriteResult:
        """
        寫入點位

        Args:
            point: 寫入點位定義
            value: 要寫入的值
            verify: 是否寫後讀回驗證

        Returns:
            寫入結果
        """
        logger.debug(
            f"[ValidatedWriter] write 開始: point={point.name}, value={value}, type={type(value).__name__}, verify={verify}"
        )

        if point.validator and not point.validator.validate(value):
            msg = point.validator.get_error_message(value)
            logger.warning(f"[ValidatedWriter] 驗證失敗: point={point.name}, value={value}, error={msg}")
            return WriteResult(
                status=WriteStatus.VALIDATION_FAILED,
                point_name=point.name,
                value=value,
                error_message=msg,
            )

        try:
            # 寫入前管線轉換（使用者值 → 暫存器值）
            if point.pipeline is not None:
                original = value
                value = point.pipeline.process(value)
                logger.debug(f"[ValidatedWriter] pipeline 轉換: {original} → {value}")

            # pipeline 回傳 float 但整數型態需要 int，自動轉換整數值
            if isinstance(value, float) and value.is_integer():
                value = int(value)
                logger.debug(f"[ValidatedWriter] float→int 自動轉換: {value}")

            # 編碼
            encoded = self._encode(point, value)
            logger.debug(f"[ValidatedWriter] 編碼完成: point={point.name}, encoded={encoded}, fc={point.function_code}")

            await self._write_to_device(point, encoded)
            logger.debug(f"[ValidatedWriter] 寫入設備完成: point={point.name}")

            if verify:
                read_value = await self._read_back(point)
                logger.debug(f"[ValidatedWriter] 讀回驗證: point={point.name}, 期望={value}, 實際={read_value}")
                if not self._values_equal(value, read_value):
                    return WriteResult(
                        status=WriteStatus.VERIFICATION_FAILED,
                        point_name=point.name,
                        value=value,
                        error_message=f"寫入後讀回值不匹配: 期望 {value}, 實際 {read_value}",
                    )

            logger.info(f"[ValidatedWriter] write 成功: point={point.name}, value={value}")
            return WriteResult(
                status=WriteStatus.SUCCESS,
                point_name=point.name,
                value=value,
            )

        except ConfigurationError:
            raise
        except ModbusError as e:
            logger.error(f"[ValidatedWriter] Modbus 錯誤: point={point.name}, error={e}")
            return WriteResult(
                status=WriteStatus.WRITE_FAILED, point_name=point.name, value=value, error_message=str(e)
            )
        except Exception as e:
            logger.error(f"[ValidatedWriter] 未預期錯誤: point={point.name}, error={e}")
            return WriteResult(
                status=WriteStatus.WRITE_FAILED, point_name=point.name, value=value, error_message=str(e)
            )

    def _encode(self, point: WritePoint, value: Any) -> list[int] | int | bool:
        """編碼值"""
        registers = point.data_type.encode(
            value=value,
            byte_order=point.byte_order,
            register_order=point.register_order,
        )

        function_code = point.function_code

        if function_code in [FunctionCode.WRITE_SINGLE_COIL, FunctionCode.WRITE_SINGLE_REGISTER]:
            if len(registers) != 1:
                raise ConfigurationError(f"Function Code {function_code} 只能寫入一個暫存器")
            if function_code == FunctionCode.WRITE_SINGLE_COIL:
                return bool(registers[0])
            return registers[0]
        return registers

    async def _write_to_device(self, point: WritePoint, encoded: list[int] | int | bool):
        """寫入暫存器"""
        address = point.address + self._address_offset
        function_code = point.function_code
        logger.debug(
            f"[ValidatedWriter] _write_to_device: point={point.name}, address={address} "
            f"(base={point.address}+offset={self._address_offset}), fc={function_code}, "
            f"unit_id={self._unit_id}, encoded={encoded}"
        )

        if function_code == FunctionCode.WRITE_SINGLE_COIL:
            await self._client.write_single_coil(address=address, value=bool(encoded), unit_id=self._unit_id)
        elif function_code == FunctionCode.WRITE_SINGLE_REGISTER:
            await self._client.write_single_register(address=address, value=int(encoded), unit_id=self._unit_id)  # type: ignore[arg-type]
        elif function_code == FunctionCode.WRITE_MULTIPLE_COILS:
            if isinstance(encoded, list):
                await self._client.write_multiple_coils(
                    address=address, values=[bool(v) for v in encoded], unit_id=self._unit_id
                )
            else:
                await self._client.write_multiple_coils(address=address, values=[bool(encoded)], unit_id=self._unit_id)
        elif function_code == FunctionCode.WRITE_MULTIPLE_REGISTERS:
            if isinstance(encoded, list):
                await self._client.write_multiple_registers(address=address, values=encoded, unit_id=self._unit_id)
            else:
                await self._client.write_multiple_registers(
                    address=address, values=[int(encoded)], unit_id=self._unit_id
                )
        else:
            raise ConfigurationError(f"不支援的 Function Code: {function_code}")

    async def _read_back(self, point: WritePoint) -> Any:
        """讀回驗證"""
        address = point.address + self._address_offset
        register_count = point.data_type.register_count
        function_code = point.function_code

        # 根據寫入功能碼選擇對應的讀取功能碼
        if function_code in [FunctionCode.WRITE_SINGLE_COIL, FunctionCode.WRITE_MULTIPLE_COILS]:
            data = await self._client.read_coils(address, register_count, self._unit_id)
        elif function_code in [FunctionCode.WRITE_SINGLE_REGISTER, FunctionCode.WRITE_MULTIPLE_REGISTERS]:
            data = await self._client.read_holding_registers(address, register_count, self._unit_id)  # type: ignore[assignment]
        else:
            raise ConfigurationError(f"不支援的 Function Code: {function_code}")

        return point.data_type.decode(
            registers=list(data),
            byte_order=point.byte_order,
            register_order=point.register_order,
        )

    @staticmethod
    def _values_equal(expected: Any, actual: Any) -> bool:
        """比較值是否相等"""
        if isinstance(expected, float) and isinstance(actual, float):
            return abs(expected - actual) < 1e-6
        return expected == actual


__all__ = [
    "WriteResult",
    "WriteStatus",
    "ValidatedWriter",
]
