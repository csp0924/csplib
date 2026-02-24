# =============== Modbus Server Tests - Register Block ===============
#
# RegisterBlock 單元測試

import pytest

from csp_lib.modbus import ByteOrder, Float32, Int16, RegisterOrder, UInt16, UInt32
from csp_lib.modbus_server.config import SimulatedPoint
from csp_lib.modbus_server.register_block import RegisterBlock


class TestRegisterBlock:
    """RegisterBlock 基本操作測試"""

    def setup_method(self):
        self.block = RegisterBlock()

    def test_register_point_and_get_value(self):
        """註冊 point 並讀取初始值"""
        point = SimulatedPoint(name="voltage", address=0, data_type=Float32(), initial_value=380.0)
        self.block.register_point(point)
        value = self.block.get_value("voltage")
        assert abs(value - 380.0) < 0.01

    def test_set_and_get_value(self):
        """設定並讀取值"""
        point = SimulatedPoint(name="power", address=0, data_type=Float32(), initial_value=0.0)
        self.block.register_point(point)

        self.block.set_value("power", 100.5)
        assert abs(self.block.get_value("power") - 100.5) < 0.01

    def test_uint16_value(self):
        """UInt16 值操作"""
        point = SimulatedPoint(name="status", address=0, data_type=UInt16(), initial_value=1)
        self.block.register_point(point)

        assert self.block.get_value("status") == 1
        self.block.set_value("status", 42)
        assert self.block.get_value("status") == 42

    def test_int16_signed_value(self):
        """Int16 帶符號值操作"""
        point = SimulatedPoint(name="temp", address=0, data_type=Int16(), initial_value=-10)
        self.block.register_point(point)

        assert self.block.get_value("temp") == -10

    def test_uint32_value(self):
        """UInt32 值操作（跨 2 registers）"""
        point = SimulatedPoint(name="energy", address=0, data_type=UInt32(), initial_value=100000)
        self.block.register_point(point)

        assert self.block.get_value("energy") == 100000

    def test_multiple_points(self):
        """多個 point 不互相干擾"""
        f32 = Float32()
        points = [
            SimulatedPoint(name="v", address=0, data_type=f32, initial_value=380.0),
            SimulatedPoint(name="i", address=2, data_type=f32, initial_value=10.0),
            SimulatedPoint(name="p", address=4, data_type=f32, initial_value=3800.0),
        ]
        self.block.register_points(points)

        assert abs(self.block.get_value("v") - 380.0) < 0.01
        assert abs(self.block.get_value("i") - 10.0) < 0.01
        assert abs(self.block.get_value("p") - 3800.0) < 0.1

    def test_unknown_point_raises(self):
        """存取未知 point 拋出 KeyError"""
        with pytest.raises(KeyError):
            self.block.get_value("nonexistent")

        with pytest.raises(KeyError):
            self.block.set_value("nonexistent", 0)


class TestRegisterBlockRaw:
    """RegisterBlock raw 操作測試"""

    def setup_method(self):
        self.block = RegisterBlock()

    def test_get_raw(self):
        """取得原始 register 值"""
        point = SimulatedPoint(name="test", address=10, data_type=UInt16(), initial_value=42)
        self.block.register_point(point)

        raw = self.block.get_raw(10, 1)
        assert raw == [42]

    def test_set_raw(self):
        """設定原始 register 值"""
        self.block.set_raw(0, [100, 200, 300])
        assert self.block.get_raw(0, 3) == [100, 200, 300]

    def test_raw_extends_registers(self):
        """超出範圍時自動擴展"""
        block = RegisterBlock(size=10)
        block.set_raw(8, [1, 2, 3, 4])
        assert block.get_raw(8, 4) == [1, 2, 3, 4]


class TestRegisterBlockFindPoints:
    """RegisterBlock point 查找測試"""

    def setup_method(self):
        self.block = RegisterBlock()
        f32 = Float32()
        u16 = UInt16()
        self.block.register_point(
            SimulatedPoint(name="voltage", address=0, data_type=f32, initial_value=380.0)
        )
        self.block.register_point(
            SimulatedPoint(name="power", address=2, data_type=f32, initial_value=0.0, writable=True)
        )
        self.block.register_point(
            SimulatedPoint(name="status", address=4, data_type=u16, initial_value=1)
        )

    def test_find_point_at_address(self):
        """查找指定 address 的 point"""
        point = self.block.find_point_at_address(0)
        assert point is not None
        assert point.name == "voltage"

        # Float32 佔 2 registers，address 1 也屬於 voltage
        point = self.block.find_point_at_address(1)
        assert point is not None
        assert point.name == "voltage"

    def test_find_point_not_found(self):
        """找不到 point"""
        assert self.block.find_point_at_address(100) is None

    def test_find_affected_points(self):
        """查找受寫入影響的 writable points"""
        affected = self.block.find_affected_points(2, 2)
        assert len(affected) == 1
        assert affected[0].name == "power"

    def test_find_affected_readonly_excluded(self):
        """唯讀 point 不被包含"""
        affected = self.block.find_affected_points(0, 2)
        assert len(affected) == 0


class TestRegisterBlockCodecConsistency:
    """RegisterBlock 與 ModbusCodec 編碼一致性測試"""

    def test_float32_roundtrip(self):
        """Float32 編碼/解碼一致"""
        from csp_lib.modbus import ModbusCodec

        codec = ModbusCodec()
        block = RegisterBlock()
        point = SimulatedPoint(name="test", address=0, data_type=Float32(), initial_value=0.0)
        block.register_point(point)

        # 透過 block 設定值
        block.set_value("test", 123.456)

        # 直接用 codec 解碼同一段 registers
        raw = block.get_raw(0, 2)
        codec_value = codec.decode(Float32(), raw)

        block_value = block.get_value("test")
        assert abs(codec_value - block_value) < 0.001
