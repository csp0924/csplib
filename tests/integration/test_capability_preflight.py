# =============== Integration Tests - Capability Preflight ===============
#
# validate_capabilities + preflight_check 測試
#
# 測試覆蓋：
# - validate_capabilities: 足夠 / 不足 / trait_filter 過濾
# - preflight_check: 無需求 / 通過 / 失敗列表 / strict mode raises

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.equipment.device.capability import ACTIVE_POWER_CONTROL, HEARTBEAT, MEASURABLE
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CapabilityRequirement


def _make_device(
    device_id: str,
    capabilities: dict | None = None,
    responsive: bool = True,
) -> MagicMock:
    """建立 mock AsyncModbusDevice（含 capabilities 與 has_capability）"""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).capabilities = PropertyMock(return_value=capabilities or {})

    def _has_capability(cap):
        name = cap.name if hasattr(cap, "name") else str(cap)
        return name in (capabilities or {})

    dev.has_capability = MagicMock(side_effect=_has_capability)
    return dev


# ======================== validate_capabilities ========================


class TestValidateCapabilities:
    """DeviceRegistry.validate_capabilities 測試"""

    def test_enough_devices(self):
        """需求滿足 → 空列表"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", {"heartbeat": MagicMock()}))
        reg.register(_make_device("d2", {"heartbeat": MagicMock()}))

        failures = reg.validate_capabilities(
            [
                CapabilityRequirement(capability=HEARTBEAT, min_count=2),
            ]
        )
        assert failures == []

    def test_insufficient_devices(self):
        """設備不足 → 回傳失敗描述"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", {"heartbeat": MagicMock()}))

        failures = reg.validate_capabilities(
            [
                CapabilityRequirement(capability=HEARTBEAT, min_count=3),
            ]
        )
        assert len(failures) == 1
        assert "heartbeat" in failures[0].lower()
        assert "3" in failures[0]

    def test_multiple_requirements(self):
        """多個需求，部分滿足"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", {"heartbeat": MagicMock(), "active_power_control": MagicMock()}))

        failures = reg.validate_capabilities(
            [
                CapabilityRequirement(capability=HEARTBEAT, min_count=1),
                CapabilityRequirement(capability=ACTIVE_POWER_CONTROL, min_count=2),
            ]
        )
        assert len(failures) == 1
        assert "active_power_control" in failures[0]

    def test_trait_filter(self):
        """trait_filter 限定特定 trait 的設備"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"heartbeat": MagicMock()})
        d2 = _make_device("d2", {"heartbeat": MagicMock()})
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["meter"])

        # 要求 trait=pcs 的設備至少 2 台有 heartbeat → 只有 1 台
        failures = reg.validate_capabilities(
            [
                CapabilityRequirement(capability=HEARTBEAT, min_count=2, trait_filter="pcs"),
            ]
        )
        assert len(failures) == 1
        assert "pcs" in failures[0]

    def test_trait_filter_enough(self):
        """trait_filter 滿足需求"""
        reg = DeviceRegistry()
        d1 = _make_device("d1", {"measurable": MagicMock()})
        d2 = _make_device("d2", {"measurable": MagicMock()})
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        failures = reg.validate_capabilities(
            [
                CapabilityRequirement(capability=MEASURABLE, min_count=2, trait_filter="pcs"),
            ]
        )
        assert failures == []

    def test_empty_requirements(self):
        """無需求 → 空列表"""
        reg = DeviceRegistry()
        assert reg.validate_capabilities([]) == []

    def test_no_devices_registered(self):
        """Registry 為空但有需求 → 失敗"""
        reg = DeviceRegistry()
        failures = reg.validate_capabilities(
            [
                CapabilityRequirement(capability=HEARTBEAT, min_count=1),
            ]
        )
        assert len(failures) == 1


# ======================== preflight_check ========================


class TestPreflightCheck:
    """SystemController.preflight_check 測試

    使用最小化 mock 測試 preflight_check 邏輯：
    直接建構 SystemController 的核心依賴。
    """

    def _make_controller(self, registry, requirements=None, strict=False):
        """建構最小化的 SystemController mock（只測試 preflight_check）"""
        # 直接模擬 preflight_check 的行為邏輯而非建構整個 SystemController
        controller = MagicMock()
        controller._registry = registry

        # 模擬 config
        config = MagicMock()
        config.capability_requirements = requirements or []
        config.strict_capability_check = strict
        controller._config = config

        def preflight_check():
            if not config.capability_requirements:
                return []
            failures = registry.validate_capabilities(config.capability_requirements)
            if failures and config.strict_capability_check:
                raise ConfigurationError(f"Preflight capability check failed: {'; '.join(failures)}")
            return failures

        controller.preflight_check = preflight_check
        return controller

    def test_no_requirements(self):
        """無 capability_requirements → 空列表"""
        reg = DeviceRegistry()
        ctrl = self._make_controller(reg, requirements=[])
        assert ctrl.preflight_check() == []

    def test_all_pass(self):
        """所有需求滿足 → 空列表"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", {"heartbeat": MagicMock()}))

        ctrl = self._make_controller(
            reg,
            requirements=[
                CapabilityRequirement(capability=HEARTBEAT, min_count=1),
            ],
        )
        assert ctrl.preflight_check() == []

    def test_failures_returned(self):
        """需求不滿足 → 回傳失敗列表"""
        reg = DeviceRegistry()

        ctrl = self._make_controller(
            reg,
            requirements=[
                CapabilityRequirement(capability=HEARTBEAT, min_count=1),
            ],
        )
        failures = ctrl.preflight_check()
        assert len(failures) == 1

    def test_strict_mode_raises(self):
        """strict_capability_check=True + 失敗 → raise ConfigurationError"""
        reg = DeviceRegistry()

        ctrl = self._make_controller(
            reg,
            requirements=[CapabilityRequirement(capability=HEARTBEAT, min_count=1)],
            strict=True,
        )
        with pytest.raises(ConfigurationError, match="Preflight capability check failed"):
            ctrl.preflight_check()

    def test_strict_mode_no_raise_on_pass(self):
        """strict_capability_check=True + 滿足 → 不 raise"""
        reg = DeviceRegistry()
        reg.register(_make_device("d1", {"heartbeat": MagicMock()}))

        ctrl = self._make_controller(
            reg,
            requirements=[CapabilityRequirement(capability=HEARTBEAT, min_count=1)],
            strict=True,
        )
        assert ctrl.preflight_check() == []
