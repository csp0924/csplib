# =============== Equipment IO - Reader ===============
#
# 群組讀取器
#
# 負責執行 Modbus 讀取並解碼群組資料

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Sequence

from csp_lib.core import get_logger
from csp_lib.core.errors import CommunicationError, ConfigurationError
from csp_lib.modbus.enums import FunctionCode
from csp_lib.modbus.exceptions import ModbusError

from .base import ReadGroup

logger = get_logger(__name__)

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
        max_concurrent_reads: 最大並行讀取數
            - TCP client: 預設 3（可同時多個請求）
            - SharedTCP/RTU client: 預設 1（串列讀取）

    使用範例：
        from csp_lib.equipment.transport import GroupReader, PointGrouper, ReadScheduler

        grouper = PointGrouper()
        scheduler = ReadScheduler(always_groups=grouper.group(points))

        # TCP 設備可並行讀取
        reader = GroupReader(client, max_concurrent_reads=3)

        # RTU/SharedTCP 設備需串列讀取
        reader = GroupReader(client, max_concurrent_reads=1)

        # 讀取下一批群組
        groups = scheduler.get_next_groups()
        data = await reader.read_many(groups)
    """

    def __init__(
        self,
        client: AsyncModbusClientBase,
        unit_id: int = 1,
        address_offset: int = 0,
        max_concurrent_reads: int = 1,
    ):
        """
        初始化群組讀取器

        Args:
            client: Modbus 客戶端
            unit_id: 設備位址 (Slave ID)
            address_offset: 位址偏移（PLC 1-based 定址時設為 1）
            max_concurrent_reads: 最大並行讀取數（預設 1 = 串列讀取）
        """
        if max_concurrent_reads < 1:
            raise ConfigurationError(f"max_concurrent_reads 必須 >= 1，收到: {max_concurrent_reads}")

        self._client = client
        self._default_unit_id = unit_id
        self._address_offset = address_offset
        self._max_concurrent_reads = max_concurrent_reads
        self._semaphore = asyncio.Semaphore(max_concurrent_reads)
        # Per-unit serialization: 保護單一 slave 不被自己多個 in-flight 請求打爆；
        # 跨 unit_id 仍可並行（SMA multi-unit 場景），限於全局 _semaphore 上限。
        self._unit_semaphores: dict[int, asyncio.Semaphore] = {}

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
        uid = group.unit_id if group.unit_id is not None else self._default_unit_id
        unit_sem = self._unit_semaphores.setdefault(uid, asyncio.Semaphore(1))
        async with self._semaphore, unit_sem:
            raw_data = await self._read_from_device(group, uid)
            return self._decode(group, raw_data)

    async def read_many(self, groups: Sequence[ReadGroup]) -> dict[str, Any]:
        """
        讀取多個群組並合併結果

        若 max_concurrent_reads > 1，會並行讀取多個群組。

        Args:
            groups: 讀取群組列表

        Returns:
            合併的 {點位名稱: 值} 字典
        """
        if self._max_concurrent_reads == 1:
            # 串列讀取（RTU/SharedTCP）
            result: dict[str, Any] = {}
            for group in groups:
                data = await self.read(group)
                result.update(data)
            return result

        # 並行讀取（TCP）
        # SEC-016：使用 return_exceptions=True 避免單一 group 失敗讓整批結果丟失。
        # - 成功：merge 進 merged dict
        # - CancelledError 與其他 BaseException（SystemExit/KeyboardInterrupt）：必須
        #   傳播，否則 lifecycle 停機 / 中斷會被吞掉。只有一般 Exception 才 log+continue
        tasks = [self.read(group) for group in groups]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged: dict[str, Any] = {}
        for group, outcome in zip(groups, results, strict=True):
            if isinstance(outcome, BaseException) and not isinstance(outcome, Exception):
                # CancelledError / SystemExit / KeyboardInterrupt 等：直接 re-raise
                raise outcome
            if isinstance(outcome, Exception):
                logger.warning(
                    f"GroupReader.read_many: group read failed "
                    f"(fc={group.function_code}, addr={group.start_address}, count={group.count}): {outcome}"
                )
                continue
            merged.update(outcome)
        return merged

    async def _read_from_device(self, group: ReadGroup, unit_id: int) -> list[int] | list[bool]:
        """
        根據 function_code 讀取資料

        Args:
            group: 讀取群組
            unit_id: 此次 Modbus 請求的 slave address（由 caller resolve，
                優先用 ``group.unit_id``，fallback ``self._default_unit_id``）

        Returns:
            原始暫存器/線圈資料

        Raises:
            ConfigurationError: 不支援的 FunctionCode
            CommunicationError: Modbus 通訊錯誤
        """
        address = group.start_address + self._address_offset
        count = group.count
        function_code = group.function_code

        try:
            if function_code == FunctionCode.READ_COILS:
                return list(await self._client.read_coils(address, count, unit_id))
            elif function_code == FunctionCode.READ_DISCRETE_INPUTS:
                return list(await self._client.read_discrete_inputs(address, count, unit_id))
            elif function_code == FunctionCode.READ_HOLDING_REGISTERS:
                return list(await self._client.read_holding_registers(address, count, unit_id))
            elif function_code == FunctionCode.READ_INPUT_REGISTERS:
                return list(await self._client.read_input_registers(address, count, unit_id))
            else:
                raise ConfigurationError(f"不支援的 Function Code: {function_code}")
        except (ConfigurationError, CommunicationError):
            raise
        except ModbusError as e:
            raise CommunicationError("unknown", f"Modbus 通訊錯誤: {e}") from e

    def _decode(self, group: ReadGroup, raw_data: list[int] | list[bool]) -> dict[str, Any]:
        """
        解碼群組讀取結果

        Args:
            group: 讀取群組
            raw_data: 原始資料

        Returns:
            {點位名稱: 值} 字典

        Raises:
            CommunicationError: 資料長度不足以解碼點位
        """
        result: dict[str, Any] = {}

        for point in group.points:
            # 計算偏移
            offset = point.address - group.start_address
            length = point.data_type.register_count

            # 提取資料切片並驗證長度
            data_slice = list(raw_data[offset : offset + length])
            if len(data_slice) < length:
                raise CommunicationError(
                    "unknown",
                    f"資料不足以解碼點位 '{point.name}': "
                    f"期望 {length} 個暫存器，實際 {len(data_slice)} "
                    f"(offset={offset}, group.count={group.count})",
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
