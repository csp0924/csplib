"""SEC-013a L6 防禦：ContextBuilder 過濾非有限值（NaN / +Inf / -Inf）

設計決策：保持 `Float32/64.decode()` permissive（Modbus 原始層不改），
在 L6 ContextBuilder 過濾非有限浮點值（寫入 None），避免 NaN/Inf 透過
`latest_values` 注入 StrategyContext 後污染保護鏈與策略計算。

修復前行為：build() 直接將 NaN/Inf 寫入 ctx.soc / ctx.extra[...]，
下游 protection rules 會遇到 `soc >= soc_max` 這類比較運算
（NaN 比較永遠 False → 保護被無聲繞過）。

修復後行為：_set_context_field 偵測 float 且非有限 → 寫入 None
（不寫會留 stale value 更危險）。

本檔案的每個測試在未修 source 前皆應 FAIL。
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, PropertyMock

from csp_lib.integration.context_builder import ContextBuilder
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import AggregateFunc, ContextMapping


def _make_device(device_id: str, values: dict | None = None, responsive: bool = True) -> MagicMock:
    """建立帶 latest_values 的 mock 設備（對齊 test_context_builder.py）。"""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).latest_values = PropertyMock(return_value=values or {})
    return dev


class TestContextBuilderNaNInfFiltering:
    """ContextBuilder 對 NaN/Inf 的過濾行為（SEC-013a L6）"""

    # ─── 直接 context 欄位（soc）───

    def test_nan_on_direct_field_becomes_none(self):
        """
        SEC-013a L6: device 回傳 NaN → ctx.soc 應為 None（非 NaN）。

        修復前：ctx.soc = nan（math.isnan 為 True）
        修復後：ctx.soc is None
        """
        reg = DeviceRegistry()
        dev = _make_device("bms1", {"soc": float("nan")})
        reg.register(dev)

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", device_id="bms1")],
        )
        ctx = builder.build()

        # 預期：修復後應過濾為 None
        assert ctx.soc is None, f"NaN 應被過濾為 None，實際得到 {ctx.soc!r}"

    def test_positive_inf_on_direct_field_becomes_none(self):
        """SEC-013a L6: device 回傳 +Inf → ctx.soc 應為 None。"""
        reg = DeviceRegistry()
        dev = _make_device("bms1", {"soc": float("inf")})
        reg.register(dev)

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", device_id="bms1")],
        )
        ctx = builder.build()

        assert ctx.soc is None, f"+Inf 應被過濾為 None，實際得到 {ctx.soc!r}"

    def test_negative_inf_on_direct_field_becomes_none(self):
        """SEC-013a L6: device 回傳 -Inf → ctx.soc 應為 None。"""
        reg = DeviceRegistry()
        dev = _make_device("bms1", {"soc": float("-inf")})
        reg.register(dev)

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", device_id="bms1")],
        )
        ctx = builder.build()

        assert ctx.soc is None, f"-Inf 應被過濾為 None，實際得到 {ctx.soc!r}"

    # ─── extra.* 欄位（meter_power 等）───

    def test_nan_on_extra_field_becomes_none(self):
        """
        SEC-013a L6: device 回傳 NaN → ctx.extra['meter_power'] 應為 None。

        meter_power=NaN 若未過濾，會讓 ReversePowerProtection 誤判 max_discharge=NaN，
        下游比較 p > NaN 永遠 False，保護被無聲繞過。
        """
        reg = DeviceRegistry()
        dev = _make_device("meter1", {"meter_power": float("nan")})
        reg.register(dev)

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="meter_power", context_field="extra.meter_power", device_id="meter1")],
        )
        ctx = builder.build()

        assert ctx.extra["meter_power"] is None, (
            f"extra.meter_power 的 NaN 應被過濾為 None，實際得到 {ctx.extra['meter_power']!r}"
        )

    def test_inf_on_extra_field_becomes_none(self):
        """SEC-013a L6: device 回傳 Inf → ctx.extra[...] 應為 None。"""
        reg = DeviceRegistry()
        dev = _make_device("meter1", {"meter_power": float("inf")})
        reg.register(dev)

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="meter_power", context_field="extra.meter_power", device_id="meter1")],
        )
        ctx = builder.build()

        assert ctx.extra["meter_power"] is None

    # ─── Trait 聚合路徑（NaN 參與 average 會污染結果）───

    def test_nan_in_trait_aggregate_average_becomes_none(self):
        """
        SEC-013a L6: trait 聚合平均值中含 NaN → 聚合結果為 NaN，應被過濾為 None。

        修復前：average([80.0, nan]) = nan，寫入 ctx.soc
        修復後：_set_context_field 偵測 nan → ctx.soc is None
        """
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"soc": 80.0})
        d2 = _make_device("d2", {"soc": float("nan")})
        reg.register(d1, traits=["bms"])
        reg.register(d2, traits=["bms"])

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", trait="bms", aggregate=AggregateFunc.AVERAGE)],
        )
        ctx = builder.build()

        assert ctx.soc is None or (isinstance(ctx.soc, float) and math.isfinite(ctx.soc)), (
            f"聚合結果若為非有限值應被過濾為 None，實際得到 {ctx.soc!r}"
        )
        # 更嚴格：若 aggregate 回傳 NaN，必須被過濾
        if ctx.soc is not None:
            assert math.isfinite(ctx.soc), f"ctx.soc 不應為非有限值，實際得到 {ctx.soc!r}"

    # ─── 非 float 型別不受影響（int / bool / None 保持原狀）───

    def test_int_value_not_affected(self):
        """SEC-013a L6: int 值應原樣寫入（NaN/Inf 過濾只針對 float 非有限值）。"""
        reg = DeviceRegistry()
        dev = _make_device("d1", {"status": 1})
        reg.register(dev)

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="status", context_field="extra.status", device_id="d1")],
        )
        ctx = builder.build()

        assert ctx.extra["status"] == 1

    def test_finite_float_not_affected(self):
        """SEC-013a L6: 正常 float 值應原樣寫入。"""
        reg = DeviceRegistry()
        dev = _make_device("d1", {"soc": 85.5})
        reg.register(dev)

        builder = ContextBuilder(
            reg,
            [ContextMapping(point_name="soc", context_field="soc", device_id="d1")],
        )
        ctx = builder.build()

        assert ctx.soc == 85.5
