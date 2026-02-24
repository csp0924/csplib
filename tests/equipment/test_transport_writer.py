# =============== Equipment Transport Tests - Writer ===============
#
# ValidatedWriter 驗證寫入器單元測試
#
# 測試基於理論正確行為設計，覆蓋：
# - 各 FunctionCode 的寫入邏輯
# - 驗證失敗處理
# - 寫入異常處理
# - 讀回驗證 (verify mode)
# - 浮點數比較
# - address_offset 處理

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.equipment.core.point import WritePoint
from csp_lib.equipment.transport.writer import (
    ValidatedWriter,
    WriteResult,
    WriteStatus,
)
from csp_lib.modbus import Float32, FunctionCode, Int32, UInt16

# ======================== Mock Fixtures ========================


class MockValidator:
    """Mock 驗證器 - 不使用預設參數以確保呼叫正確"""

    def __init__(self, should_pass: bool = True, error_msg: str = "驗證失敗"):
        self.should_pass = should_pass
        self.error_msg = error_msg
        self.last_validated_value = None
        self.last_error_message_value = None

    def validate(self, value: Any) -> bool:
        self.last_validated_value = value
        return self.should_pass

    def get_error_message(self, value: Any) -> str:
        """必須傳入 value 參數，否則會 TypeError"""
        self.last_error_message_value = value
        return self.error_msg


@pytest.fixture
def mock_client() -> AsyncMock:
    """建立 Mock Modbus 客戶端"""
    client = AsyncMock()
    client.write_single_coil = AsyncMock()
    client.write_multiple_coils = AsyncMock()
    client.write_single_register = AsyncMock()
    client.write_multiple_registers = AsyncMock()
    client.read_coils = AsyncMock(return_value=[True])
    client.read_holding_registers = AsyncMock(return_value=[100])
    return client


@pytest.fixture
def writer(mock_client: AsyncMock) -> ValidatedWriter:
    """建立 ValidatedWriter"""
    return ValidatedWriter(client=mock_client)


@pytest.fixture
def writer_with_offset(mock_client: AsyncMock) -> ValidatedWriter:
    """建立帶 offset 的 ValidatedWriter（PLC 1-based）"""
    return ValidatedWriter(client=mock_client, address_offset=1)


# ======================== WriteResult Tests ========================


class TestWriteResult:
    """WriteResult dataclass 測試"""

    def test_success_result(self):
        """成功結果應有正確欄位"""
        result = WriteResult(
            status=WriteStatus.SUCCESS,
            point_name="power",
            value=100,
        )
        assert result.status == WriteStatus.SUCCESS
        assert result.point_name == "power"
        assert result.value == 100
        assert result.error_message == ""

    def test_failed_result_with_message(self):
        """失敗結果應包含錯誤訊息"""
        result = WriteResult(
            status=WriteStatus.WRITE_FAILED,
            point_name="power",
            value=100,
            error_message="連線逾時",
        )
        assert result.status == WriteStatus.WRITE_FAILED
        assert result.error_message == "連線逾時"


# ======================== Basic Write Tests ========================


