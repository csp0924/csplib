# =============== RegistryAggregatingSource Tests (v0.8.2) ===============
#
# 驗證 RegistryAggregatingSource 作為 DataSyncSource：
#   - 各 AggregateFunc (AVERAGE / SUM / MIN / MAX)
#   - 自訂 Callable
#   - 全設備離線 + offline_fallback
#   - 無 point 跳過 / 部分 responsive / 全缺 fallback
#   - writable_param 回寫 RuntimeParameters
#   - update_callback 例外處理（PermissionError / KeyError）
#   - Callable aggregate 拋例外
#   - start / stop lifecycle

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, PropertyMock

from csp_lib.core.runtime_params import RuntimeParameters
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.modbus_gateway.registry_sync_source import (
    AggregateFunc,
    RegisterAggregateMapping,
    RegistryAggregatingSource,
)

# =============== Helpers ===============


def _make_mock_device(
    device_id: str,
    latest_values: dict[str, Any],
    is_responsive: bool = True,
) -> MagicMock:
    """建立 AsyncModbusDevice 的 mock，只關心 RegistryAggregatingSource 讀取的欄位。"""
    device = MagicMock()
    type(device).device_id = PropertyMock(return_value=device_id)
    type(device).is_responsive = PropertyMock(return_value=is_responsive)
    type(device).latest_values = PropertyMock(return_value=latest_values)
    type(device).capabilities = PropertyMock(return_value=[])
    return device


def _make_registry_with_devices(
    devices: list[tuple[MagicMock, list[str]]],
) -> DeviceRegistry:
    """建立已註冊設備的 registry。每個 tuple 為 (device, traits)。"""
    registry = DeviceRegistry()
    for device, traits in devices:
        registry.register(device, traits=traits)
    return registry


