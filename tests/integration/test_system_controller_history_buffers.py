"""SystemController HistoryBuffer 多來源配置測試（v0.9.x）。

驗證：
1. 舊 ``data_feed_mapping`` 路徑：自動建 PVDataService，``history_buffers`` property
   回傳 ``{"pv_power": PVDataService(...)}``，``pv_service`` property 亦可取到。
2. 新 ``history_buffers`` + ``data_feed_mappings`` 路徑：多 key 都能從 property 取回；
   若 key="pv_power" 是 PVDataService 也 expose 於 pv_service（相容）。
3. ``SystemControllerConfigBuilder.history_buffer(key, buffer, mapping)`` fluent method：
   - 可多次呼叫註冊多個 key
   - 重複註冊同一 key raise ValueError
   - 不傳 mapping 時只註冊 buffer（外部自行 append）
4. ``history_buffers`` property 是 snapshot（dict copy，修改不影響內部狀態）。
"""

from __future__ import annotations

import pytest

from csp_lib.controller.services import HistoryBuffer, PVDataService
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import DataFeedMapping
from csp_lib.integration.system_controller import (
    SystemController,
    SystemControllerConfig,
    SystemControllerConfigBuilder,
)


class TestSystemControllerLegacyHistoryBuffers:
    """舊 ``data_feed_mapping`` 路徑相容性"""

    def test_legacy_config_exposes_pv_power_key_in_history_buffers(self):
        reg = DeviceRegistry()
        config = SystemControllerConfig(
            data_feed_mapping=DataFeedMapping(device_id="pcs1", point_name="pv_power"),
            pv_max_history=100,
        )
        sc = SystemController(reg, config)

        buffers = sc.history_buffers
        assert "pv_power" in buffers
        # legacy 路徑自動建 PVDataService（HistoryBuffer 的 subclass）
        assert isinstance(buffers["pv_power"], HistoryBuffer)
        assert isinstance(buffers["pv_power"], PVDataService)
        assert buffers["pv_power"].max_history == 100

    def test_legacy_config_pv_service_property_still_works(self):
        reg = DeviceRegistry()
        config = SystemControllerConfig(
            data_feed_mapping=DataFeedMapping(device_id="pcs1", point_name="pv_power"),
        )
        sc = SystemController(reg, config)

        # 舊 pv_service property 應與 history_buffers["pv_power"] 為同一物件
        assert sc.pv_service is not None
        assert sc.pv_service is sc.history_buffers["pv_power"]

    def test_no_data_feed_config_has_empty_history_buffers(self):
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig())

        assert sc.history_buffers == {}
        assert sc.pv_service is None


