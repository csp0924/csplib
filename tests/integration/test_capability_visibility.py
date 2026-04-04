# =============== Integration Tests - Capability Visibility ===============
#
# DeviceRegistry capability P2 功能測試
#
# 測試覆蓋：
# - get_capability_map: 正確映射、空 registry
# - get_capability_map_text: 格式化輸出
# - capability_health: responsive / non-responsive 設備統計
# - refresh_capability_traits: 同步新增/移除 capability traits

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from csp_lib.integration.registry import DeviceRegistry


def _make_device(
    device_id: str,
    capabilities: dict | None = None,
    responsive: bool = True,
) -> MagicMock:
    """建立 mock AsyncModbusDevice（含 capabilities）"""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).capabilities = PropertyMock(return_value=capabilities or {})

    def _has_capability(cap):
        name = cap.name if hasattr(cap, "name") else str(cap)
        return name in (capabilities or {})

    dev.has_capability = MagicMock(side_effect=_has_capability)
    return dev


# ======================== get_capability_map ========================


class TestGetCapabilityMap:
    """get_capability_map 測試"""

    def test_basic_mapping(self):
        """正確建立 capability → device_ids 映射"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"active_power_control": MagicMock(), "soc_readable": MagicMock()})
        d2 = _make_device("d2", {"active_power_control": MagicMock()})
        reg.register(d1)
        reg.register(d2)

        cap_map = reg.get_capability_map()
        assert set(cap_map.keys()) == {"active_power_control", "soc_readable"}
        assert cap_map["active_power_control"] == ["d1", "d2"]
        assert cap_map["soc_readable"] == ["d1"]

    def test_empty_registry(self):
        """空 registry → 空 dict"""
        reg = DeviceRegistry()
        assert reg.get_capability_map() == {}

    def test_no_capabilities(self):
        """設備無 capability → 空映射"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", capabilities={}))
        assert reg.get_capability_map() == {}

    def test_device_ids_sorted(self):
        """device_ids 列表按字母排序"""
        reg = DeviceRegistry()
        reg.register(_make_device("z_dev", {"cap_a": MagicMock()}))
        reg.register(_make_device("a_dev", {"cap_a": MagicMock()}))

        cap_map = reg.get_capability_map()
        assert cap_map["cap_a"] == ["a_dev", "z_dev"]


# ======================== get_capability_map_text ========================


class TestGetCapabilityMapText:
    """get_capability_map_text 測試"""

    def test_formatted_output(self):
        """格式化輸出包含 capability 名稱、設備數、設備列表"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", {"heartbeat": MagicMock(), "measurable": MagicMock()}))
        reg.register(_make_device("d2", {"heartbeat": MagicMock()}))

        text = reg.get_capability_map_text()
        assert "heartbeat (2 devices): d1, d2" in text
        assert "measurable (1 devices): d1" in text

    def test_empty_returns_empty_string(self):
        """空 registry → 空字串"""
        reg = DeviceRegistry()
        assert reg.get_capability_map_text() == ""

    def test_alphabetical_order(self):
        """capability 名稱按字母排序"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", {"zebra": MagicMock(), "alpha": MagicMock()}))

        text = reg.get_capability_map_text()
        lines = text.split("\n")
        assert lines[0].startswith("alpha")
        assert lines[1].startswith("zebra")


# ======================== capability_health ========================


class TestCapabilityHealth:
    """capability_health 測試"""

    def test_all_responsive(self):
        """全部 responsive → ratio = 1.0"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", {"heartbeat": MagicMock()}, responsive=True))
        reg.register(_make_device("d2", {"heartbeat": MagicMock()}, responsive=True))

        health = reg.capability_health("heartbeat")
        assert health["capability"] == "heartbeat"
        assert health["total_devices"] == 2
        assert health["responsive_devices"] == 2
        assert health["responsive_ratio"] == 1.0
        assert len(health["devices"]) == 2

    def test_partial_responsive(self):
        """部分 responsive → ratio 正確"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", {"cap_x": MagicMock()}, responsive=True))
        reg.register(_make_device("d2", {"cap_x": MagicMock()}, responsive=False))

        health = reg.capability_health("cap_x")
        assert health["total_devices"] == 2
        assert health["responsive_devices"] == 1
        assert health["responsive_ratio"] == 0.5

    def test_no_devices(self):
        """無設備具備能力 → total=0, ratio=0.0"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", capabilities={}))

        health = reg.capability_health("nonexistent")
        assert health["total_devices"] == 0
        assert health["responsive_ratio"] == 0.0

    def test_device_details(self):
        """devices 包含每台設備的 device_id 和 is_responsive"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", {"cap": MagicMock()}, responsive=True))
        reg.register(_make_device("d2", {"cap": MagicMock()}, responsive=False))

        health = reg.capability_health("cap")
        details = {d["device_id"]: d["is_responsive"] for d in health["devices"]}
        assert details["d1"] is True
        assert details["d2"] is False

    def test_capability_object_name(self):
        """支援 Capability 物件（取 .name）"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", {"heartbeat": MagicMock()}))

        cap_obj = MagicMock()
        cap_obj.name = "heartbeat"
        health = reg.capability_health(cap_obj)
        assert health["capability"] == "heartbeat"


# ======================== refresh_capability_traits ========================


class TestRefreshCapabilityTraits:
    """refresh_capability_traits 測試"""

    def test_add_new_capability_trait(self):
        """新增 capability 後 refresh → 新 trait 出現"""
        reg = DeviceRegistry()
        caps = {"heartbeat": MagicMock()}
        dev = _make_device("d1", capabilities=caps)
        reg.register_with_capabilities(dev)

        # 模擬設備新增能力
        caps["measurable"] = MagicMock()
        reg.refresh_capability_traits("d1")

        traits = reg.get_traits("d1")
        assert "cap:measurable" in traits
        assert "cap:heartbeat" in traits

    def test_remove_capability_trait(self):
        """移除 capability 後 refresh → 舊 trait 消失"""
        reg = DeviceRegistry()
        caps = {"heartbeat": MagicMock(), "measurable": MagicMock()}
        dev = _make_device("d1", capabilities=caps)
        reg.register_with_capabilities(dev)

        # 模擬設備移除能力
        del caps["measurable"]
        reg.refresh_capability_traits("d1")

        traits = reg.get_traits("d1")
        assert "cap:heartbeat" in traits
        assert "cap:measurable" not in traits

    def test_extra_traits_preserved(self):
        """refresh 不影響非 cap: 前綴的 traits"""
        reg = DeviceRegistry()
        dev = _make_device("d1", capabilities={"heartbeat": MagicMock()})
        reg.register_with_capabilities(dev, extra_traits=["pcs", "inverter"])

        reg.refresh_capability_traits("d1")

        traits = reg.get_traits("d1")
        assert "pcs" in traits
        assert "inverter" in traits

    def test_unregistered_device_raises(self):
        """未註冊設備 → KeyError"""
        reg = DeviceRegistry()
        with pytest.raises(KeyError):
            reg.refresh_capability_traits("no_such_device")

    def test_no_change_when_unchanged(self):
        """capabilities 不變時 refresh 不影響 traits"""
        reg = DeviceRegistry()
        dev = _make_device("d1", capabilities={"heartbeat": MagicMock()})
        reg.register_with_capabilities(dev, extra_traits=["pcs"])

        reg.refresh_capability_traits("d1")

        traits = reg.get_traits("d1")
        assert traits == {"pcs", "cap:heartbeat"}