class _Recorder:
    """記錄 update_callback 呼叫的工具。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def __call__(self, register: str, value: Any) -> None:
        self.calls.append((register, value))


# =============== Aggregate Function Tests ===============


class TestAggregateFunctions:
    """各 AggregateFunc 行為驗證。"""

    async def test_average_aggregate(self):
        """AVERAGE：兩台 responsive 設備的 soc 取平均。"""
        d1 = _make_mock_device("pcs1", {"soc": 40.0})
        d2 = _make_mock_device("pcs2", {"soc": 60.0})
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["pcs"])])

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [RegisterAggregateMapping(register="avg_soc", trait="pcs", point="soc")],
            interval=10.0,
        )
        # 直接跑一次 _process_all_mappings，不進 poll loop
        source._update_cb = recorder
        await source._process_all_mappings()

        assert recorder.calls == [("avg_soc", 50.0)]

    async def test_sum_aggregate(self):
        """SUM：三台設備的功率加總。"""
        d1 = _make_mock_device("pcs1", {"p_out": 100.0})
        d2 = _make_mock_device("pcs2", {"p_out": 200.0})
        d3 = _make_mock_device("pcs3", {"p_out": 150.0})
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["pcs"]), (d3, ["pcs"])])

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [RegisterAggregateMapping(register="total_p", trait="pcs", point="p_out", aggregate=AggregateFunc.SUM)],
        )
        source._update_cb = recorder
        await source._process_all_mappings()

        assert recorder.calls == [("total_p", 450.0)]

    async def test_min_aggregate(self):
        """MIN：取最小值。"""
        d1 = _make_mock_device("pcs1", {"soc": 40.0})
        d2 = _make_mock_device("pcs2", {"soc": 60.0})
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["pcs"])])

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [RegisterAggregateMapping(register="min_soc", trait="pcs", point="soc", aggregate=AggregateFunc.MIN)],
        )
        source._update_cb = recorder
        await source._process_all_mappings()

        assert recorder.calls == [("min_soc", 40.0)]

    async def test_max_aggregate(self):
        """MAX：取最大值。"""
        d1 = _make_mock_device("pcs1", {"soc": 40.0})
        d2 = _make_mock_device("pcs2", {"soc": 60.0})
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["pcs"])])

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [RegisterAggregateMapping(register="max_soc", trait="pcs", point="soc", aggregate=AggregateFunc.MAX)],
        )
        source._update_cb = recorder
        await source._process_all_mappings()

        assert recorder.calls == [("max_soc", 60.0)]

    async def test_custom_callable_aggregate(self):
        """自訂 Callable：取第一個（或任意自訂邏輯）。"""
        d1 = _make_mock_device("pcs1", {"soc": 40.0})
        d2 = _make_mock_device("pcs2", {"soc": 60.0})
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["pcs"])])

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [
                RegisterAggregateMapping(
                    register="first_soc",
                    trait="pcs",
                    point="soc",
                    aggregate=lambda xs: xs[0],
                )
            ],
        )
        source._update_cb = recorder
        await source._process_all_mappings()

        # 設備按 device_id 排序 → pcs1 的 soc=40.0 在前
        assert recorder.calls == [("first_soc", 40.0)]


# =============== Offline / Missing Point 行為 ===============


class TestOfflineFallback:
    """設備離線 / 無 point 時的回退行為。"""

    async def test_all_devices_offline_with_fallback(self):
        """全設備 is_responsive=False + offline_fallback → 寫入 fallback。"""
        d1 = _make_mock_device("pcs1", {"soc": 40.0}, is_responsive=False)
        d2 = _make_mock_device("pcs2", {"soc": 60.0}, is_responsive=False)
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["pcs"])])

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [
                RegisterAggregateMapping(
                    register="avg_soc",
                    trait="pcs",
                    point="soc",
                    offline_fallback=50.0,
                )
            ],
        )
        source._update_cb = recorder
        await source._process_all_mappings()

        assert recorder.calls == [("avg_soc", 50.0)]

    async def test_all_responsive_but_no_point_with_fallback(self):
        """全設備 responsive 但 latest_values 無該 point + fallback → 寫入 fallback。"""
        d1 = _make_mock_device("pcs1", {"other": 10.0})
        d2 = _make_mock_device("pcs2", {"other": 20.0})
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["pcs"])])

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [
                RegisterAggregateMapping(
                    register="avg_soc",
                    trait="pcs",
                    point="soc",
                    offline_fallback=77.0,
                )
            ],
        )
        source._update_cb = recorder
        await source._process_all_mappings()

        assert recorder.calls == [("avg_soc", 77.0)]

    async def test_no_point_no_fallback_skips(self):
        """全設備無 point 且無 fallback → 跳過，不呼叫 update_callback。"""
        d1 = _make_mock_device("pcs1", {"other": 10.0})
        registry = _make_registry_with_devices([(d1, ["pcs"])])

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [RegisterAggregateMapping(register="avg_soc", trait="pcs", point="soc")],
        )
        source._update_cb = recorder
        await source._process_all_mappings()

        assert recorder.calls == []

    async def test_partial_responsive_aggregates_only_available(self):
        """部分 responsive + 部分無 point → 只聚合有值的設備。"""
        d1 = _make_mock_device("pcs1", {"soc": 40.0}, is_responsive=True)
        d2 = _make_mock_device("pcs2", {"soc": 100.0}, is_responsive=False)  # 離線
        d3 = _make_mock_device("pcs3", {"other": 50.0}, is_responsive=True)  # 無 point
        d4 = _make_mock_device("pcs4", {"soc": 80.0}, is_responsive=True)
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["pcs"]), (d3, ["pcs"]), (d4, ["pcs"])])

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [RegisterAggregateMapping(register="avg_soc", trait="pcs", point="soc")],
        )
        source._update_cb = recorder
        await source._process_all_mappings()

        # 只有 pcs1(40) + pcs4(80) 有效 → avg=60
        assert recorder.calls == [("avg_soc", 60.0)]


# =============== writable_param 回寫 ===============


class TestWritableParam:
    """writable_param 回寫 RuntimeParameters。"""

    async def test_writable_param_writes_to_params(self):
        """writable_param + params 有值 → params.get(writable_param) == result。"""
        d1 = _make_mock_device("pcs1", {"soc": 40.0})
        d2 = _make_mock_device("pcs2", {"soc": 60.0})
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["pcs"])])

        params = RuntimeParameters()
        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [
                RegisterAggregateMapping(
                    register="avg_soc",
                    trait="pcs",
                    point="soc",
                    writable_param="runtime_avg_soc",
                )
            ],
            params=params,
        )
        source._update_cb = recorder
        await source._process_all_mappings()

        assert recorder.calls == [("avg_soc", 50.0)]
        assert params.get("runtime_avg_soc") == 50.0

    async def test_writable_param_without_params_does_not_raise(self):
        """writable_param 有設但 params=None → 只寫 register，不拋錯。"""
        d1 = _make_mock_device("pcs1", {"soc": 40.0})
        registry = _make_registry_with_devices([(d1, ["pcs"])])

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [
                RegisterAggregateMapping(
                    register="avg_soc",
                    trait="pcs",
                    point="soc",
                    writable_param="runtime_avg_soc",
                )
            ],
            params=None,
        )
        source._update_cb = recorder
        # 不應拋錯
        await source._process_all_mappings()
        assert recorder.calls == [("avg_soc", 40.0)]


# =============== 錯誤處理 ===============


class TestErrorHandling:
    """update_callback 例外與 Callable aggregate 例外。"""

    async def test_update_callback_permission_error_continues(self):
        """update_callback 拋 PermissionError → warning log，不中斷下一 mapping。"""
        d1 = _make_mock_device("pcs1", {"soc": 40.0})
        d2 = _make_mock_device("bms1", {"temp": 25.0})
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["bms"])])

        calls: list[tuple[str, Any]] = []

        async def cb(register: str, value: Any) -> None:
            if register == "avg_soc":
                raise PermissionError("HOLDING register protected")
            calls.append((register, value))

        source = RegistryAggregatingSource(
            registry,
            [
                RegisterAggregateMapping(register="avg_soc", trait="pcs", point="soc"),
                RegisterAggregateMapping(register="avg_temp", trait="bms", point="temp"),
            ],
        )
        source._update_cb = cb
        # 第一個 mapping 拋 PermissionError，應被吸收；第二個正常執行
        await source._process_all_mappings()
        assert calls == [("avg_temp", 25.0)]

    async def test_update_callback_key_error_continues(self):
        """update_callback 拋 KeyError → warning log，不中斷下一 mapping。"""
        d1 = _make_mock_device("pcs1", {"soc": 40.0})
        d2 = _make_mock_device("bms1", {"temp": 25.0})
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["bms"])])

        calls: list[tuple[str, Any]] = []

        async def cb(register: str, value: Any) -> None:
            if register == "avg_soc":
                raise KeyError(register)
            calls.append((register, value))

        source = RegistryAggregatingSource(
            registry,
            [
                RegisterAggregateMapping(register="avg_soc", trait="pcs", point="soc"),
                RegisterAggregateMapping(register="avg_temp", trait="bms", point="temp"),
            ],
        )
        source._update_cb = cb
        await source._process_all_mappings()
        assert calls == [("avg_temp", 25.0)]

    async def test_callable_aggregate_exception_skips_mapping(self):
        """Callable aggregate 拋例外 → warning log，該 mapping 跳過、繼續下一個。"""
        d1 = _make_mock_device("pcs1", {"soc": 40.0})
        d2 = _make_mock_device("bms1", {"temp": 25.0})
        registry = _make_registry_with_devices([(d1, ["pcs"]), (d2, ["bms"])])

        def broken_agg(xs: list[float]) -> float:
            raise RuntimeError("aggregate failed")

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [
                RegisterAggregateMapping(register="broken", trait="pcs", point="soc", aggregate=broken_agg),
                RegisterAggregateMapping(register="avg_temp", trait="bms", point="temp"),
            ],
        )
        source._update_cb = recorder
        await source._process_all_mappings()
        # 第一個 mapping 被跳過，第二個成功
        assert recorder.calls == [("avg_temp", 25.0)]


# =============== Lifecycle ===============


class TestLifecycle:
    """start / stop 生命週期。"""

    async def test_start_stop_clean_cancel(self):
        """start 啟動 task，stop 取消 task 乾淨結束。"""
        d1 = _make_mock_device("pcs1", {"soc": 50.0})
        registry = _make_registry_with_devices([(d1, ["pcs"])])

        recorder = _Recorder()
        source = RegistryAggregatingSource(
            registry,
            [RegisterAggregateMapping(register="avg_soc", trait="pcs", point="soc")],
            interval=0.05,
        )
        await source.start(recorder)
        # 至少讓一個週期跑完
        await asyncio.sleep(0.15)
        await source.stop()

        # 跑了幾次都好，至少一次
        assert len(recorder.calls) >= 1
        assert all(r == "avg_soc" for r, _ in recorder.calls)
        # task 應已結束
        assert source._task is not None
        assert source._task.done()

    async def test_stop_without_start_is_safe(self):
        """尚未 start 即呼叫 stop → 不拋錯。"""
        registry = DeviceRegistry()
        source = RegistryAggregatingSource(registry, [], interval=1.0)
        await source.stop()  # 應靜默完成
