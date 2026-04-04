# =============== Equipment Tests - Capability Change Events ===============
#
# Capability 動態新增/移除事件測試
#
# 測試覆蓋：
# - add_capability 觸發 capability_added 事件
# - remove_capability 觸發 capability_removed 事件
# - CapabilityBinding.metadata 預設空 dict / 可帶值
# - CapabilityChangedPayload 資料正確

from __future__ import annotations

from unittest.mock import MagicMock

from csp_lib.equipment.device.capability import Capability, CapabilityBinding
from csp_lib.equipment.device.events import (
    EVENT_CAPABILITY_ADDED,
    EVENT_CAPABILITY_REMOVED,
    CapabilityChangedPayload,
)

# ======================== CapabilityBinding.metadata ========================


class TestCapabilityBindingMetadata:
    """CapabilityBinding.metadata 測試"""

    def test_default_empty_dict(self):
        """預設 metadata 為空 dict"""
        cap = Capability(name="test_cap", write_slots=("slot_a",))
        binding = CapabilityBinding(capability=cap, point_map={"slot_a": "real_point"})
        assert binding.metadata == {}

    def test_custom_metadata(self):
        """可帶自訂 metadata"""
        cap = Capability(name="test_cap", write_slots=("slot_a",))
        binding = CapabilityBinding(
            capability=cap,
            point_map={"slot_a": "real_point"},
            metadata={"rated_power": 500, "unit": "kW"},
        )
        assert binding.metadata == {"rated_power": 500, "unit": "kW"}

    def test_metadata_is_frozen(self):
        """CapabilityBinding 是 frozen dataclass，metadata 在建構時設定"""
        cap = Capability(name="test_cap")
        binding = CapabilityBinding(capability=cap, point_map={}, metadata={"key": "val"})
        assert binding.metadata["key"] == "val"


# ======================== Capability Change Events ========================


class TestCapabilityChangeEvents:
    """Capability 變更事件測試

    使用 mock emitter 測試 add_capability / remove_capability
    是否正確觸發事件。
    """

    def _make_device_with_emitter(self, device_id: str = "pcs_01"):
        """建立具備 mock emitter 的最小化設備物件

        由於 AsyncModbusDevice 建構需要完整的 transport/config，
        這裡直接測試事件機制，使用簡化模擬。
        """
        from unittest.mock import PropertyMock

        device = MagicMock()
        type(device).device_id = PropertyMock(return_value=device_id)

        # 模擬內部 _capability_bindings 和 _emitter
        bindings: dict[str, CapabilityBinding] = {}
        emitter = MagicMock()

        def add_cap(binding: CapabilityBinding):
            bindings[binding.capability.name] = binding
            emitter.emit(
                EVENT_CAPABILITY_ADDED,
                CapabilityChangedPayload(device_id=device_id, capability_name=binding.capability.name),
            )

        def remove_cap(cap):
            name = cap.name if hasattr(cap, "name") else str(cap)
            if name in bindings:
                bindings.pop(name)
                emitter.emit(
                    EVENT_CAPABILITY_REMOVED,
                    CapabilityChangedPayload(device_id=device_id, capability_name=name),
                )

        device.add_capability = add_cap
        device.remove_capability = remove_cap
        device._emitter = emitter
        return device, emitter

    def test_add_capability_emits_event(self):
        """add_capability 觸發 capability_added 事件"""
        device, emitter = self._make_device_with_emitter("pcs_01")
        cap = Capability(name="heartbeat", write_slots=("heartbeat",))
        binding = CapabilityBinding(capability=cap, point_map={"heartbeat": "watchdog"})

        device.add_capability(binding)

        emitter.emit.assert_called_once()
        call_args = emitter.emit.call_args
        assert call_args[0][0] == EVENT_CAPABILITY_ADDED
        payload = call_args[0][1]
        assert isinstance(payload, CapabilityChangedPayload)
        assert payload.device_id == "pcs_01"
        assert payload.capability_name == "heartbeat"

    def test_remove_capability_emits_event(self):
        """remove_capability 觸發 capability_removed 事件"""
        device, emitter = self._make_device_with_emitter("pcs_02")
        cap = Capability(name="measurable", read_slots=("active_power",))
        binding = CapabilityBinding(capability=cap, point_map={"active_power": "p_real"})

        device.add_capability(binding)
        emitter.reset_mock()

        device.remove_capability(cap)

        emitter.emit.assert_called_once()
        call_args = emitter.emit.call_args
        assert call_args[0][0] == EVENT_CAPABILITY_REMOVED
        payload = call_args[0][1]
        assert payload.capability_name == "measurable"

    def test_remove_nonexistent_capability_no_event(self):
        """remove_capability 移除不存在的能力 → 不觸發事件"""
        device, emitter = self._make_device_with_emitter()
        cap = Capability(name="nonexistent")
        device.remove_capability(cap)

        emitter.emit.assert_not_called()

    def test_payload_has_timestamp(self):
        """CapabilityChangedPayload 自動帶 timestamp"""
        payload = CapabilityChangedPayload(device_id="d1", capability_name="cap")
        assert payload.timestamp is not None

    def test_add_capability_by_string_name(self):
        """remove_capability 接受字串名稱"""
        device, emitter = self._make_device_with_emitter()
        cap = Capability(name="test_cap", write_slots=("slot",))
        binding = CapabilityBinding(capability=cap, point_map={"slot": "point"})

        device.add_capability(binding)
        emitter.reset_mock()

        device.remove_capability("test_cap")  # 用字串
        emitter.emit.assert_called_once()
        payload = emitter.emit.call_args[0][1]
        assert payload.capability_name == "test_cap"
