# =============== ParamResolver Tests (v0.8.2) ===============
#
# 測試 ParamResolver 的解析規則：
#   - params + param_keys 同步 None 驗證
#   - params 優先 → fallback config 的讀值路徑
#   - scale 套用行為
#   - resolve_optional 針對 runtime-only 旗標
#   - with_config 切換 config

from __future__ import annotations

from dataclasses import dataclass

import pytest

from csp_lib.controller.strategies._param_resolver import ParamResolver
from csp_lib.core.runtime_params import RuntimeParameters


@dataclass(frozen=True, slots=True)
class _DummyCfg:
    """供測試使用的 frozen config。"""

    droop: float = 0.05
    f_base: float = 60.0
    deadband: float = 0.01


class TestParamResolverInit:
    """ctor 驗證：params 與 param_keys 必須同步 None/非 None。"""

    def test_both_none_is_valid(self):
        """兩者皆 None → 純 config 模式，has_runtime=False。"""
        cfg = _DummyCfg()
        resolver = ParamResolver(params=None, param_keys=None, config=cfg)
        assert resolver.has_runtime is False

    def test_both_provided_is_valid(self):
        """兩者皆提供 → runtime 模式，has_runtime=True。"""
        cfg = _DummyCfg()
        params = RuntimeParameters(droop_pct=5.0)
        resolver = ParamResolver(
            params=params,
            param_keys={"droop": "droop_pct"},
            config=cfg,
        )
        assert resolver.has_runtime is True

    def test_params_none_but_param_keys_given_raises(self):
        """params=None 但 param_keys 非 None → ValueError。"""
        cfg = _DummyCfg()
        with pytest.raises(ValueError, match="params and param_keys"):
            ParamResolver(params=None, param_keys={"droop": "droop_pct"}, config=cfg)

    def test_param_keys_none_but_params_given_raises(self):
        """params 非 None 但 param_keys=None → ValueError。"""
        cfg = _DummyCfg()
        params = RuntimeParameters()
        with pytest.raises(ValueError, match="params and param_keys"):
            ParamResolver(params=params, param_keys=None, config=cfg)


class TestResolveFallbackPath:
    """resolve 回退路徑：params 無值或 field 不在 param_keys 則讀 config。"""

    def test_resolve_pure_config_mode(self):
        """無 params → 直接讀 config.droop。"""
        cfg = _DummyCfg(droop=0.03)
        resolver = ParamResolver(params=None, param_keys=None, config=cfg)
        assert resolver.resolve("droop") == 0.03
        assert resolver.resolve("f_base") == 60.0

    def test_resolve_field_not_in_param_keys_fallback(self):
        """field 不在 param_keys → 讀 config（即使 params 有同名 key）。"""
        cfg = _DummyCfg(deadband=0.02)
        params = RuntimeParameters(droop_pct=5.0, deadband=999.0)
        # param_keys 只映射 droop，不映射 deadband
        resolver = ParamResolver(
            params=params,
            param_keys={"droop": "droop_pct"},
            config=cfg,
        )
        # deadband 不在 param_keys，fallback 到 config.deadband (0.02)
        assert resolver.resolve("deadband") == 0.02

    def test_resolve_param_value_none_fallback(self):
        """params.get 回 None → fallback 到 config。"""
        cfg = _DummyCfg(droop=0.07)
        params = RuntimeParameters()  # 沒設 droop_pct → get 回 None
        resolver = ParamResolver(
            params=params,
            param_keys={"droop": "droop_pct"},
            config=cfg,
        )
        assert resolver.resolve("droop") == 0.07


