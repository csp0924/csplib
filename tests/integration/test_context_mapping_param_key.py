# =============== ContextMapping param_key Tests (v0.8.0 WI-V080-003) ===============
#
# 驗證 ContextMapping 的 param_key 模式：
#   - 從 RuntimeParameters 讀值並映射到 context 欄位
#   - param_key 與 device_id / trait 互斥（三擇一）
#   - runtime_params=None 時 fallback 到 default 並 warning
#   - default 在 key 未設定時生效
#   - transform 在 param_key 模式下照常套用

from __future__ import annotations

import pytest

from csp_lib.core.runtime_params import RuntimeParameters
from csp_lib.integration.context_builder import ContextBuilder
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import ContextMapping

# =============== 正確映射 ===============


class TestContextMappingParamKeyReadValue:
    """param_key 模式正確把 RuntimeParameters 值注入 context"""

    def test_param_key_maps_to_extra_field(self):
        """param_key='k1' + set('k1', 42) → context.extra['x'] == 42"""
        params = RuntimeParameters(k1=42)
        reg = DeviceRegistry()

        mapping = ContextMapping(
            point_name="",  # param_key 模式下不會被使用
            context_field="extra.x",
            param_key="k1",
        )
        builder = ContextBuilder(reg, [mapping], runtime_params=params)
        ctx = builder.build()

        assert ctx.extra["x"] == 42

    def test_param_key_maps_to_top_level_field(self):
        """param_key 也可映射到 context 頂層屬性（如 soc）"""
        params = RuntimeParameters(soc_runtime=80.5)
        reg = DeviceRegistry()

        mapping = ContextMapping(
            point_name="",
            context_field="soc",
            param_key="soc_runtime",
        )
        builder = ContextBuilder(reg, [mapping], runtime_params=params)
        ctx = builder.build()

        assert ctx.soc == 80.5

    def test_param_key_updated_value_reflected_on_next_build(self):
        """RuntimeParameters.set 後，下次 build 應看到新值"""
        params = RuntimeParameters(k1=10)
        reg = DeviceRegistry()

        mapping = ContextMapping(point_name="", context_field="extra.x", param_key="k1")
        builder = ContextBuilder(reg, [mapping], runtime_params=params)

        ctx1 = builder.build()
        assert ctx1.extra["x"] == 10

        params.set("k1", 99)
        ctx2 = builder.build()
        assert ctx2.extra["x"] == 99


# =============== 三擇一驗證 ===============


class TestContextMappingParamKeyExclusivity:
    """param_key 與 device_id / trait 互斥"""

    def test_param_key_and_device_id_both_raises(self):
        with pytest.raises(ValueError, match="Cannot set more than one of device_id / trait / param_key"):
            ContextMapping(
                point_name="",
                context_field="extra.x",
                param_key="k1",
                device_id="d1",
            )

    def test_param_key_and_trait_both_raises(self):
        with pytest.raises(ValueError, match="Cannot set more than one of device_id / trait / param_key"):
            ContextMapping(
                point_name="",
                context_field="extra.x",
                param_key="k1",
                trait="t1",
            )

    def test_all_three_raises(self):
        with pytest.raises(ValueError, match="Cannot set more than one"):
            ContextMapping(
                point_name="",
                context_field="extra.x",
                param_key="k1",
                device_id="d1",
                trait="t1",
            )


# =============== runtime_params=None 退回 default ===============


class TestContextMappingParamKeyNoRuntimeParams:
    """runtime_params=None 但 mapping 使用 param_key → default + warning"""

    def test_param_key_without_runtime_params_uses_default(self):
        """ContextBuilder 未傳 runtime_params → param_key 模式退回 default"""
        reg = DeviceRegistry()
        mapping = ContextMapping(
            point_name="",
            context_field="extra.x",
            param_key="k1",
            default=-1,
        )
        # 注意：不傳 runtime_params
        builder = ContextBuilder(reg, [mapping])
        ctx = builder.build()

        assert ctx.extra["x"] == -1  # 退回 default

    def test_param_key_without_runtime_params_default_none(self):
        """default 未提供時退回 None"""
        reg = DeviceRegistry()
        mapping = ContextMapping(point_name="", context_field="extra.x", param_key="k1")
        builder = ContextBuilder(reg, [mapping])
        ctx = builder.build()

        assert ctx.extra["x"] is None


# =============== key 未設定時退回 default ===============


class TestContextMappingParamKeyMissingKey:
    """RuntimeParameters 有連線但 key 不存在 → RuntimeParameters.get 回 None → default"""

    def test_missing_key_uses_default(self):
        params = RuntimeParameters(other_key=123)  # 沒有 "k1"
        reg = DeviceRegistry()
        mapping = ContextMapping(
            point_name="",
            context_field="extra.x",
            param_key="k1",
            default=99,
        )
        builder = ContextBuilder(reg, [mapping], runtime_params=params)
        ctx = builder.build()
        assert ctx.extra["x"] == 99

    def test_missing_key_no_default_returns_none(self):
        params = RuntimeParameters(other_key=123)
        reg = DeviceRegistry()
        mapping = ContextMapping(point_name="", context_field="extra.x", param_key="k1")
        builder = ContextBuilder(reg, [mapping], runtime_params=params)
        ctx = builder.build()
        assert ctx.extra["x"] is None


# =============== transform 在 param_key 模式 ===============


class TestContextMappingParamKeyTransform:
    """transform 需要在 param_key 模式下照常運作"""

    def test_transform_applied_to_param_value(self):
        params = RuntimeParameters(pct=50)
        reg = DeviceRegistry()
        mapping = ContextMapping(
            point_name="",
            context_field="extra.ratio",
            param_key="pct",
            transform=lambda v: v / 100.0,
        )
        builder = ContextBuilder(reg, [mapping], runtime_params=params)
        ctx = builder.build()
        assert ctx.extra["ratio"] == pytest.approx(0.5)

    def test_transform_exception_returns_default(self):
        """transform 拋例外 → 回 default，與 device_id 模式一致"""
        params = RuntimeParameters(bad_value="not-a-number")
        reg = DeviceRegistry()
        mapping = ContextMapping(
            point_name="",
            context_field="extra.x",
            param_key="bad_value",
            default=-1,
            transform=lambda v: float(v) + 1,  # float("not-a-number") 會拋 ValueError
        )
        builder = ContextBuilder(reg, [mapping], runtime_params=params)
        ctx = builder.build()
        assert ctx.extra["x"] == -1


# =============== context.params 引用傳遞 ===============


class TestContextParamsReference:
    """runtime_params 也會直接掛到 context.params（獨立於 ContextMapping）"""

    def test_runtime_params_attached_to_context(self):
        params = RuntimeParameters(k1=42)
        reg = DeviceRegistry()
        builder = ContextBuilder(reg, [], runtime_params=params)
        ctx = builder.build()
        # 即使沒有 ContextMapping，runtime_params 仍 attach 到 ctx.params
        assert ctx.params is params
