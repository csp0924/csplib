# =============== v0.8.1 HeartbeatValueGenerator Tests ===============
#
# 涵蓋 Feature spec AC4：新 Protocol-driven value generator API。
#
# 測試對象：
#   - ToggleGenerator：交替 0/1，per-key 狀態隔離
#   - IncrementGenerator：遞增到 max_value 後歸零，建構時邊界驗證
#   - ConstantGenerator：固定值，建構時邊界驗證
#   - HeartbeatValueGenerator Protocol：runtime_checkable 結構子型別檢查
#
# 驗證要點：
#   1. 單一 key 連續呼叫的序列正確性
#   2. 多 key 狀態獨立不互相污染
#   3. reset(key) / reset(None) 的行為區分
#   4. 建構參數邊界（min / max / 0 / 超出 Modbus 16-bit 範圍）
#   5. @runtime_checkable Protocol 對所有 impl 都成立

from __future__ import annotations

import pytest

from csp_lib.integration.heartbeat_generators import (
    ConstantGenerator,
    HeartbeatValueGenerator,
    IncrementGenerator,
    ToggleGenerator,
)

# ─────────────── ToggleGenerator ───────────────


class TestToggleGenerator:
    """ToggleGenerator：每個 key 在 0 / 1 交替（初始 0，首次呼叫回 1）"""

    def test_next_alternates_for_single_key(self):
        """AC4：同一 key 連續呼叫 next 回 1, 0, 1, 0, ... 交替"""
        gen = ToggleGenerator()
        assert gen.next("pcs1") == 1
        assert gen.next("pcs1") == 0
        assert gen.next("pcs1") == 1
        assert gen.next("pcs1") == 0

    def test_independent_state_across_keys(self):
        """AC4：不同 key 狀態獨立；交錯呼叫各自維持 0/1 序列"""
        gen = ToggleGenerator()
        # 兩個 key 交錯呼叫
        assert gen.next("pcs1") == 1  # pcs1: 0 -> 1
        assert gen.next("pcs2") == 1  # pcs2: 0 -> 1（不受 pcs1 影響）
        assert gen.next("pcs1") == 0  # pcs1: 1 -> 0
        assert gen.next("pcs2") == 0  # pcs2: 1 -> 0
        assert gen.next("pcs1") == 1  # pcs1: 0 -> 1
        assert gen.next("pcs2") == 1  # pcs2: 0 -> 1

    def test_reset_single_key(self):
        """AC4：reset(key) 清除指定 key，其他 key 狀態保留"""
        gen = ToggleGenerator()
        gen.next("pcs1")  # pcs1 -> 1
        gen.next("pcs2")  # pcs2 -> 1

        gen.reset("pcs1")
        # pcs1 狀態被清除 → 下次呼叫從 0 開始，回 1
        assert gen.next("pcs1") == 1
        # pcs2 狀態保留 → 下次繼續從 1 翻為 0
        assert gen.next("pcs2") == 0

    def test_reset_all_with_none(self):
        """AC4：reset(None) 清除所有 key 的狀態"""
        gen = ToggleGenerator()
        gen.next("pcs1")  # -> 1
        gen.next("pcs2")  # -> 1

        gen.reset(None)
        # 所有 key 重置 → 下次都從 0 開始，回 1
        assert gen.next("pcs1") == 1
        assert gen.next("pcs2") == 1

    def test_reset_unknown_key_is_noop(self):
        """AC4：reset 未知 key 應靜默忽略（不 raise）"""
        gen = ToggleGenerator()
        # 不 raise
        gen.reset("never_used")


# ─────────────── IncrementGenerator ───────────────


