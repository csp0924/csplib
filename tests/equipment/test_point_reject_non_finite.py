# =============== ReadPoint reject_non_finite Tests (v0.8.0 WI-V080-001) ===============
#
# 驗證 ReadPoint.reject_non_finite 旗標的行為：
#   - 預設 False：非有限值（NaN / ±Inf）照舊寫入 latest_values
#   - True：非有限值被 reject，保留上次值，不發 EVENT_VALUE_CHANGE
#   - True + 首輪無歷史：保留原始非有限值（implementer 的「首輪保留原值」決策）
#   - effective_values（用於下游告警評估、EVENT_READ_COMPLETE）優先取舊 latest
#
# 設計：直接測試 AsyncModbusDevice 的 private helper（_process_values /
# _resolve_effective_values / _should_reject_non_finite），避免建構完整
# Modbus stack 的 noise。

from __future__ import annotations

import math
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.core import ReadPoint
from csp_lib.equipment.device.base import AsyncModbusDevice
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.equipment.device.events import EVENT_VALUE_CHANGE
from csp_lib.modbus import Float32

# =============== Fixtures ===============


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    return client


def _make_device(points: list[ReadPoint], client: AsyncMock) -> AsyncModbusDevice:
    config = DeviceConfig(
        device_id="test_reject_nan",
        unit_id=1,
        address_offset=0,
        read_interval=0.1,
    )
    return AsyncModbusDevice(config=config, client=client, always_points=points)


# =============== 預設行為 (reject_non_finite=False) ===============


class TestDefaultNonFiniteAccepted:
    """ReadPoint 預設 reject_non_finite=False，維持 v0.7.x 行為"""

    async def test_nan_written_to_latest_when_flag_off(self, mock_client: AsyncMock):
        """預設旗標 False：NaN 會被寫入 latest_values"""
        points = [ReadPoint(name="p", address=0, data_type=Float32())]  # 預設 reject_non_finite=False
        device = _make_device(points, mock_client)

        await device._process_values({"p": float("nan")})

        # NaN 不能直接用 == 比，用 math.isnan
        assert math.isnan(device._latest_values["p"])

    async def test_inf_written_to_latest_when_flag_off(self, mock_client: AsyncMock):
        """預設旗標 False：+Inf 會被寫入 latest_values"""
        points = [ReadPoint(name="p", address=0, data_type=Float32())]
        device = _make_device(points, mock_client)

        await device._process_values({"p": float("inf")})

        assert device._latest_values["p"] == float("inf")


# =============== reject_non_finite=True ===============


class TestRejectNonFiniteEnabled:
    """reject_non_finite=True 時的 reject 行為"""

    async def test_nan_rejected_keeps_last_value(self, mock_client: AsyncMock):
        """reject_non_finite=True：NaN 不覆寫、保留舊值"""
        points = [ReadPoint(name="p", address=0, data_type=Float32(), reject_non_finite=True)]
        device = _make_device(points, mock_client)

        # 先寫入正常值建立歷史
        await device._process_values({"p": 42.0})
        assert device._latest_values["p"] == 42.0

        # 再塞 NaN：應被 reject
        await device._process_values({"p": float("nan")})
        assert device._latest_values["p"] == 42.0  # 未更新

    async def test_inf_positive_rejected(self, mock_client: AsyncMock):
        points = [ReadPoint(name="p", address=0, data_type=Float32(), reject_non_finite=True)]
        device = _make_device(points, mock_client)

        await device._process_values({"p": 10.0})
        await device._process_values({"p": float("inf")})
        assert device._latest_values["p"] == 10.0

    async def test_inf_negative_rejected(self, mock_client: AsyncMock):
        points = [ReadPoint(name="p", address=0, data_type=Float32(), reject_non_finite=True)]
        device = _make_device(points, mock_client)

        await device._process_values({"p": 10.0})
        await device._process_values({"p": float("-inf")})
        assert device._latest_values["p"] == 10.0

    async def test_normal_float_updates_latest(self, mock_client: AsyncMock):
        """reject_non_finite=True：正常 float 仍正常更新"""
        points = [ReadPoint(name="p", address=0, data_type=Float32(), reject_non_finite=True)]
        device = _make_device(points, mock_client)

        await device._process_values({"p": 1.0})
        await device._process_values({"p": 2.5})
        assert device._latest_values["p"] == 2.5


# =============== 首輪無歷史 ===============


class TestFirstRoundNoHistory:
    """reject_non_finite=True + 首輪無歷史 latest_values 時的行為

    implementer 決策：首輪無歷史值不寫入 latest（因為 _process_values 檢查到
    reject 命中就 continue 跳過更新），且 effective_values 由於 name 不在
    _latest_values，會保留原始非有限值（供 READ_COMPLETE payload 呈現）。
    """

    async def test_first_read_nan_not_written_to_latest(self, mock_client: AsyncMock):
        """首輪讀到 NaN 時 latest_values 不會新增該 key（保留空）"""
        points = [ReadPoint(name="p", address=0, data_type=Float32(), reject_non_finite=True)]
        device = _make_device(points, mock_client)

        await device._process_values({"p": float("nan")})
        # latest 未被寫入 — 下游查詢會回 None
        assert "p" not in device._latest_values

    async def test_effective_values_keeps_raw_when_no_history(self, mock_client: AsyncMock):
        """_resolve_effective_values 首輪無歷史時保留原始非有限值"""
        points = [ReadPoint(name="p", address=0, data_type=Float32(), reject_non_finite=True)]
        device = _make_device(points, mock_client)

        raw = {"p": float("nan")}
        effective = device._resolve_effective_values(raw)
        # _latest_values 中無 "p"，故保留原始 NaN 值
        assert math.isnan(effective["p"])


