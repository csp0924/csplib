"""Tests for GatewayRegisterMap — set/get value, scale, overlap detection, thread safety."""

import threading

import pytest

from csp_lib.modbus.types.numeric import Float32, Int16, Int32, UInt16
from csp_lib.modbus_gateway.config import GatewayRegisterDef, GatewayServerConfig, RegisterType
from csp_lib.modbus_gateway.errors import RegisterConflictError
from csp_lib.modbus_gateway.register_map import GatewayRegisterMap

# ===========================================================================
# Helpers
# ===========================================================================


def _server_config(**overrides) -> GatewayServerConfig:
    defaults = {"host": "127.0.0.1", "port": 502, "register_space_size": 1000}
    defaults.update(overrides)
    return GatewayServerConfig(**defaults)


def _reg(name: str, address: int, data_type=None, **kwargs) -> GatewayRegisterDef:
    return GatewayRegisterDef(
        name=name,
        address=address,
        data_type=data_type or UInt16(),
        **kwargs,
    )


# ===========================================================================
# Construction & Basic Access
# ===========================================================================


class TestRegisterMapConstruction:
    def test_empty_register_defs(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [])
        assert rmap.register_defs == {}

    def test_single_register(self):
        cfg = _server_config()
        reg = _reg("power", 0, initial_value=42)
        rmap = GatewayRegisterMap(cfg, [reg])
        assert rmap.get_value("power") == 42

    def test_multiple_registers(self):
        cfg = _server_config()
        regs = [
            _reg("power", 0, initial_value=100),
            _reg("voltage", 10, initial_value=220),
        ]
        rmap = GatewayRegisterMap(cfg, regs)
        assert rmap.get_value("power") == 100
        assert rmap.get_value("voltage") == 220


# ===========================================================================
# set_value / get_value
# ===========================================================================


class TestRegisterMapSetGet:
    def test_set_and_get(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [_reg("power", 0)])
        rmap.set_value("power", 500)
        assert rmap.get_value("power") == 500

    def test_set_negative_int16(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [_reg("power", 0, data_type=Int16())])
        rmap.set_value("power", -100)
        assert rmap.get_value("power") == -100

    def test_set_float32(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [_reg("temp", 0, data_type=Float32())])
        rmap.set_value("temp", 36.5)
        assert rmap.get_value("temp") == pytest.approx(36.5, abs=0.01)

    def test_set_int32(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [_reg("energy", 0, data_type=Int32())])
        rmap.set_value("energy", 100000)
        assert rmap.get_value("energy") == 100000

    def test_get_nonexistent_key_raises(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [])
        with pytest.raises(KeyError):
            rmap.get_value("nonexistent")

    def test_set_nonexistent_key_raises(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [])
        with pytest.raises(KeyError):
            rmap.set_value("nonexistent", 42)


# ===========================================================================
# Scale factor
# ===========================================================================


class TestRegisterMapScale:
    def test_scale_on_write_and_read(self):
        """stored = physical * scale; read = stored / scale."""
        cfg = _server_config()
        # scale=10: writing 50.0 stores 500, reading returns 50.0
        rmap = GatewayRegisterMap(cfg, [_reg("power", 0, scale=10.0)])
        rmap.set_value("power", 50)
        assert rmap.get_value("power") == pytest.approx(50.0)

    def test_scale_preserves_initial_value(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [_reg("power", 0, scale=10.0, initial_value=25)])
        assert rmap.get_value("power") == pytest.approx(25.0)

    def test_scale_factor_one_no_change(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [_reg("power", 0, scale=1.0, initial_value=42)])
        assert rmap.get_value("power") == 42


# ===========================================================================
# get_all_values
# ===========================================================================


class TestRegisterMapGetAll:
    def test_get_all_values(self):
        cfg = _server_config()
        regs = [
            _reg("a", 0, initial_value=10),
            _reg("b", 10, initial_value=20),
        ]
        rmap = GatewayRegisterMap(cfg, regs)
        all_vals = rmap.get_all_values()
        assert all_vals == {"a": 10, "b": 20}


# ===========================================================================
# Overlap detection
# ===========================================================================


