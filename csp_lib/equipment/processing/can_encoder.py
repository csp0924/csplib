# =============== Equipment Processing - CAN Encoder ===============
#
# CAN 訊框編碼器
#
# 將物理值編碼為 CAN 訊框位元資料。
# 與 CANFrameParser（解碼方向）對稱。

from __future__ import annotations

import threading
from dataclasses import dataclass

from .can_parser import CANField


@dataclass(frozen=True, slots=True)
class CANSignalDefinition:
    """
    CAN 信號定義（含 CAN ID）

    組合 CANField 並加上所屬的 CAN ID，用於發送方向。

    Attributes:
        can_id: CAN 訊框 ID
        field: 欄位定義（復用 CANField）
        min_raw: 原始值下限（None 表示不限制）
        max_raw: 原始值上限（None 表示不限制）
    """

    can_id: int
    field: CANField
    min_raw: int | None = None
    max_raw: int | None = None


@dataclass(frozen=True, slots=True)
class FrameBufferConfig:
    """
    Frame Buffer 配置

    Attributes:
        can_id: CAN 訊框 ID
        initial_data: 初始資料（8 bytes），預設全零
    """

    can_id: int
    initial_data: bytes = b"\x00" * 8


class CANFieldEncoder:
    """
    CAN 欄位編碼器

    CANFrameParser._extract_field 的逆運算。
    將物理值編碼回 CAN 訊框的位元欄位。
    """

    @staticmethod
    def encode_physical(signal: CANSignalDefinition, physical_value: float | int) -> int:
        """
        物理值 -> raw 值

        逆運算：raw = round((physical - offset) / resolution)
        結果會 clamp 到 bit 範圍內。

        Args:
            signal: 信號定義
            physical_value: 物理值

        Returns:
            原始整數值
        """
        field = signal.field
        raw = round((physical_value - field.offset) / field.resolution)

        # clamp 到 bit 範圍
        max_val = (1 << field.bit_length) - 1
        min_val = 0

        # 使用自定義範圍（如果有）
        if signal.min_raw is not None:
            min_val = signal.min_raw
        if signal.max_raw is not None:
            max_val = min(max_val, signal.max_raw)

        return max(min_val, min(max_val, raw))

    @staticmethod
    def pack_field(buffer_int: int, signal: CANSignalDefinition, raw_value: int) -> int:
        """
        Read-modify-write: 將 raw 值寫入 buffer 的指定位元範圍

        清除目標 bit 範圍，然後寫入新值。其他 bit 不受影響。

        Args:
            buffer_int: 當前 buffer 的 64-bit 整數值（little-endian 解讀）
            signal: 信號定義
            raw_value: 要寫入的原始值

        Returns:
            更新後的 64-bit 整數值
        """
        field = signal.field
        mask = (1 << field.bit_length) - 1

        # 清除目標位元
        clear_mask = ~(mask << field.start_bit) & 0xFFFFFFFFFFFFFFFF
        buffer_int &= clear_mask

        # 寫入新值
        buffer_int |= (raw_value & mask) << field.start_bit

        return buffer_int


class CANFrameBuffer:
    """
    CAN 訊框緩衝區

    為每個發送用 CAN ID 維護 8-byte 緩衝區。
    支援 read-modify-write 操作，確保修改一個信號不影響同一訊框中的其他 bit。
    Thread-safe（使用 threading.Lock，因為是純記憶體操作）。

    使用範例::

        buffer = CANFrameBuffer(
            configs=[FrameBufferConfig(can_id=0x200)],
            signals=[
                CANSignalDefinition(0x200, CANField("power", 0, 16, resolution=1.0)),
                CANSignalDefinition(0x200, CANField("mode", 16, 4, resolution=1.0)),
            ],
        )
        buffer.set_signal("power", 5000)   # 只改 bit 0-15
        buffer.set_signal("mode", 3)       # 只改 bit 16-19，其他不變
        frame = buffer.get_frame(0x200)     # 取得完整 8 bytes
    """

    def __init__(
        self,
        configs: list[FrameBufferConfig],
        signals: list[CANSignalDefinition],
    ) -> None:
        self._lock = threading.Lock()

        # 信號名稱 -> 信號定義
        self._signals: dict[str, CANSignalDefinition] = {}
        for sig in signals:
            self._signals[sig.field.name] = sig

        # CAN ID -> 64-bit int buffer（以 little-endian 解讀，與 CANFrameParser 一致）
        self._buffers: dict[int, int] = {}
        for cfg in configs:
            self._buffers[cfg.can_id] = int.from_bytes(cfg.initial_data[:8].ljust(8, b"\x00"), byteorder="little")

    def set_signal(self, name: str, physical_value: float | int) -> None:
        """
        設定信號的物理值

        將物理值編碼為 raw 值，然後寫入對應的 bit 範圍。

        Args:
            name: 信號名稱
            physical_value: 物理值

        Raises:
            KeyError: 信號名稱不存在
        """
        signal = self._signals.get(name)
        if signal is None:
            raise KeyError(f"Signal '{name}' not found. Available: {list(self._signals.keys())}")

        raw = CANFieldEncoder.encode_physical(signal, physical_value)
        self._write_raw(signal, raw)

    def set_raw(self, name: str, raw_value: int) -> None:
        """
        設定信號的原始值

        直接寫入 raw 值到對應的 bit 範圍。

        Args:
            name: 信號名稱
            raw_value: 原始整數值

        Raises:
            KeyError: 信號名稱不存在
        """
        signal = self._signals.get(name)
        if signal is None:
            raise KeyError(f"Signal '{name}' not found. Available: {list(self._signals.keys())}")

        self._write_raw(signal, raw_value)

    def get_frame(self, can_id: int) -> bytes:
        """
        取得指定 CAN ID 的完整 8-byte 訊框資料

        Args:
            can_id: CAN 訊框 ID

        Returns:
            8 bytes 訊框資料

        Raises:
            KeyError: CAN ID 不存在
        """
        with self._lock:
            buf = self._buffers.get(can_id)
            if buf is None:
                raise KeyError(f"CAN ID 0x{can_id:03X} not found in buffer")
            return buf.to_bytes(8, byteorder="little")

    def get_signal(self, name: str) -> CANSignalDefinition:
        """
        取得信號定義

        Args:
            name: 信號名稱

        Returns:
            信號定義

        Raises:
            KeyError: 信號名稱不存在
        """
        signal = self._signals.get(name)
        if signal is None:
            raise KeyError(f"Signal '{name}' not found. Available: {list(self._signals.keys())}")
        return signal

    def _write_raw(self, signal: CANSignalDefinition, raw_value: int) -> None:
        """內部方法：將 raw 值寫入 buffer"""
        with self._lock:
            buf = self._buffers.get(signal.can_id)
            if buf is None:
                raise KeyError(f"CAN ID 0x{signal.can_id:03X} not found in buffer")
            self._buffers[signal.can_id] = CANFieldEncoder.pack_field(buf, signal, raw_value)


__all__ = [
    "CANSignalDefinition",
    "FrameBufferConfig",
    "CANFieldEncoder",
    "CANFrameBuffer",
]
