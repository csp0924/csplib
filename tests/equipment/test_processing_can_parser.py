# =============== Equipment Processing Tests - CAN Parser ===============
#
# CAN 訊框解析器單元測試

from csp_lib.equipment.processing.can_parser import CANField, CANFrameParser


class TestCANField:
    """CANField 測試"""

    def test_default_values(self):
        """預設值"""
        field = CANField("test", 0, 8)
        assert field.name == "test"
        assert field.start_bit == 0
        assert field.bit_length == 8
        assert field.resolution == 1.0
        assert field.offset == 0.0
        assert field.decimals is None
        assert field.as_int is False

    def test_all_attributes(self):
        """完整屬性"""
        field = CANField(
            name="voltage",
            start_bit=16,
            bit_length=16,
            resolution=0.1,
            offset=-100.0,
            decimals=2,
            as_int=False,
        )
        assert field.name == "voltage"
        assert field.start_bit == 16
        assert field.bit_length == 16
        assert field.resolution == 0.1
        assert field.offset == -100.0
        assert field.decimals == 2


class TestCANFrameParser:
    """CANFrameParser 測試"""

    # Note: Raw values represent CAN frames where:
    # - UInt64 big endian: byte 0 is MSB (highest byte of the number)
    # - CAN frame byte 0 should be at the HIGH end of the UInt64
    # - Example: CAN bytes [0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    #            -> UInt64 = 0x5500000000000000

    def test_single_field_extraction(self):
        """單一欄位提取"""
        parser = CANFrameParser(
            source_name="raw",
            fields=[CANField("value", 0, 8)],
        )
        # CAN bytes: [0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        # bit 0-7 (byte 0) = 0x55 = 85
        raw = 0x5500000000000000
        result = parser.process({"raw": raw})
        assert result["value"] == 85
        assert "raw" not in result  # 預設移除來源

    def test_multiple_fields(self):
        """多欄位提取"""
        parser = CANFrameParser(
            source_name="can_data",
            fields=[
                CANField("field0", 0, 8),
                CANField("field1", 8, 8),
                CANField("field2", 16, 16),
            ],
        )
        # CAN bytes: [0x01, 0x02, 0x01, 0x02, 0x00, 0x00, 0x00, 0x00]
        # Little endian interpretation:
        # - bit 0-7 (byte 0): 0x01 = 1
        # - bit 8-15 (byte 1): 0x02 = 2
        # - bit 16-31 (bytes 2-3): 0x0201 = 513
        raw = 0x0102010200000000
        result = parser.process({"can_data": raw})
        assert result["field0"] == 1
        assert result["field1"] == 2
        assert result["field2"] == 513

    def test_resolution_and_offset(self):
        """解析度與偏移量"""
        parser = CANFrameParser(
            source_name="raw",
            fields=[
                CANField("voltage", 0, 16, resolution=0.1, decimals=1),
                CANField("temp", 16, 8, resolution=1.0, offset=-40.0, as_int=True),
            ],
        )
        # CAN bytes: [0xE8, 0x03, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00]
        # - voltage (bit 0-15): little endian 0x03E8 = 1000 -> 100.0V
        # - temp (bit 16-23): 0x64 = 100 -> 100 - 40 = 60°C
        raw = 0xE803640000000000
        result = parser.process({"raw": raw})
        assert result["voltage"] == 100.0
        assert result["temp"] == 60

    def test_remove_source_false(self):
        """保留來源"""
        parser = CANFrameParser(
            source_name="raw",
            fields=[CANField("parsed", 0, 8)],
            remove_source=False,
        )
        raw = 0x5500000000000000  # byte 0 = 0x55
        result = parser.process({"raw": raw})
        assert "raw" in result
        assert result["raw"] == raw
        assert result["parsed"] == 85

    def test_missing_source_returns_none(self):
        """來源不存在返回 None"""
        parser = CANFrameParser(
            source_name="raw",
            fields=[
                CANField("field1", 0, 8),
                CANField("field2", 8, 8),
            ],
        )
        result = parser.process({"other": 123})
        assert result["field1"] is None
        assert result["field2"] is None
        assert result["other"] == 123

    def test_source_is_none(self):
        """來源為 None 返回 None"""
        parser = CANFrameParser(
            source_name="raw",
            fields=[CANField("value", 0, 8)],
        )
        result = parser.process({"raw": None})
        assert result["value"] is None

    def test_bit_extraction_intel_format(self):
        """Intel (Little Endian) 位元提取"""
        parser = CANFrameParser(
            source_name="sys_65522",
            fields=[
                CANField("v_total", 0, 16, resolution=0.1, decimals=1),
                CANField("v_cell_max", 16, 16, resolution=0.001, decimals=3),
            ],
        )
        # CAN bytes: [0x00, 0x0F, 0x80, 0x0D, 0x00, 0x00, 0x00, 0x00]
        # - v_total (bit 0-15): 0x0F00 = 3840 -> 384.0V
        # - v_cell_max (bit 16-31): 0x0D80 = 3456 -> 3.456V
        raw = 0x000F800D00000000
        result = parser.process({"sys_65522": raw})
        assert result["v_total"] == 384.0
        assert result["v_cell_max"] == 3.456

    def test_single_bit_extraction(self):
        """單位元提取（布林旗標）"""
        parser = CANFrameParser(
            source_name="raw",
            fields=[
                CANField("bit0", 0, 1, as_int=True),
                CANField("bit1", 1, 1, as_int=True),
                CANField("bit7", 7, 1, as_int=True),
                CANField("bit8", 8, 1, as_int=True),
            ],
        )
        # CAN bytes: [0x83, 0x01, 0x00, ...]
        # byte 0 = 0x83 = 0b10000011: bit0=1, bit1=1, bit7=1
        # byte 1 = 0x01 = 0b00000001: bit8=1
        raw = 0x8301000000000000
        result = parser.process({"raw": raw})
        assert result["bit0"] == 1
        assert result["bit1"] == 1
        assert result["bit7"] == 1
        assert result["bit8"] == 1

    def test_as_int_flag(self):
        """as_int 強制轉整數"""
        parser = CANFrameParser(
            source_name="raw",
            fields=[
                CANField("float_val", 0, 8, resolution=0.5),
                CANField("int_val", 0, 8, resolution=0.5, as_int=True),
            ],
        )
        # CAN bytes: [0x05, 0x00, ...] -> value = 5 * 0.5 = 2.5
        raw = 0x0500000000000000
        result = parser.process({"raw": raw})
        assert result["float_val"] == 2.5
        assert result["int_val"] == 2

    def test_decimals_rounding(self):
        """小數位四捨五入"""
        parser = CANFrameParser(
            source_name="raw",
            fields=[
                CANField("no_round", 0, 16, resolution=0.001),
                CANField("round_2", 0, 16, resolution=0.001, decimals=2),
                CANField("round_0", 0, 16, resolution=0.001, decimals=0),
            ],
        )
        # CAN bytes: [0x34, 0x12, ...] -> little endian 0x1234 = 4660
        # 4660 * 0.001 = 4.66
        raw = 0x3412000000000000
        result = parser.process({"raw": raw})
        assert result["no_round"] == 4.66
        assert result["round_2"] == 4.66
        assert result["round_0"] == 5.0

    def test_empty_fields_only_removes_source(self):
        """空欄位列表只移除來源"""
        parser = CANFrameParser(
            source_name="reserved",
            fields=[],
            remove_source=True,
        )
        result = parser.process({"reserved": 0x123, "keep": 456})
        assert "reserved" not in result
        assert result["keep"] == 456

    def test_preserves_other_values(self):
        """保留其他點位值"""
        parser = CANFrameParser(
            source_name="raw",
            fields=[CANField("parsed", 0, 8)],
        )
        raw = 0x5500000000000000  # byte 0 = 0x55 = 85
        result = parser.process({"raw": raw, "other": "value", "number": 123})
        assert result["parsed"] == 85
        assert result["other"] == "value"
        assert result["number"] == 123