class TestRegisterMapOverlap:
    def test_same_address_same_type_conflict(self):
        cfg = _server_config()
        regs = [
            _reg("a", 0),
            _reg("b", 0),
        ]
        with pytest.raises(RegisterConflictError):
            GatewayRegisterMap(cfg, regs)

    def test_overlapping_multi_register(self):
        """Int32 occupies 2 registers; placing another at address 1 should conflict."""
        cfg = _server_config()
        regs = [
            _reg("wide", 0, data_type=Int32()),  # occupies 0, 1
            _reg("narrow", 1),  # occupies 1 -> overlap
        ]
        with pytest.raises(RegisterConflictError):
            GatewayRegisterMap(cfg, regs)

    def test_adjacent_no_conflict(self):
        """Adjacent registers should not conflict."""
        cfg = _server_config()
        regs = [
            _reg("a", 0, data_type=Int32()),  # occupies 0, 1
            _reg("b", 2),  # occupies 2 -> no overlap
        ]
        rmap = GatewayRegisterMap(cfg, regs)
        assert "a" in rmap.register_defs
        assert "b" in rmap.register_defs

    def test_different_register_type_no_conflict(self):
        """Same address in different register types (HOLDING vs INPUT) is fine."""
        cfg = _server_config()
        regs = [
            _reg("hr", 0, register_type=RegisterType.HOLDING),
            _reg("ir", 0, register_type=RegisterType.INPUT),
        ]
        rmap = GatewayRegisterMap(cfg, regs)
        assert len(rmap.register_defs) == 2

    def test_duplicate_name_raises(self):
        cfg = _server_config()
        regs = [
            _reg("power", 0),
            _reg("power", 10),  # duplicate name
        ]
        with pytest.raises(ValueError, match="Duplicate register name"):
            GatewayRegisterMap(cfg, regs)

    def test_address_exceeds_space_size(self):
        cfg = _server_config(register_space_size=100)
        regs = [_reg("too_far", 100)]  # end = 100, space = 100 -> exceeds
        with pytest.raises(ValueError, match="exceeds space size"):
            GatewayRegisterMap(cfg, regs)


# ===========================================================================
# Raw register access
# ===========================================================================


class TestRegisterMapRawAccess:
    def test_get_hr_raw(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [_reg("power", 0, initial_value=42)])
        raw = rmap.get_hr_raw(0, 1)
        assert len(raw) == 1
        assert raw[0] == 42  # UInt16, scale=1, value=42 -> raw=42

    def test_set_hr_raw(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [_reg("power", 0)])
        rmap.set_hr_raw(0, [99])
        raw = rmap.get_hr_raw(0, 1)
        assert raw[0] == 99

    def test_get_ir_raw(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [_reg("ir_val", 0, register_type=RegisterType.INPUT, initial_value=77)])
        raw = rmap.get_ir_raw(0, 1)
        assert raw[0] == 77


# ===========================================================================
# find_affected_registers
# ===========================================================================


class TestRegisterMapFindAffected:
    def test_single_affected(self):
        cfg = _server_config()
        regs = [_reg("a", 0), _reg("b", 10)]
        rmap = GatewayRegisterMap(cfg, regs)
        affected = rmap.find_affected_registers(0, 1, RegisterType.HOLDING)
        assert len(affected) == 1
        assert affected[0].name == "a"

    def test_multi_register_affected(self):
        cfg = _server_config()
        regs = [_reg("wide", 0, data_type=Int32()), _reg("narrow", 5)]
        rmap = GatewayRegisterMap(cfg, regs)
        # Writing addresses 0-1 affects "wide" (Int32 occupies 0, 1)
        affected = rmap.find_affected_registers(0, 2, RegisterType.HOLDING)
        names = [r.name for r in affected]
        assert "wide" in names

    def test_no_affected(self):
        cfg = _server_config()
        regs = [_reg("a", 0)]
        rmap = GatewayRegisterMap(cfg, regs)
        affected = rmap.find_affected_registers(100, 1, RegisterType.HOLDING)
        assert affected == []

    def test_wrong_register_type_not_affected(self):
        cfg = _server_config()
        regs = [_reg("hr", 0, register_type=RegisterType.HOLDING)]
        rmap = GatewayRegisterMap(cfg, regs)
        affected = rmap.find_affected_registers(0, 1, RegisterType.INPUT)
        assert affected == []


# ===========================================================================
# get_register_def
# ===========================================================================


class TestRegisterMapGetDef:
    def test_get_existing(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [_reg("power", 0)])
        d = rmap.get_register_def("power")
        assert d.name == "power"

    def test_get_nonexistent_raises(self):
        cfg = _server_config()
        rmap = GatewayRegisterMap(cfg, [])
        with pytest.raises(KeyError):
            rmap.get_register_def("none")


# ===========================================================================
# Thread safety (structural)
# ===========================================================================


class TestRegisterMapThreadSafety:
    def test_concurrent_set_get(self):
        cfg = _server_config()
        regs = [_reg(f"r{i}", i * 10) for i in range(10)]
        rmap = GatewayRegisterMap(cfg, regs)
        errors = []

        def writer(name, value):
            try:
                for _ in range(200):
                    rmap.set_value(name, value)
            except Exception as e:
                errors.append(e)

        def reader(name):
            try:
                for _ in range(200):
                    rmap.get_value(name)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            threads.append(threading.Thread(target=writer, args=(f"r{i}", i * 100)))
            threads.append(threading.Thread(target=reader, args=(f"r{i}",)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
