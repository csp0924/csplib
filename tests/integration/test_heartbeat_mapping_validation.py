# =============== v0.8.1 HeartbeatMapping Validation Tests ===============
#
# 涵蓋 Feature spec AC4（向後相容）：
#   - 舊欄位（mode / constant_value / increment_max / device_id / trait）完全保留
#   - 新欄位（value_generator / target）與舊欄位互斥，混用時 raise ValueError
#   - 舊路徑不應 emit DeprecationWarning（legacy-only 路徑安靜）
#
# 互斥矩陣：
#   value_generator 與 mode / constant_value / increment_max 三欄位互斥
#   target 與 device_id / trait 互斥

from __future__ import annotations

import warnings
from unittest.mock import MagicMock, PropertyMock

import pytest

from csp_lib.integration.heartbeat_generators import (
    ConstantGenerator,
    IncrementGenerator,
    ToggleGenerator,
)
from csp_lib.integration.heartbeat_targets import DeviceHeartbeatTarget
from csp_lib.integration.schema import HeartbeatMapping, HeartbeatMode


def _make_target() -> DeviceHeartbeatTarget:
    """建立一個最小 target，供驗證用（不會真的寫入）"""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value="pcs1")
    return DeviceHeartbeatTarget(dev, point_name="hb")


# ─────────────── value_generator 與舊欄位互斥 ───────────────


class TestValueGeneratorExclusive:
    """AC4：value_generator 與 mode/constant_value/increment_max 互斥"""

    def test_value_generator_with_mode_increment_raises(self):
        """value_generator 已設，且 mode 非預設（INCREMENT）→ raise"""
        with pytest.raises(ValueError, match="value_generator.*mode"):
            HeartbeatMapping(
                point_name="hb",
                device_id="pcs1",
                value_generator=ToggleGenerator(),
                mode=HeartbeatMode.INCREMENT,
            )

    def test_value_generator_with_mode_constant_raises(self):
        """value_generator 已設，且 mode=CONSTANT → raise"""
        with pytest.raises(ValueError, match="value_generator.*mode"):
            HeartbeatMapping(
                point_name="hb",
                device_id="pcs1",
                value_generator=ToggleGenerator(),
                mode=HeartbeatMode.CONSTANT,
            )

    def test_value_generator_with_constant_value_raises(self):
        """value_generator 已設 + constant_value 非預設 1 → raise"""
        with pytest.raises(ValueError, match="constant_value"):
            HeartbeatMapping(
                point_name="hb",
                device_id="pcs1",
                value_generator=ConstantGenerator(value=5),
                constant_value=5,
            )

    def test_value_generator_with_increment_max_raises(self):
        """value_generator 已設 + increment_max 非預設 65535 → raise"""
        with pytest.raises(ValueError, match="increment_max"):
            HeartbeatMapping(
                point_name="hb",
                device_id="pcs1",
                value_generator=IncrementGenerator(max_value=100),
                increment_max=100,
            )

    def test_value_generator_without_target_raises(self):
        """value_generator 必須搭配 target；僅給 value_generator + device_id/trait 會被
        HeartbeatService 的 legacy 路徑忽略 generator，屬於誤用 API → 建構時 raise"""
        with pytest.raises(ValueError, match="value_generator.*target"):
            HeartbeatMapping(
                point_name="hb",
                device_id="pcs1",
                value_generator=ToggleGenerator(),
            )


# ─────────────── target 與 device_id/trait 互斥 ───────────────


class TestTargetExclusive:
    """AC4：target 與 device_id/trait 互斥"""

    def test_target_with_device_id_raises(self):
        with pytest.raises(ValueError, match="target.*device_id"):
            HeartbeatMapping(
                point_name="hb",
                target=_make_target(),
                device_id="pcs1",
            )

    def test_target_with_trait_raises(self):
        with pytest.raises(ValueError, match="target.*device_id"):
            # 實作的 error message 是 "target.*device_id.*trait"（同一條訊息）
            HeartbeatMapping(
                point_name="hb",
                target=_make_target(),
                trait="pcs",
            )

    def test_target_alone_is_ok(self):
        """AC4：只給 target、不給 device_id/trait → 合法"""
        mapping = HeartbeatMapping(
            point_name="hb",
            target=_make_target(),
        )
        assert mapping.target is not None
        assert mapping.device_id is None
        assert mapping.trait is None


# ─────────────── 新 API path 組合 ───────────────


class TestNewApiCombinations:
    """value_generator + target 一起設（純新 API）"""

    def test_both_value_generator_and_target_ok(self):
        """AC4：完整新 API 路徑 — value_generator + target + 預設 mode / 不設 device_id"""
        mapping = HeartbeatMapping(
            point_name="hb",
            value_generator=ToggleGenerator(),
            target=_make_target(),
        )
        assert mapping.value_generator is not None
        assert mapping.target is not None


# ─────────────── 向後相容：舊 API 路徑 ───────────────


class TestLegacyBackwardCompat:
    """AC4：舊 API 路徑完全保留，且不 emit DeprecationWarning"""

    def test_legacy_device_id_mode_constructs_cleanly(self):
        """舊用法（只給 device_id + mode）應正常建構"""
        mapping = HeartbeatMapping(
            point_name="hb",
            device_id="pcs1",
            mode=HeartbeatMode.TOGGLE,
        )
        assert mapping.device_id == "pcs1"
        assert mapping.mode is HeartbeatMode.TOGGLE
        assert mapping.value_generator is None
        assert mapping.target is None

    def test_legacy_trait_mode_constructs_cleanly(self):
        """舊用法 trait 模式"""
        mapping = HeartbeatMapping(
            point_name="hb",
            trait="pcs",
            mode=HeartbeatMode.INCREMENT,
            increment_max=100,
        )
        assert mapping.trait == "pcs"
        assert mapping.increment_max == 100

    def test_legacy_no_deprecation_warning(self):
        """AC4：舊 API 路徑不應 emit DeprecationWarning（legacy-only 路徑安靜）"""
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")  # 捕獲所有警告
            HeartbeatMapping(
                point_name="hb",
                device_id="pcs1",
                mode=HeartbeatMode.TOGGLE,
            )
        # 篩出 DeprecationWarning（忽略其他可能的 warning）
        deprecation = [w for w in captured if issubclass(w.category, DeprecationWarning)]
        assert deprecation == [], f"Legacy path 不應 emit DeprecationWarning，但發現：{deprecation}"

    def test_legacy_constant_mode_with_custom_value(self):
        """舊 constant_value 設定應可正常傳入（只要不混 value_generator）"""
        mapping = HeartbeatMapping(
            point_name="hb",
            device_id="pcs1",
            mode=HeartbeatMode.CONSTANT,
            constant_value=42,
        )
        assert mapping.constant_value == 42

    def test_legacy_neither_device_nor_trait_raises(self):
        """AC4：仍保留舊驗證 — legacy 路徑未設 device_id/trait/target → raise"""
        with pytest.raises(ValueError, match="Must set either"):
            HeartbeatMapping(point_name="hb")

    def test_legacy_both_device_and_trait_raises(self):
        """AC4：舊驗證 — device_id + trait 同時設 → raise"""
        with pytest.raises(ValueError, match="Cannot set both"):
            HeartbeatMapping(point_name="hb", device_id="pcs1", trait="pcs")