class TestCANFrameParserIntegration:
    """CANFrameParser 整合測試 - 模擬 NYJMBMU 使用場景"""

    def test_nyjmbmu_pgn65522_parsing(self):
        """模擬 NYJMBMU PGN 65522 解析"""
        parser = CANFrameParser(
            source_name="sys_65522",
            fields=[
                CANField("v_total", 0, 16, resolution=0.1, decimals=1),
                CANField("v_cell_max", 16, 16, resolution=0.001, decimals=3),
                CANField("v_cell_min", 32, 16, resolution=0.001, decimals=3),
                CANField("soc", 48, 8, resolution=0.4, decimals=1),
                CANField("v_cell_max_chain", 56, 8, as_int=True),
            ],
        )

        # 建構測試資料 (CAN bytes in order):
        # byte 0-1: v_total = 3840 -> 0x0F00 -> bytes [0x00, 0x0F]
        # byte 2-3: v_cell_max = 3456 -> 0x0D80 -> bytes [0x80, 0x0D]
        # byte 4-5: v_cell_min = 3200 -> 0x0C80 -> bytes [0x80, 0x0C]
        # byte 6: soc = 200 -> 0xC8
        # byte 7: v_cell_max_chain = 1 -> 0x01
        # CAN bytes: [0x00, 0x0F, 0x80, 0x0D, 0x80, 0x0C, 0xC8, 0x01]
        raw = 0x000F800D800CC801
        result = parser.process({"sys_65522": raw})

        assert result["v_total"] == 384.0
        assert result["v_cell_max"] == 3.456
        assert result["v_cell_min"] == 3.2
        assert result["soc"] == 80.0
        assert result["v_cell_max_chain"] == 1

    def test_nyjmbmu_pgn65523_temperature(self):
        """模擬 NYJMBMU PGN 65523 溫度解析"""
        parser = CANFrameParser(
            source_name="sys_65523",
            fields=[
                CANField("temp_max", 0, 8, offset=-40.0, as_int=True),
                CANField("temp_min", 8, 8, offset=-40.0, as_int=True),
                CANField("i_total", 16, 16, resolution=0.1, offset=-3200.0, decimals=1),
            ],
        )
        # byte 0: temp_max = 85 -> 85 - 40 = 45°C
        # byte 1: temp_min = 60 -> 60 - 40 = 20°C
        # byte 2-3: i_total = 35000 -> 0x88B8 -> bytes [0xB8, 0x88]
        #           35000 * 0.1 - 3200 = 300.0A
        raw = 0x553CB88800000000
        result = parser.process({"sys_65523": raw})

        assert result["temp_max"] == 45
        assert result["temp_min"] == 20
        assert result["i_total"] == 300.0