class TestResolveRuntimePath:
    """resolve 動態路徑：params 有值則優先回傳。"""

    def test_resolve_runtime_value_overrides_config(self):
        """param_keys 對應的 params key 有值 → 用 params 的值。"""
        cfg = _DummyCfg(droop=0.05)
        params = RuntimeParameters(droop_pct=4.0)
        resolver = ParamResolver(
            params=params,
            param_keys={"droop": "droop_pct"},
            config=cfg,
        )
        assert resolver.resolve("droop") == 4.0

    def test_resolve_scale_applied_to_runtime_value(self):
        """scale 套用於 params value（例如百分比 → 小數）。"""
        cfg = _DummyCfg(droop=0.05)
        params = RuntimeParameters(droop_pct=4.0)
        resolver = ParamResolver(
            params=params,
            param_keys={"droop": "droop_pct"},
            config=cfg,
            scale={"droop": 0.01},
        )
        # 4.0 * 0.01 = 0.04
        assert resolver.resolve("droop") == pytest.approx(0.04)

    def test_resolve_scale_applied_to_config_fallback(self):
        """scale 也套用於 config fallback 值。"""
        cfg = _DummyCfg(droop=5.0)  # config 值是百分比形式
        params = RuntimeParameters()  # 未設 → fallback config
        resolver = ParamResolver(
            params=params,
            param_keys={"droop": "droop_pct"},
            config=cfg,
            scale={"droop": 0.01},
        )
        # fallback 到 config.droop=5.0，套 scale → 0.05
        assert resolver.resolve("droop") == pytest.approx(0.05)


class TestResolveOptional:
    """resolve_optional：runtime-only 旗標解析。"""

    def test_resolve_optional_returns_default_when_params_none(self):
        """params=None → 回 default。"""
        cfg = _DummyCfg()
        resolver = ParamResolver(params=None, param_keys=None, config=cfg)
        assert resolver.resolve_optional("any_key", default=True) is True
        assert resolver.resolve_optional("any_key", default=42) == 42

    def test_resolve_optional_returns_default_when_key_is_none(self):
        """key=None → 回 default（即使 params 存在）。"""
        cfg = _DummyCfg()
        params = RuntimeParameters(foo=10)
        resolver = ParamResolver(
            params=params,
            param_keys={"droop": "droop_pct"},
            config=cfg,
        )
        assert resolver.resolve_optional(None, default="fallback") == "fallback"

    def test_resolve_optional_returns_params_value(self):
        """params 有 key → 回實際值。"""
        cfg = _DummyCfg()
        params = RuntimeParameters(enabled=False, schedule=123.0)
        resolver = ParamResolver(
            params=params,
            param_keys={"droop": "droop_pct"},
            config=cfg,
        )
        assert resolver.resolve_optional("enabled", default=True) is False
        assert resolver.resolve_optional("schedule", default=0.0) == 123.0

    def test_resolve_optional_missing_key_returns_default(self):
        """params 沒這個 key → 回 default（不 fallback 到 config）。"""
        cfg = _DummyCfg(droop=0.05)  # 即使 config 有 droop 屬性
        params = RuntimeParameters()
        resolver = ParamResolver(
            params=params,
            param_keys={"droop": "droop_pct"},
            config=cfg,
        )
        # key 不存在於 params → default（不讀 config）
        assert resolver.resolve_optional("nonexistent_key", default="d") == "d"


class TestWithConfig:
    """with_config：保留 params/param_keys/scale，僅替換 config。"""

    def test_with_config_preserves_runtime_binding(self):
        """替換 config 後，runtime 讀值行為仍有效。"""
        cfg1 = _DummyCfg(droop=0.05)
        cfg2 = _DummyCfg(droop=0.10)
        params = RuntimeParameters(droop_pct=3.0)
        resolver = ParamResolver(
            params=params,
            param_keys={"droop": "droop_pct"},
            config=cfg1,
            scale={"droop": 0.01},
        )
        new_resolver = resolver.with_config(cfg2)
        # runtime 仍優先（3.0 * 0.01 = 0.03），不受新 config 影響
        assert new_resolver.resolve("droop") == pytest.approx(0.03)
        # 但移除 params 值後，fallback 應讀到新 config（0.10 * 0.01 = 0.001）
        params.delete("droop_pct")
        assert new_resolver.resolve("droop") == pytest.approx(0.10 * 0.01)

    def test_with_config_fallback_uses_new_config(self):
        """無 runtime 值時 fallback 到新 config。"""
        cfg1 = _DummyCfg(f_base=60.0)
        cfg2 = _DummyCfg(f_base=50.0)
        resolver = ParamResolver(params=None, param_keys=None, config=cfg1)
        new_resolver = resolver.with_config(cfg2)
        assert new_resolver.resolve("f_base") == 50.0