class TestValidatedWriterBasicWrite:
    """ValidatedWriter 基本寫入測試"""

    @pytest.mark.asyncio
    async def test_write_single_register_success(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """寫入單一暫存器 (FC=6) 成功"""
        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        )
        result = await writer.write(point, 500)

        assert result.status == WriteStatus.SUCCESS
        assert result.point_name == "power"
        assert result.value == 500
        mock_client.write_single_register.assert_called_once_with(address=100, value=500, unit_id=1)

    @pytest.mark.asyncio
    async def test_write_multiple_registers_success(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """寫入多個暫存器 (FC=16) 成功"""
        point = WritePoint(
            name="power",
            address=100,
            data_type=Int32(),
            function_code=FunctionCode.WRITE_MULTIPLE_REGISTERS,
        )
        result = await writer.write(point, 100000)

        assert result.status == WriteStatus.SUCCESS
        mock_client.write_multiple_registers.assert_called_once()
        call_args = mock_client.write_multiple_registers.call_args
        assert call_args.kwargs["address"] == 100
        assert call_args.kwargs["unit_id"] == 1
        # Int32 應編碼為 2 個暫存器
        assert len(call_args.kwargs["values"]) == 2

    @pytest.mark.asyncio
    async def test_write_single_coil_success(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """寫入單一線圈 (FC=5) 成功"""
        point = WritePoint(
            name="switch",
            address=0,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_COIL,
        )
        result = await writer.write(point, 1)

        assert result.status == WriteStatus.SUCCESS
        mock_client.write_single_coil.assert_called_once_with(address=0, value=True, unit_id=1)

    @pytest.mark.asyncio
    async def test_write_multiple_coils_success(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """寫入多個線圈 (FC=15) 成功"""
        point = WritePoint(
            name="switches",
            address=0,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_MULTIPLE_COILS,
        )
        result = await writer.write(point, 1)

        assert result.status == WriteStatus.SUCCESS
        mock_client.write_multiple_coils.assert_called_once()


# ======================== Address Offset Tests ========================


class TestValidatedWriterAddressOffset:
    """address_offset 測試"""

    @pytest.mark.asyncio
    async def test_offset_applied_to_write(self, writer_with_offset: ValidatedWriter, mock_client: AsyncMock):
        """寫入時應套用 address_offset"""
        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        )
        await writer_with_offset.write(point, 500)

        # 100 + 1 = 101
        mock_client.write_single_register.assert_called_once_with(address=101, value=500, unit_id=1)

    @pytest.mark.asyncio
    async def test_offset_applied_to_readback(self, writer_with_offset: ValidatedWriter, mock_client: AsyncMock):
        """讀回驗證時也應套用 address_offset"""
        mock_client.read_holding_registers.return_value = [500]

        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        )
        await writer_with_offset.write(point, 500, verify=True)

        mock_client.read_holding_registers.assert_called_once_with(101, 1, 1)


# ======================== Validation Tests ========================


class TestValidatedWriterValidation:
    """驗證器測試"""

    @pytest.mark.asyncio
    async def test_validation_failed_returns_status(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """驗證失敗時應回傳 VALIDATION_FAILED 狀態"""
        validator = MockValidator(should_pass=False, error_msg="值超出範圍")
        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
            validator=validator,
        )

        result = await writer.write(point, 9999)

        assert result.status == WriteStatus.VALIDATION_FAILED
        assert "值超出範圍" in result.error_message
        mock_client.write_single_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_validation_get_error_message_receives_value(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """get_error_message 應收到正確的 value 參數"""
        validator = MockValidator(should_pass=False, error_msg="值超出範圍")
        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
            validator=validator,
        )
        test_value = 9999

        await writer.write(point, test_value)

        # 確認 validate 和 get_error_message 都收到正確的 value
        assert validator.last_validated_value == test_value
        assert validator.last_error_message_value == test_value

    @pytest.mark.asyncio
    async def test_validation_passed_continues_write(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """驗證通過時應繼續寫入"""
        validator = MockValidator(should_pass=True)
        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
            validator=validator,
        )

        result = await writer.write(point, 500)

        assert result.status == WriteStatus.SUCCESS
        mock_client.write_single_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_validator_skips_validation(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """無驗證器時應直接寫入"""
        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
            validator=None,
        )

        result = await writer.write(point, 500)

        assert result.status == WriteStatus.SUCCESS


# ======================== Write Exception Tests ========================


class TestValidatedWriterExceptions:
    """寫入異常測試"""

    @pytest.mark.asyncio
    async def test_write_exception_returns_failed_status(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """寫入異常時應回傳 WRITE_FAILED 狀態"""
        mock_client.write_single_register.side_effect = Exception("連線逾時")
        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        )

        result = await writer.write(point, 500)

        assert result.status == WriteStatus.WRITE_FAILED
        assert "連線逾時" in result.error_message

    @pytest.mark.asyncio
    async def test_unsupported_function_code_raises(self, writer: ValidatedWriter):
        """不支援的 FunctionCode 應拋 ConfigurationError"""
        point = WritePoint(
            name="invalid",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.READ_HOLDING_REGISTERS,  # 讀取用的 FC
        )

        with pytest.raises(ConfigurationError, match="不支援"):
            await writer.write(point, 500)


# ======================== Verification Tests ========================


class TestValidatedWriterVerification:
    """讀回驗證測試"""

    @pytest.mark.asyncio
    async def test_verify_success_register(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """讀回驗證成功 (register)"""
        mock_client.read_holding_registers.return_value = [500]
        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        )

        result = await writer.write(point, 500, verify=True)

        assert result.status == WriteStatus.SUCCESS
        mock_client.read_holding_registers.assert_called_once_with(100, 1, 1)

    @pytest.mark.asyncio
    async def test_verify_success_coil(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """讀回驗證成功 (coil)"""
        mock_client.read_coils.return_value = [True]
        point = WritePoint(
            name="switch",
            address=0,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_COIL,
        )

        result = await writer.write(point, 1, verify=True)

        assert result.status == WriteStatus.SUCCESS
        mock_client.read_coils.assert_called_once_with(0, 1, 1)

    @pytest.mark.asyncio
    async def test_verify_mismatch_returns_failed(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """讀回值不匹配應回傳 VERIFICATION_FAILED"""
        mock_client.read_holding_registers.return_value = [999]  # 不同於寫入值
        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        )

        result = await writer.write(point, 500, verify=True)

        assert result.status == WriteStatus.VERIFICATION_FAILED
        assert "不匹配" in result.error_message
        assert "500" in result.error_message
        assert "999" in result.error_message

    @pytest.mark.asyncio
    async def test_verify_disabled_skips_readback(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """verify=False 時不應讀回"""
        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        )

        await writer.write(point, 500, verify=False)

        mock_client.read_holding_registers.assert_not_called()


# ======================== Float Comparison Tests ========================


class TestValidatedWriterFloatComparison:
    """浮點數比較測試"""

    def test_values_equal_exact_integers(self):
        """整數相等"""
        assert ValidatedWriter._values_equal(100, 100)
        assert not ValidatedWriter._values_equal(100, 200)

    def test_values_equal_exact_floats(self):
        """浮點數精確相等"""
        assert ValidatedWriter._values_equal(3.14, 3.14)

    def test_values_equal_float_tolerance(self):
        """浮點數容差比較 (1e-6)"""
        # 在容差內應視為相等
        assert ValidatedWriter._values_equal(1.0, 1.0 + 1e-7)
        assert ValidatedWriter._values_equal(1.0, 1.0 - 1e-7)

        # 超出容差應視為不相等
        assert not ValidatedWriter._values_equal(1.0, 1.0 + 1e-5)

    def test_values_equal_mixed_types(self):
        """混合類型比較"""
        # int vs float 相等
        assert ValidatedWriter._values_equal(100, 100.0)

        # 字串比較
        assert ValidatedWriter._values_equal("abc", "abc")
        assert not ValidatedWriter._values_equal("abc", "def")


# ======================== Encoding Edge Cases ========================


class TestValidatedWriterEncoding:
    """編碼邊界情況測試"""

    @pytest.mark.asyncio
    async def test_single_register_fc_with_multi_register_type_raises(self, writer: ValidatedWriter):
        """單一暫存器 FC 搭配多暫存器 DataType 應拋 ConfigurationError"""
        point = WritePoint(
            name="invalid",
            address=100,
            data_type=Int32(),  # 佔 2 個暫存器
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        )

        with pytest.raises(ConfigurationError, match="只能寫入一個暫存器"):
            await writer.write(point, 100)

    @pytest.mark.asyncio
    async def test_write_zero_value(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """寫入零值"""
        point = WritePoint(
            name="power",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        )

        result = await writer.write(point, 0)

        assert result.status == WriteStatus.SUCCESS
        mock_client.write_single_register.assert_called_once_with(address=100, value=0, unit_id=1)

    @pytest.mark.asyncio
    async def test_write_max_uint16_value(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """寫入 UInt16 最大值"""
        point = WritePoint(
            name="max_value",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        )

        result = await writer.write(point, 65535)

        assert result.status == WriteStatus.SUCCESS
        mock_client.write_single_register.assert_called_once_with(address=100, value=65535, unit_id=1)

    @pytest.mark.asyncio
    async def test_write_float32(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """寫入 Float32"""
        point = WritePoint(
            name="temperature",
            address=100,
            data_type=Float32(),
            function_code=FunctionCode.WRITE_MULTIPLE_REGISTERS,
        )

        result = await writer.write(point, 25.5)

        assert result.status == WriteStatus.SUCCESS
        call_args = mock_client.write_multiple_registers.call_args
        assert len(call_args.kwargs["values"]) == 2
        assert call_args.kwargs["unit_id"] == 1


# ======================== Default FunctionCode Tests ========================


class TestValidatedWriterDefaultFunctionCode:
    """預設 FunctionCode 測試"""

    @pytest.mark.asyncio
    async def test_default_fc_is_write_multiple_registers(self, writer: ValidatedWriter, mock_client: AsyncMock):
        """WritePoint 預設 FC 應為 WRITE_MULTIPLE_REGISTERS"""
        point = WritePoint(
            name="value",
            address=100,
            data_type=UInt16(),
            # 不指定 function_code，使用預設值
        )

        result = await writer.write(point, 500)

        assert result.status == WriteStatus.SUCCESS
        mock_client.write_multiple_registers.assert_called_once()
