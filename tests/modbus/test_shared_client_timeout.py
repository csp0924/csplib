"""Per-call timeout plumbing for SharedPymodbusTcpClient / PymodbusRtuClient.

驗證 read/write 方法可接受 timeout= kw, 並真正下沉到底層 queue.submit。
這是 additive change — 不傳 timeout 時行為與既往一致 (沿用 default_timeout)。
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.modbus.clients.client import (
    PymodbusRtuClient,
    SharedPymodbusTcpClient,
    _rtu_instances,
    _tcp_instances,
)
from csp_lib.modbus.clients.queue import ModbusRequestQueue, RequestQueueConfig
from csp_lib.modbus.config import ModbusRtuConfig, ModbusTcpConfig

_QUEUE_CONFIG = RequestQueueConfig(default_timeout=30.0, circuit_breaker_threshold=100)
_MOCK_METHODS = (
    "read_holding_registers",
    "read_input_registers",
    "read_coils",
    "read_discrete_inputs",
    "write_register",
    "write_registers",
    "write_coil",
    "write_coils",
)


def _make_slow_mock_pymodbus(slow_seconds: float) -> AsyncMock:
    """建立 mock pymodbus client, 所有 read/write 都會 sleep slow_seconds 再回應。"""

    async def slow_response(*args, **kwargs) -> MagicMock:
        await asyncio.sleep(slow_seconds)
        response = MagicMock()
        response.isError.return_value = False
        response.registers = [1, 2, 3]
        response.bits = [True, True, True]
        return response

    mock_pymodbus = AsyncMock()
    mock_pymodbus.connected = True
    for method in _MOCK_METHODS:
        setattr(mock_pymodbus, method, AsyncMock(side_effect=slow_response))
    return mock_pymodbus


async def _setup_shared_tcp(slow_seconds: float) -> tuple[SharedPymodbusTcpClient, AsyncMock]:
    """建立共用 TCP client + 注入 slow underlying client (sleep slow_seconds 才回應)。"""
    config = ModbusTcpConfig(host="127.0.0.1", port=15020)
    client = SharedPymodbusTcpClient(config, queue_config=_QUEUE_CONFIG)
    mock_pymodbus = _make_slow_mock_pymodbus(slow_seconds)
    queue = ModbusRequestQueue(_QUEUE_CONFIG)
    _tcp_instances[client._endpoint] = (mock_pymodbus, queue, 1)
    client._resources_acquired = True
    await queue.start()
    return client, mock_pymodbus


async def _teardown_shared_tcp(client: SharedPymodbusTcpClient) -> None:
    endpoint = client._endpoint
    if endpoint in _tcp_instances:
        _, queue, _ = _tcp_instances[endpoint]
        await queue.stop()
        del _tcp_instances[endpoint]


async def _setup_rtu(slow_seconds: float) -> tuple[PymodbusRtuClient, AsyncMock]:
    config = ModbusRtuConfig(port="COM-FAKE-99")
    client = PymodbusRtuClient(config, queue_config=_QUEUE_CONFIG)
    mock_pymodbus = _make_slow_mock_pymodbus(slow_seconds)
    queue = ModbusRequestQueue(_QUEUE_CONFIG)
    _rtu_instances[client._port] = (mock_pymodbus, queue, 1)
    client._resources_acquired = True
    await queue.start()
    return client, mock_pymodbus


async def _teardown_rtu(client: PymodbusRtuClient) -> None:
    port = client._port
    if port in _rtu_instances:
        _, queue, _ = _rtu_instances[port]
        await queue.stop()
        del _rtu_instances[port]


# ============================================================================
# SharedPymodbusTcpClient — per-call timeout
# ============================================================================


class TestSharedTcpPerCallTimeout:
    """global default_timeout=30s, 但 per-call 傳 0.2s 應在 ~0.2s 內 TimeoutError。"""

    async def test_read_holding_registers_per_call_timeout_honored(self):
        client, _ = await _setup_shared_tcp(slow_seconds=2.0)
        try:
            t0 = time.monotonic()
            with pytest.raises(asyncio.TimeoutError):
                await client.read_holding_registers(0, 3, unit_id=1, timeout=0.2)
            elapsed = time.monotonic() - t0
            # 必須遠小於 default_timeout=30s; 0.2s timeout 應在 ~0.2~0.5s 之間返回
            assert elapsed < 1.0, f"timeout did not propagate, elapsed={elapsed:.2f}s"
        finally:
            await _teardown_shared_tcp(client)

    async def test_read_input_registers_per_call_timeout_honored(self):
        client, _ = await _setup_shared_tcp(slow_seconds=2.0)
        try:
            t0 = time.monotonic()
            with pytest.raises(asyncio.TimeoutError):
                await client.read_input_registers(0, 3, unit_id=1, timeout=0.2)
            assert time.monotonic() - t0 < 1.0
        finally:
            await _teardown_shared_tcp(client)

    async def test_read_coils_per_call_timeout_honored(self):
        client, _ = await _setup_shared_tcp(slow_seconds=2.0)
        try:
            t0 = time.monotonic()
            with pytest.raises(asyncio.TimeoutError):
                await client.read_coils(0, 3, unit_id=1, timeout=0.2)
            assert time.monotonic() - t0 < 1.0
        finally:
            await _teardown_shared_tcp(client)

    async def test_read_discrete_inputs_per_call_timeout_honored(self):
        client, _ = await _setup_shared_tcp(slow_seconds=2.0)
        try:
            t0 = time.monotonic()
            with pytest.raises(asyncio.TimeoutError):
                await client.read_discrete_inputs(0, 3, unit_id=1, timeout=0.2)
            assert time.monotonic() - t0 < 1.0
        finally:
            await _teardown_shared_tcp(client)

    async def test_write_single_register_per_call_timeout_honored(self):
        client, _ = await _setup_shared_tcp(slow_seconds=2.0)
        try:
            t0 = time.monotonic()
            with pytest.raises(asyncio.TimeoutError):
                await client.write_single_register(0, 42, unit_id=1, timeout=0.2)
            assert time.monotonic() - t0 < 1.0
        finally:
            await _teardown_shared_tcp(client)

    async def test_write_multiple_registers_per_call_timeout_honored(self):
        client, _ = await _setup_shared_tcp(slow_seconds=2.0)
        try:
            t0 = time.monotonic()
            with pytest.raises(asyncio.TimeoutError):
                await client.write_multiple_registers(0, [1, 2], unit_id=1, timeout=0.2)
            assert time.monotonic() - t0 < 1.0
        finally:
            await _teardown_shared_tcp(client)

    async def test_write_single_coil_per_call_timeout_honored(self):
        client, _ = await _setup_shared_tcp(slow_seconds=2.0)
        try:
            t0 = time.monotonic()
            with pytest.raises(asyncio.TimeoutError):
                await client.write_single_coil(0, True, unit_id=1, timeout=0.2)
            assert time.monotonic() - t0 < 1.0
        finally:
            await _teardown_shared_tcp(client)

    async def test_write_multiple_coils_per_call_timeout_honored(self):
        client, _ = await _setup_shared_tcp(slow_seconds=2.0)
        try:
            t0 = time.monotonic()
            with pytest.raises(asyncio.TimeoutError):
                await client.write_multiple_coils(0, [True, False], unit_id=1, timeout=0.2)
            assert time.monotonic() - t0 < 1.0
        finally:
            await _teardown_shared_tcp(client)

    async def test_no_timeout_falls_back_to_default(self):
        """不傳 timeout 時, 應使用 queue 的 default_timeout (此處 30s, 不會在 fast call 中 timeout)"""
        client, _ = await _setup_shared_tcp(slow_seconds=0.05)
        try:
            result = await client.read_holding_registers(0, 3, unit_id=1)
            assert result == [1, 2, 3]
        finally:
            await _teardown_shared_tcp(client)


# ============================================================================
# PymodbusRtuClient — per-call timeout
# ============================================================================


class TestRtuPerCallTimeout:
    async def test_read_holding_registers_per_call_timeout_honored(self):
        client, _ = await _setup_rtu(slow_seconds=2.0)
        try:
            t0 = time.monotonic()
            with pytest.raises(asyncio.TimeoutError):
                await client.read_holding_registers(0, 3, unit_id=1, timeout=0.2)
            assert time.monotonic() - t0 < 1.0
        finally:
            await _teardown_rtu(client)

    async def test_write_single_register_per_call_timeout_honored(self):
        client, _ = await _setup_rtu(slow_seconds=2.0)
        try:
            t0 = time.monotonic()
            with pytest.raises(asyncio.TimeoutError):
                await client.write_single_register(0, 42, unit_id=1, timeout=0.2)
            assert time.monotonic() - t0 < 1.0
        finally:
            await _teardown_rtu(client)

    async def test_no_timeout_falls_back_to_default(self):
        client, _ = await _setup_rtu(slow_seconds=0.05)
        try:
            result = await client.read_holding_registers(0, 3, unit_id=1)
            assert result == [1, 2, 3]
        finally:
            await _teardown_rtu(client)