class TestIncrementGenerator:
    """IncrementGenerator：遞增到 max_value 後歸零"""

    def test_next_wraps_at_max_value_plus_one(self):
        """AC4：max_value=3 → 序列為 1, 2, 3, 0, 1, 2, 3, 0（wrap 在 max+1）"""
        gen = IncrementGenerator(max_value=3)
        values = [gen.next("pcs1") for _ in range(8)]
        assert values == [1, 2, 3, 0, 1, 2, 3, 0]

    def test_default_max_value_65535(self):
        """AC4：預設 max_value=65535（Modbus 16-bit register 上界）"""
        gen = IncrementGenerator()
        # 首幾次呼叫應正常遞增，未 wrap
        assert gen.next("pcs1") == 1
        assert gen.next("pcs1") == 2

    def test_independent_state_across_keys(self):
        """AC4：不同 key 計數獨立"""
        gen = IncrementGenerator(max_value=5)
        assert gen.next("pcs1") == 1
        assert gen.next("pcs2") == 1  # pcs2 從 0 開始，不受 pcs1 影響
        assert gen.next("pcs1") == 2
        assert gen.next("pcs2") == 2

    def test_reset_single_key(self):
        """AC4：reset(key) 只清特定 key"""
        gen = IncrementGenerator(max_value=10)
        gen.next("pcs1")  # 1
        gen.next("pcs1")  # 2
        gen.next("pcs2")  # 1

        gen.reset("pcs1")
        # pcs1 重新從 0 開始 → 下次 1
        assert gen.next("pcs1") == 1
        # pcs2 繼續 → 下次 2
        assert gen.next("pcs2") == 2

    def test_reset_all(self):
        """AC4：reset(None) 清全部"""
        gen = IncrementGenerator(max_value=10)
        gen.next("pcs1")
        gen.next("pcs2")
        gen.reset(None)
        assert gen.next("pcs1") == 1
        assert gen.next("pcs2") == 1

    def test_init_max_value_zero_raises(self):
        """AC4：max_value=0 超出合法範圍 [1, 65535]，raise ValueError"""
        with pytest.raises(ValueError, match="max_value must be in"):
            IncrementGenerator(max_value=0)

    def test_init_max_value_65536_raises(self):
        """AC4：max_value=65536 超出 Modbus 16-bit 上界，raise ValueError"""
        with pytest.raises(ValueError, match="max_value must be in"):
            IncrementGenerator(max_value=65536)

    def test_init_negative_max_value_raises(self):
        """AC4：負數 max_value 應 raise"""
        with pytest.raises(ValueError, match="max_value must be in"):
            IncrementGenerator(max_value=-1)

    def test_init_max_value_1_valid(self):
        """AC4：邊界值 max_value=1 合法，序列為 1, 0, 1, 0"""
        gen = IncrementGenerator(max_value=1)
        values = [gen.next("k") for _ in range(4)]
        assert values == [1, 0, 1, 0]

    def test_init_max_value_65535_valid(self):
        """AC4：邊界值 max_value=65535 合法"""
        gen = IncrementGenerator(max_value=65535)
        assert gen.next("k") == 1


# ─────────────── ConstantGenerator ───────────────


class TestConstantGenerator:
    """ConstantGenerator：固定值，無狀態"""

    def test_next_returns_fixed_value(self):
        """AC4：ConstantGenerator(value=42) 任何 key 呼叫都回 42"""
        gen = ConstantGenerator(value=42)
        assert gen.next("pcs1") == 42
        assert gen.next("pcs1") == 42
        assert gen.next("pcs2") == 42

    def test_default_value_is_1(self):
        """AC4：預設 value=1"""
        gen = ConstantGenerator()
        assert gen.next("anything") == 1

    def test_reset_is_noop(self):
        """AC4：ConstantGenerator 無狀態，reset 不影響行為"""
        gen = ConstantGenerator(value=7)
        gen.reset("pcs1")
        gen.reset(None)
        assert gen.next("pcs1") == 7  # 仍回 7

    def test_init_negative_value_raises(self):
        """AC4：value=-1 超出 Modbus register 合法範圍 [0, 65535]"""
        with pytest.raises(ValueError, match="value must be in"):
            ConstantGenerator(value=-1)

    def test_init_value_65536_raises(self):
        """AC4：value=65536 超出 Modbus 16-bit 上界"""
        with pytest.raises(ValueError, match="value must be in"):
            ConstantGenerator(value=65536)

    def test_init_value_0_valid(self):
        """AC4：邊界值 value=0 合法"""
        gen = ConstantGenerator(value=0)
        assert gen.next("k") == 0

    def test_init_value_65535_valid(self):
        """AC4：邊界值 value=65535 合法"""
        gen = ConstantGenerator(value=65535)
        assert gen.next("k") == 65535


# ─────────────── Protocol 結構子型別驗證 ───────────────


class TestHeartbeatValueGeneratorProtocol:
    """@runtime_checkable Protocol：三個內建 impl 皆應滿足"""

    def test_toggle_generator_satisfies_protocol(self):
        """AC4：ToggleGenerator 應被識別為 HeartbeatValueGenerator"""
        assert isinstance(ToggleGenerator(), HeartbeatValueGenerator)

    def test_increment_generator_satisfies_protocol(self):
        """AC4：IncrementGenerator 應被識別為 HeartbeatValueGenerator"""
        assert isinstance(IncrementGenerator(), HeartbeatValueGenerator)

    def test_constant_generator_satisfies_protocol(self):
        """AC4：ConstantGenerator 應被識別為 HeartbeatValueGenerator"""
        assert isinstance(ConstantGenerator(), HeartbeatValueGenerator)

    def test_custom_generator_satisfies_protocol(self):
        """AC4：使用者自訂類別只要實作 next/reset 即滿足 Protocol"""

        class MyGen:
            def next(self, key: str) -> int:
                return 3

            def reset(self, key: str | None = None) -> None:
                pass

        assert isinstance(MyGen(), HeartbeatValueGenerator)

    def test_incomplete_impl_does_not_satisfy_protocol(self):
        """AC4：只有 next 沒 reset 的類別不滿足 Protocol"""

        class MissingReset:
            def next(self, key: str) -> int:
                return 0

        # runtime_checkable Protocol 會檢查兩個方法是否都存在
        assert not isinstance(MissingReset(), HeartbeatValueGenerator)