# =============== effective_values 用 last ===============


class TestEffectiveValues:
    """_resolve_effective_values 將 reject 命中的值替換為舊 latest"""

    async def test_effective_replaces_non_finite_with_last_value(self, mock_client: AsyncMock):
        points = [ReadPoint(name="p", address=0, data_type=Float32(), reject_non_finite=True)]
        device = _make_device(points, mock_client)

        # 建立歷史
        await device._process_values({"p": 100.0})

        # 本輪讀到 NaN
        raw = {"p": float("nan")}
        effective = device._resolve_effective_values(raw)
        assert effective["p"] == 100.0  # 取舊 latest

    async def test_effective_passes_normal_values_through(self, mock_client: AsyncMock):
        """未命中 reject 的點位原值傳遞"""
        points = [
            ReadPoint(name="p", address=0, data_type=Float32(), reject_non_finite=True),
            ReadPoint(name="q", address=2, data_type=Float32()),  # 預設 False
        ]
        device = _make_device(points, mock_client)
        await device._process_values({"p": 50.0, "q": 10.0})

        raw = {"p": float("nan"), "q": 20.0}
        effective = device._resolve_effective_values(raw)
        assert effective["p"] == 50.0  # 取 last
        assert effective["q"] == 20.0  # 照原值


# =============== EVENT_VALUE_CHANGE 不發 ===============


class TestValueChangeEventNotEmitted:
    """reject_non_finite 命中時不應發送 EVENT_VALUE_CHANGE

    使用 monkey-patch 替換 emitter.emit 來捕捉呼叫（避免啟動完整 emitter worker
    的複雜度 — emitter.start 需要 running event loop 下的 worker task）。
    """

    async def test_no_value_change_event_on_rejected_nan(self, mock_client: AsyncMock, monkeypatch: pytest.MonkeyPatch):
        points = [ReadPoint(name="p", address=0, data_type=Float32(), reject_non_finite=True)]
        device = _make_device(points, mock_client)
        await device._process_values({"p": 10.0})  # 建立歷史

        # Patch emit 來捕捉事件呼叫
        emit_calls: list[tuple[str, object]] = []
        original_emit = device._emitter.emit

        def spy_emit(event: str, payload=None) -> None:
            emit_calls.append((event, payload))
            return original_emit(event, payload)

        monkeypatch.setattr(device._emitter, "emit", spy_emit)

        # 讀到 NaN 應被 reject，不該發 value_change
        await device._process_values({"p": float("nan")})

        value_change_calls = [c for c in emit_calls if c[0] == EVENT_VALUE_CHANGE]
        assert value_change_calls == [], "reject 命中時不應觸發 EVENT_VALUE_CHANGE"

    async def test_value_change_emitted_for_normal_updates(
        self, mock_client: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ):
        """正常更新仍發送 value_change，驗證 reject 旗標不會誤擋其他正常值"""
        points = [ReadPoint(name="p", address=0, data_type=Float32(), reject_non_finite=True)]
        device = _make_device(points, mock_client)
        await device._process_values({"p": 10.0})  # 建立歷史（此時尚未 patch）

        emit_calls: list[tuple[str, object]] = []
        original_emit = device._emitter.emit

        def spy_emit(event: str, payload=None) -> None:
            emit_calls.append((event, payload))
            return original_emit(event, payload)

        monkeypatch.setattr(device._emitter, "emit", spy_emit)

        # 變更為正常值 — 應呼叫 emit(EVENT_VALUE_CHANGE, ...)
        await device._process_values({"p": 20.0})

        value_change_calls = [c for c in emit_calls if c[0] == EVENT_VALUE_CHANGE]
        assert len(value_change_calls) == 1, (
            f"正常更新應呼叫 emit(EVENT_VALUE_CHANGE) 1 次，實際 {len(value_change_calls)}"
        )


# =============== 混合旗標點位 ===============


class TestMixedPointFlags:
    """同設備多點位混用 reject_non_finite 旗標"""

    async def test_only_flagged_points_reject_non_finite(self, mock_client: AsyncMock):
        """p 設 reject=True，q 預設 False — 只有 p 被 reject"""
        points = [
            ReadPoint(name="p", address=0, data_type=Float32(), reject_non_finite=True),
            ReadPoint(name="q", address=2, data_type=Float32()),
        ]
        device = _make_device(points, mock_client)

        # 建立歷史
        await device._process_values({"p": 100.0, "q": 200.0})

        # 本輪兩個都是 NaN
        await device._process_values({"p": float("nan"), "q": float("nan")})

        # p 被 reject，保留 100.0
        assert device._latest_values["p"] == 100.0
        # q 未開旗標，照原行為寫入 NaN
        assert math.isnan(device._latest_values["q"])