class TestSystemControllerNewHistoryBuffers:
    """v0.9.x+ 新路徑：config.history_buffers + config.data_feed_mappings"""

    def test_multi_key_buffers_exposed_via_property(self):
        reg = DeviceRegistry()
        pv_buf = HistoryBuffer(max_history=50)
        grid_buf = HistoryBuffer(max_history=60)
        soc_buf = HistoryBuffer(max_history=20)

        config = SystemControllerConfig(
            history_buffers={"pv_power": pv_buf, "grid_power": grid_buf, "battery_soc": soc_buf},
            data_feed_mappings={
                "pv_power": DataFeedMapping(device_id="meter1", point_name="pv_power"),
                "grid_power": DataFeedMapping(device_id="meter2", point_name="grid_power"),
            },
        )
        sc = SystemController(reg, config)

        buffers = sc.history_buffers
        assert set(buffers.keys()) == {"pv_power", "grid_power", "battery_soc"}
        assert buffers["pv_power"] is pv_buf
        assert buffers["grid_power"] is grid_buf
        assert buffers["battery_soc"] is soc_buf

    def test_new_path_pv_power_as_plain_history_buffer_hides_from_pv_service(self):
        """若 pv_power 是純 HistoryBuffer（非 PVDataService subclass），
        pv_service property 回 None（不向下相容至非 PVDataService 類型）
        """
        reg = DeviceRegistry()
        pv_buf = HistoryBuffer(max_history=50)  # 純 HistoryBuffer，非 PVDataService

        config = SystemControllerConfig(
            history_buffers={"pv_power": pv_buf},
            data_feed_mappings={"pv_power": DataFeedMapping(device_id="m1", point_name="pv_power")},
        )
        sc = SystemController(reg, config)

        # history_buffers 仍可取得
        assert sc.history_buffers["pv_power"] is pv_buf
        # pv_service 不 expose 非 PVDataService 的 buffer（看 source 的
        # ``if isinstance(legacy_buf, PVDataService)`` 分支）
        assert sc.pv_service is None

    def test_new_path_pv_power_as_pv_data_service_exposes_via_pv_service(self):
        """若 pv_power 是 PVDataService subclass，pv_service property 應能取到（相容）"""
        reg = DeviceRegistry()
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            pv_svc = PVDataService(max_history=50)

        config = SystemControllerConfig(
            history_buffers={"pv_power": pv_svc},
            data_feed_mappings={"pv_power": DataFeedMapping(device_id="m1", point_name="pv_power")},
        )
        sc = SystemController(reg, config)

        assert sc.pv_service is pv_svc
        assert sc.history_buffers["pv_power"] is pv_svc

    def test_history_buffers_property_is_readonly_view(self):
        """history_buffers property 回傳 MappingProxyType 唯讀視圖，caller 無法修改。"""
        reg = DeviceRegistry()
        pv_buf = HistoryBuffer()
        config = SystemControllerConfig(history_buffers={"pv_power": pv_buf})
        sc = SystemController(reg, config)

        snapshot = sc.history_buffers
        with pytest.raises(TypeError):
            snapshot["injected"] = HistoryBuffer()  # type: ignore[index]
        # MappingProxyType 不提供 MutableMapping API（pop/update 等）
        assert not hasattr(snapshot, "pop")

        # 內部不受影響
        assert sc.history_buffers["pv_power"] is pv_buf


class TestConfigBuilderHistoryBufferFluent:
    """SystemControllerConfigBuilder.history_buffer fluent method"""

    def test_register_single_buffer_with_mapping(self):
        pv_buf = HistoryBuffer(max_history=100)
        mapping = DataFeedMapping(device_id="meter1", point_name="pv_power")

        config = SystemControllerConfigBuilder().history_buffer("pv_power", pv_buf, mapping).build()

        assert config.history_buffers == {"pv_power": pv_buf}
        assert config.data_feed_mappings == {"pv_power": mapping}

    def test_register_multiple_keys(self):
        pv_buf = HistoryBuffer()
        grid_buf = HistoryBuffer()
        pv_map = DataFeedMapping(device_id="m1", point_name="pv_power")
        grid_map = DataFeedMapping(device_id="m2", point_name="grid_power")

        config = (
            SystemControllerConfigBuilder()
            .history_buffer("pv_power", pv_buf, pv_map)
            .history_buffer("grid_power", grid_buf, grid_map)
            .build()
        )

        assert set(config.history_buffers.keys()) == {"pv_power", "grid_power"}  # type: ignore[union-attr]
        assert set(config.data_feed_mappings.keys()) == {"pv_power", "grid_power"}  # type: ignore[union-attr]

    def test_register_buffer_without_mapping(self):
        """不傳 mapping 時只註冊 buffer（外部自行 append；不會被 DataFeed attach）"""
        buf = HistoryBuffer()

        config = SystemControllerConfigBuilder().history_buffer("pv_power", buf).build()

        assert config.history_buffers == {"pv_power": buf}
        # mapping 為空 → data_feed_mappings 應為 None（build 時 ``or None``）
        assert config.data_feed_mappings is None

    def test_duplicate_key_raises(self):
        """同 key 重複註冊應 fail-fast（bug-validation-fail-loud）"""
        builder = SystemControllerConfigBuilder().history_buffer("pv_power", HistoryBuffer())

        with pytest.raises(ValueError, match="already registered"):
            builder.history_buffer("pv_power", HistoryBuffer())

    def test_builder_result_builds_functional_controller(self):
        """Builder fluent → config → SystemController 的整合路徑不崩"""
        reg = DeviceRegistry()
        pv_buf = HistoryBuffer(max_history=30)
        mapping = DataFeedMapping(device_id="meter1", point_name="pv_power")

        config = SystemControllerConfigBuilder().history_buffer("pv_power", pv_buf, mapping).build()
        sc = SystemController(reg, config)

        assert sc.history_buffers["pv_power"] is pv_buf
