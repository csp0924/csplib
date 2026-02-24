# =============== Modbus Server Tests - Integration ===============
#
# 端對端整合測試：SimulationServer + pymodbus client

import asyncio

import pytest

from csp_lib.modbus import Float32, ModbusCodec, UInt16
from csp_lib.modbus_server.config import (
    AlarmPointConfig,
    AlarmResetMode,
    ControllabilityMode,
    MicrogridConfig,
    ServerConfig,
)
from csp_lib.modbus_server.microgrid import MicrogridSimulator
from csp_lib.modbus_server.server import SimulationServer
from csp_lib.modbus_server.simulator.load import LoadSimulator
from csp_lib.modbus_server.simulator.pcs import PCSSimulator, default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import PowerMeterSimulator
from csp_lib.modbus_server.simulator.solar import SolarSimulator

# 跳過沒有 pymodbus 的環境
try:
    from pymodbus.client import AsyncModbusTcpClient

    HAS_PYMODBUS = True
except ImportError:
    HAS_PYMODBUS = False

pytestmark = pytest.mark.skipif(not HAS_PYMODBUS, reason="pymodbus not installed")


@pytest.fixture
def codec():
    return ModbusCodec()


class TestServerClientIntegration:
    """SimulationServer + pymodbus client 端對端測試"""

    @pytest.mark.asyncio
    async def test_read_meter_values(self, codec):
        """透過 Modbus client 讀取電表值"""
        meter = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        server = SimulationServer(ServerConfig(port=5030, tick_interval=0.1))
        server.add_simulator(meter)

        async with server:
            await asyncio.sleep(0.2)

            client = AsyncModbusTcpClient("127.0.0.1", port=5030)
            await client.connect()
            try:
                # 讀取 voltage_a (address=0, Float32=2 registers)
                result = await client.read_holding_registers(0, count=2, device_id=1)
                assert not result.isError()
                voltage = codec.decode(Float32(), list(result.registers))
                assert abs(voltage - 380.0) < 1.0
            finally:
                client.close()

    @pytest.mark.asyncio
    async def test_write_pcs_setpoint(self, codec):
        """透過 Modbus client 寫入 PCS setpoint"""
        pcs = PCSSimulator(p_ramp_rate=10000.0, tick_interval=0.1)
        server = SimulationServer(ServerConfig(port=5031, tick_interval=0.1))
        server.add_simulator(pcs)

        async with server:
            await asyncio.sleep(0.2)

            client = AsyncModbusTcpClient("127.0.0.1", port=5031)
            await client.connect()
            try:
                # 先啟動 PCS: write start_cmd=1
                # start_cmd address = 14 (see default_pcs_config layout)
                start_cmd_addr = 14
                result = await client.write_register(start_cmd_addr, 1, device_id=10)
                assert not result.isError()

                await asyncio.sleep(0.15)

                # 寫入 p_setpoint = 50.0 (address=0, Float32)
                regs = codec.encode(Float32(), 50.0)
                result = await client.write_registers(0, regs, device_id=10)
                assert not result.isError()

                # 等待 tick 更新
                await asyncio.sleep(0.3)

                # 讀取 p_actual (address=4, Float32)
                result = await client.read_holding_registers(4, count=2, device_id=10)
                assert not result.isError()
                p_actual = codec.decode(Float32(), list(result.registers))
                # 應該已經接近 50.0（大 ramp_rate）
                assert abs(p_actual - 50.0) < 1.0
            finally:
                client.close()

    @pytest.mark.asyncio
    async def test_multi_device(self, codec):
        """多設備同時運行"""
        meter = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        pcs = PCSSimulator()

        server = SimulationServer(ServerConfig(port=5032, tick_interval=0.1))
        server.add_simulator(meter)
        server.add_simulator(pcs)

        async with server:
            await asyncio.sleep(0.2)

            client = AsyncModbusTcpClient("127.0.0.1", port=5032)
            await client.connect()
            try:
                # 讀取電表 (device_id=1)
                result = await client.read_holding_registers(0, count=2, device_id=1)
                assert not result.isError()
                v_meter = codec.decode(Float32(), list(result.registers))
                assert abs(v_meter - 380.0) < 5.0

                # 讀取 PCS SOC (device_id=10, address=8, Float32)
                result = await client.read_holding_registers(8, count=2, device_id=10)
                assert not result.isError()
                soc = codec.decode(Float32(), list(result.registers))
                assert abs(soc - 50.0) < 0.01
            finally:
                client.close()

    @pytest.mark.asyncio
    async def test_alarm_trigger_and_reset(self, codec):
        """觸發告警 → 讀取 → reset → 驗證清除"""
        alarm_cfg = (
            AlarmPointConfig(alarm_code="OVER_TEMP", bit_position=0, reset_mode=AlarmResetMode.AUTO),
            AlarmPointConfig(alarm_code="DC_OV", bit_position=1, reset_mode=AlarmResetMode.MANUAL),
        )
        config = default_pcs_config(alarm_points=alarm_cfg)
        pcs = PCSSimulator(config=config)

        server = SimulationServer(ServerConfig(port=5033, tick_interval=0.1))
        server.add_simulator(pcs)

        async with server:
            await asyncio.sleep(0.2)

            # 程式觸發告警
            pcs.trigger_alarm("DC_OV")

            client = AsyncModbusTcpClient("127.0.0.1", port=5033)
            await client.connect()
            try:
                # 讀取 alarm_register_2 (address=12, UInt16)
                result = await client.read_holding_registers(12, count=1, device_id=10)
                assert not result.isError()
                alarm_val = result.registers[0]
                assert alarm_val & 0x02 == 2  # bit 1 active

                # 寫入 alarm_reset_cmd (address=13)
                result = await client.write_register(13, 1, device_id=10)
                assert not result.isError()

                await asyncio.sleep(0.15)

                # 重新讀取 → 應已清除
                result = await client.read_holding_registers(12, count=1, device_id=10)
                assert not result.isError()
                assert result.registers[0] == 0
            finally:
                client.close()


