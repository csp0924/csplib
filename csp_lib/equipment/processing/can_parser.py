# =============== Equipment Processing - CAN Parser ===============
#
# CAN 訊框解析器
#
# 將 CAN 訊框（8 bytes）解析為多個物理值。
# 支援 Intel (Little Endian) 和 Motorola (Big Endian) 格式。

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class CANField:
    """
    CAN 欄位定義

    Attributes:
        name: 輸出名稱
        start_bit: 起始位元位置 (bit 0 = byte 0 的 LSB)
        bit_length: 位元長度
        resolution: 解析度（乘數），物理值 = raw × resolution + offset
        offset: 偏移量
        decimals: 四捨五入小數位（None 表示不四捨五入）
        as_int: 是否強制轉為整數

    使用範例：
        # 電壓：bit 0~15, 解析度 0.1V
        CANField("v_total", 0, 16, resolution=0.1, decimals=1)

        # 溫度：bit 0~7, offset -40°C
        CANField("temp", 0, 8, resolution=1.0, offset=-40.0, as_int=True)
    """

    name: str
    start_bit: int
    bit_length: int
    resolution: float = 1.0
    offset: float = 0.0
    decimals: int | None = None
    as_int: bool = False


@dataclass
class CANFrameParser:
    """
    CAN 訊框解析器

    將 UInt64 原始值（8 bytes CAN 資料）解析為多個物理值。
    支援 Intel (Little Endian) 格式。

    Attributes:
        source_name: 來源點位名稱（必須是 UInt64 值）
        fields: CAN 欄位定義列表
        remove_source: 是否移除來源點位
        byte_order: 原始值轉 bytes 時的位元組順序
            - "big": UInt64 → bytes 使用 big endian（預設）
            - "little": UInt64 → bytes 使用 little endian

    使用範例：
        parser = CANFrameParser(
            source_name="sys_65522",
            fields=[
                CANField("v_total", 0, 16, 0.1, 0, 1),
                CANField("v_cell_max", 16, 16, 0.001, 0, 3),
                CANField("soc", 48, 8, 0.4, 0, 1),
            ],
        )

    Note:
        CAN 資料解析使用 Intel (Little Endian) 格式：
        1. 先將 UInt64 轉換為 8 bytes（使用 byte_order）
        2. 將 8 bytes 視為 64-bit Little Endian 整數
        3. 從起始位元提取指定長度的位元
        4. 套用解析度和偏移量計算物理值
    """

    source_name: str
    fields: list[CANField]
    remove_source: bool = True
    byte_order: Literal["big", "little"] = "big"

    def process(self, values: dict[str, Any]) -> dict[str, Any]:
        """
        處理值字典，解析 CAN 訊框

        Args:
            values: {點位名稱: 值} 字典

        Returns:
            更新後的字典，包含解析出的欄位
        """
        result = values.copy()
        raw = result.get(self.source_name)

        if raw is not None:
            raw_bytes = self._to_bytes(raw)
            for field in self.fields:
                result[field.name] = self._extract_field(raw_bytes, field)
        else:
            # 來源為 None，所有欄位都設為 None
            for field in self.fields:
                result[field.name] = None

        if self.remove_source:
            result.pop(self.source_name, None)

        return result

    def _to_bytes(self, raw: int) -> bytes:
        """將 UInt64 轉換為 8 bytes"""
        return raw.to_bytes(8, byteorder=self.byte_order)

    def _extract_field(self, raw_bytes: bytes, field: CANField) -> int | float | None:
        """
        從 CAN 資料提取 Intel (Little Endian) 格式的數值

        Args:
            raw_bytes: 8 bytes CAN 資料
            field: 欄位定義

        Returns:
            物理值 = raw × resolution + offset
        """
        # 轉換 8 bytes 為 64-bit Little Endian 整數
        value = int.from_bytes(raw_bytes, byteorder="little")

        # 提取指定位元
        mask = (1 << field.bit_length) - 1
        raw_value = (value >> field.start_bit) & mask

        # 套用公式：physical = raw × resolution + offset
        physical_value = raw_value * field.resolution + field.offset

        # 四捨五入
        if field.decimals is not None:
            physical_value = round(physical_value, field.decimals)

        # 轉整數
        if field.as_int:
            physical_value = int(physical_value)

        return physical_value


__all__ = [
    "CANField",
    "CANFrameParser",
]
