# =============== Equipment IO - Reader ===============
#
# 群組讀取器
#
# 負責執行 Modbus 讀取並解碼群組資料

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from csp_lib.modbus.enums import FunctionCode

from .base import ReadGroup

if TYPE_CHECKING:
    from csp_lib.modbus import AsyncModbusClientBase


class GroupReader:
    """
    群組讀取器

    負責執行 Modbus 讀取並解碼群組資料。
    與 ValidatedWriter 對稱，提供完整的 I/O 讀寫能力。

    Attributes:
        client: Modbus 客戶端
        address_offset: 位址偏移（PLC 1-based: offset=1）

    使用範例：
        from csp_lib.equipment.transport import GroupReader, PointGrouper, ReadScheduler

        grouper = PointGrouper()
        scheduler = ReadScheduler(always_groups=grouper.group(points))
        reader = GroupReader(client)

        # 讀取下一批群組
        groups = scheduler.get_next_groups()
        data = await reader.read_many(groups)
    """

    def __init__(self, client: AsyncModbusClientBase, address_offset: int = 0):
        """
        初始化群組讀取器

        Args:
            client: Modbus 客戶端
            address_offset: 位址偏移（PLC 1-based 定址時設為 1）
        """
        self._client = client
        self._address_offset = address_offset

    async def read(self, group: ReadGroup) -> dict[str, Any]:
        """
        讀取單一群組並解碼

        Args:
            group: 讀取群組

        Returns:
            {點位名稱: 值} 字典

        Raises:
            Exception: Modbus 通訊錯誤時傳播原始異常
        """
        raw_data = await self._read_from_device(group)
        return self._decode(group, raw_data)

    async def read_many(self, groups: Sequence[ReadGroup]) -> dict[str, Any]:
        """
        讀取多個群組並合併結果

        Args:
            groups: 讀取群組列表

        Returns:
            合併的 {點位名稱: 值} 字典
        """
        result: dict[str, Any] = {}

        for group in groups:
            data = await self.read(group)
            result.update(data)

        return result

    async def _read_from_device(self, group: ReadGroup) -> list[int] | list[bool]:
        """
        根據 function_code 讀取資料

        Args:
            group: 讀取群組

        Returns:
            原始暫存器/線圈資料

        Raises:
            ValueError: 不支援的 FunctionCode
        """
        address = group.start_address + self._address_offset
        count = group.count
        function_code = group.function_code

        if function_code == FunctionCode.READ_COILS:
            return list(await self._client.read_coils(address, count))
        elif function_code == FunctionCode.READ_DISCRETE_INPUTS:
            return list(await self._client.read_discrete_inputs(address, count))
        elif function_code == FunctionCode.READ_HOLDING_REGISTERS:
            return list(await self._client.read_holding_registers(address, count))
        elif function_code == FunctionCode.READ_INPUT_REGISTERS:
            return list(await self._client.read_input_registers(address, count))
        else:
            raise ValueError(f"不支援的 Function Code: {function_code}")

    def _decode(self, group: ReadGroup, raw_data: list[int] | list[bool]) -> dict[str, Any]:
        """
        解碼群組讀取結果

        Args:
            group: 讀取群組
            raw_data: 原始資料

        Returns:
            {點位名稱: 值} 字典

        Raises:
            ValueError: 資料長度不足以解碼點位
        """
        result: dict[str, Any] = {}

        for point in group.points:
            # 計算偏移
            offset = point.address - group.start_address
            length = point.data_type.register_count

            # 提取資料切片並驗證長度
            data_slice = list(raw_data[offset : offset + length])
            if len(data_slice) < length:
                raise ValueError(
                    f"資料不足以解碼點位 '{point.name}': "
                    f"期望 {length} 個暫存器，實際 {len(data_slice)} "
                    f"(offset={offset}, group.count={group.count})"
                )

            # 解碼
            value = point.data_type.decode(
                registers=data_slice,
                byte_order=point.byte_order,
                register_order=point.register_order,
            )

            if point.pipeline:
                value = point.pipeline.process(value)

            result[point.name] = value

        return result


__all__ = [
    "GroupReader",
]