class TestMicrogridIntegration:
    """MicrogridSimulator + SimulationServer 整合測試"""

    @pytest.mark.asyncio
    async def test_microgrid_power_balance_via_modbus(self, codec):
        """透過 Modbus 驗證功率平衡"""
        mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

        meter = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=100.0,
            load_noise=0.0,
        )
        solar = SolarSimulator(power_noise=0.0, efficiency=1.0)
        solar.set_target_power(60.0)

        mg.set_meter(meter)
        mg.add_load(load)
        mg.add_solar(solar)

        server = SimulationServer(ServerConfig(port=5034, tick_interval=0.1))
        server.set_microgrid(mg)

        async with server:
            await asyncio.sleep(0.5)

            client = AsyncModbusTcpClient("127.0.0.1", port=5034)
            await client.connect()
            try:
                # 讀取電表 active_power (address=12, Float32, device_id=1)
                # voltage_a(0-1) + voltage_b(2-3) + voltage_c(4-5) + current_a(6-7) +
                # current_b(8-9) + current_c(10-11) + active_power(12-13)
                result = await client.read_holding_registers(12, count=2, device_id=1)
                assert not result.isError()
                meter_p = codec.decode(Float32(), list(result.registers))
                # 負載 100 - 太陽能 60 = 電網 40 kW
                assert abs(meter_p - 40.0) < 5.0
            finally:
                client.close()

    @pytest.mark.asyncio
    async def test_pcs_setpoint_affects_meter(self, codec):
        """寫入 PCS setpoint → 確認 meter 讀值變化"""
        mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

        meter = PowerMeterSimulator(voltage_noise=0.0, frequency_noise=0.0)
        load = LoadSimulator(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            base_load=100.0,
            load_noise=0.0,
        )
        pcs = PCSSimulator(p_ramp_rate=10000.0, tick_interval=0.1)

        mg.set_meter(meter)
        mg.add_load(load)
        mg.add_pcs(pcs)

        server = SimulationServer(ServerConfig(port=5035, tick_interval=0.1))
        server.set_microgrid(mg)

        async with server:
            await asyncio.sleep(0.3)

            client = AsyncModbusTcpClient("127.0.0.1", port=5035)
            await client.connect()
            try:
                # 啟動 PCS
                await client.write_register(14, 1, device_id=10)
                await asyncio.sleep(0.15)

                # 設定 PCS 放電 50 kW
                regs = codec.encode(Float32(), 50.0)
                await client.write_registers(0, regs, device_id=10)

                # 等待 ramp + tick
                await asyncio.sleep(0.5)

                # 讀取電表 → 負載 100 - PCS 50 = 電網 50 kW
                result = await client.read_holding_registers(12, count=2, device_id=1)
                assert not result.isError()
                meter_p = codec.decode(Float32(), list(result.registers))
                assert abs(meter_p - 50.0) < 5.0
            finally:
                client.close()
