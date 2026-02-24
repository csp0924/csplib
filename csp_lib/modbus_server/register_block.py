# =============== Modbus Server - Register Block ===============
#
# 命名 point → register 映射，使用 ModbusCodec 做 encode/decode

from __future__ import annotations

from typing import Any

from csp_lib.modbus import ByteOrder, ModbusCodec, ModbusDataType, RegisterOrder

from .config import SimulatedPoint

# 預設 register 空間大小
_DEFAULT_REGISTER_SIZE = 1000


class RegisterBlock:
    """
    Register 映射層

    管理命名 point 與 Modbus register 之間的映射。
    使用 ModbusCodec 確保 client/server 編碼一致。
    """

    def __init__(self, size: int = _DEFAULT_REGISTER_SIZE) -> None:
        self._registers: list[int] = [0] * size
        self._codec = ModbusCodec()
        self._point_map: dict[str, SimulatedPoint] = {}
        self._address_to_point: dict[int, SimulatedPoint] = {}

    @property
    def registers(self) -> list[int]:
        return self._registers

    @property
    def point_map(self) -> dict[str, SimulatedPoint]:
        return dict(self._point_map)

    def register_point(self, point: SimulatedPoint) -> None:
        """註冊一個 point 到 register block"""
        self._point_map[point.name] = point
        self._address_to_point[point.address] = point
        # 寫入初始值
        if point.initial_value is not None:
            self._encode_to_registers(point, point.initial_value)

    def register_points(self, points: tuple[SimulatedPoint, ...] | list[SimulatedPoint]) -> None:
        """批次註冊多個 points"""
        for point in points:
            self.register_point(point)

    def set_value(self, name: str, value: Any) -> None:
        """透過名稱設定 point 的值"""
        point = self._point_map.get(name)
        if point is None:
            raise KeyError(f"Unknown point: {name}")
        self._encode_to_registers(point, value)

    def get_value(self, name: str) -> Any:
        """透過名稱取得 point 的值"""
        point = self._point_map.get(name)
        if point is None:
            raise KeyError(f"Unknown point: {name}")
        return self._decode_from_registers(point)

    def get_raw(self, address: int, count: int) -> list[int]:
        """取得原始 register 值（給 pymodbus datastore 使用）"""
        end = address + count
        if end > len(self._registers):
            # 擴展 register 空間
            self._registers.extend([0] * (end - len(self._registers)))
        return self._registers[address:end]

    def set_raw(self, address: int, values: list[int]) -> None:
        """設定原始 register 值（給 pymodbus datastore 使用）"""
        end = address + len(values)
        if end > len(self._registers):
            self._registers.extend([0] * (end - len(self._registers)))
        self._registers[address:end] = values

    def find_point_at_address(self, address: int) -> SimulatedPoint | None:
        """查找涵蓋指定 address 的 point"""
        for point in self._point_map.values():
            start = point.address
            end = start + point.data_type.register_count
            if start <= address < end:
                return point
        return None

    def find_affected_points(self, address: int, count: int) -> list[SimulatedPoint]:
        """查找被影響的所有 writable points"""
        affected = []
        for point in self._point_map.values():
            if not point.writable:
                continue
            p_start = point.address
            p_end = p_start + point.data_type.register_count
            w_start = address
            w_end = address + count
            # 檢查是否有重疊
            if p_start < w_end and w_start < p_end:
                affected.append(point)
        return affected

    def _encode_to_registers(self, point: SimulatedPoint, value: Any) -> None:
        """將值編碼到 register"""
        regs = self._codec.encode(
            data_type=point.data_type,
            value=value,
            byte_order=point.byte_order,
            register_order=point.register_order,
        )
        addr = point.address
        end = addr + len(regs)
        if end > len(self._registers):
            self._registers.extend([0] * (end - len(self._registers)))
        self._registers[addr : addr + len(regs)] = regs

    def _decode_from_registers(self, point: SimulatedPoint) -> Any:
        """從 register 解碼值"""
        count = point.data_type.register_count
        regs = self._registers[point.address : point.address + count]
        return self._codec.decode(
            data_type=point.data_type,
            registers=regs,
            byte_order=point.byte_order,
            register_order=point.register_order,
        )


__all__ = ["RegisterBlock"]
