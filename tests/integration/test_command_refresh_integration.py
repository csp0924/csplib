# =============== v0.8.1 CommandRefresh × SystemController Integration Tests ===============
#
# 涵蓋 Feature spec AC5 / AC6：
#   - AC5：opt-in 預設關閉（CommandRefreshConfig default enabled=False）
#   - AC5：Builder.command_refresh() 正確建立 service
#   - 啟停順序：executor → command_refresh → heartbeat（啟動）
#                heartbeat → command_refresh → executor（停止）
#   - command_refresh property 反映狀態（None / service）

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import HeartbeatMapping
from csp_lib.integration.system_controller import (
    CommandRefreshConfig,
    HeartbeatConfig,
    SystemController,
    SystemControllerConfig,
)


def _make_device(device_id: str, responsive: bool = True, protected: bool = False) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=True)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    type(dev).is_healthy = PropertyMock(return_value=responsive and not protected)
    type(dev).latest_values = PropertyMock(return_value={})
    type(dev).active_alarms = PropertyMock(return_value=[])
    type(dev).all_point_names = PropertyMock(return_value={"heartbeat", "p_set", "q_set"})
    dev.write = AsyncMock()
    unsub_fn = MagicMock()
    dev.on = MagicMock(return_value=unsub_fn)
    return dev


# ─────────────── AC5: opt-in 預設關閉 ───────────────


class TestCommandRefreshOptIn:
    """AC5：CommandRefreshConfig 預設 enabled=False；SystemController 不建立 service"""

    def test_default_config_no_command_refresh(self):
        """AC5：SystemControllerConfig() 預設 command_refresh is None"""
        config = SystemControllerConfig()
        assert config.command_refresh is None

    def test_command_refresh_config_defaults(self):
        """AC5：CommandRefreshConfig 預設值 enabled=False"""
        cfg = CommandRefreshConfig()
        assert cfg.enabled is False
        assert cfg.refresh_interval == 1.0
        assert cfg.device_filter is None

    def test_controller_without_config_command_refresh_is_none(self):
        """AC5：未設定 command_refresh 時 controller.command_refresh is None"""
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig())
        assert sc.command_refresh is None

    def test_controller_with_disabled_config_command_refresh_is_none(self):
        """AC5：CommandRefreshConfig(enabled=False) → 仍不建立 service"""
        reg = DeviceRegistry()
        config = SystemControllerConfig(command_refresh=CommandRefreshConfig(enabled=False))
        sc = SystemController(reg, config)
        assert sc.command_refresh is None


# ─────────────── AC5: enabled=True 建立 service ───────────────


class TestCommandRefreshEnabled:
    """AC5：CommandRefreshConfig(enabled=True) → SystemController 建立 & 生命週期管理"""

    async def test_builder_enables_command_refresh(self):
        """AC5：Builder.command_refresh(enabled=True) 正確建立 config"""
        config = SystemControllerConfig.builder().command_refresh(interval_seconds=0.1, enabled=True).build()
        assert config.command_refresh is not None
        assert config.command_refresh.enabled is True
        assert config.command_refresh.refresh_interval == 0.1
        assert config.command_refresh.device_filter is None

    async def test_builder_with_device_filter(self):
        """AC5：devices=[...] 轉為 frozenset"""
        config = (
            SystemControllerConfig.builder()
            .command_refresh(interval_seconds=0.5, enabled=True, devices=["pcs1", "pcs2"])
            .build()
        )
        assert config.command_refresh is not None
        assert config.command_refresh.device_filter == frozenset({"pcs1", "pcs2"})

    async def test_builder_devices_none_yields_no_filter(self):
        """AC5：devices=None → device_filter=None（refresh 全部）"""
        config = SystemControllerConfig.builder().command_refresh(enabled=True, devices=None).build()
        assert config.command_refresh is not None
        assert config.command_refresh.device_filter is None

    async def test_lifecycle_starts_and_stops_service(self):
        """AC5：controller 啟動後 command_refresh.is_running 為 True；停止後為 False"""
        reg = DeviceRegistry()
        config = SystemControllerConfig.builder().command_refresh(interval_seconds=0.1, enabled=True).build()
        sc = SystemController(reg, config)

        # 啟動前：service 已建立但未 is_running
        assert sc.command_refresh is not None
        assert sc.command_refresh.is_running is False

        async with sc:
            # 允許一小段時間讓 task 實際排進 event loop
            await asyncio.sleep(0.05)
            assert sc.command_refresh is not None
            assert sc.command_refresh.is_running is True

        # 停止後應已關閉
        assert sc.command_refresh is not None
        assert sc.command_refresh.is_running is False


# ─────────────── 啟動/停止順序（與 heartbeat 配合）───────────────


class TestStartStopOrder:
    """AC5：啟動順序 command_refresh 在 heartbeat 之前；停止反向"""

    async def test_start_order_refresh_before_heartbeat(self):
        """mock command_refresh 與 heartbeat 的 _on_start，記錄呼叫順序"""
        reg = DeviceRegistry()
        # 準備 heartbeat（需要真實 device 才能讓 HeartbeatService 建立）
        dev = _make_device("pcs1")
        reg.register(dev, traits=["pcs"])

        config = (
            SystemControllerConfig.builder()
            .heartbeat(
                HeartbeatConfig(
                    mappings=[HeartbeatMapping(point_name="heartbeat", device_id="pcs1")],
                    interval_seconds=0.2,
                )
            )
            .command_refresh(interval_seconds=0.2, enabled=True)
            .build()
        )
        sc = SystemController(reg, config)

        # 記錄呼叫順序
        events: list[str] = []

        original_refresh_start = sc._command_refresh.start  # type: ignore[union-attr]
        original_hb_start = sc._heartbeat.start  # type: ignore[union-attr]
        original_refresh_stop = sc._command_refresh.stop  # type: ignore[union-attr]
        original_hb_stop = sc._heartbeat.stop  # type: ignore[union-attr]

        async def refresh_start():
            events.append("refresh_start")
            await original_refresh_start()

        async def hb_start():
            events.append("hb_start")
            await original_hb_start()

        async def refresh_stop():
            events.append("refresh_stop")
            await original_refresh_stop()

        async def hb_stop():
            events.append("hb_stop")
            await original_hb_stop()

        sc._command_refresh.start = refresh_start  # type: ignore[method-assign,union-attr]
        sc._heartbeat.start = hb_start  # type: ignore[method-assign,union-attr]
        sc._command_refresh.stop = refresh_stop  # type: ignore[method-assign,union-attr]
        sc._heartbeat.stop = hb_stop  # type: ignore[method-assign,union-attr]

        async with sc:
            await asyncio.sleep(0.05)

        # 啟動：refresh 應早於 heartbeat
        start_events = [e for e in events if "start" in e]
        assert start_events == ["refresh_start", "hb_start"], f"啟動順序錯誤：{events}"

        # 停止：heartbeat 應早於 refresh
        stop_events = [e for e in events if "stop" in e]
        assert stop_events == ["hb_stop", "refresh_stop"], f"停止順序錯誤：{events}"


# ─────────────── command_refresh property 語義 ───────────────


class TestCommandRefreshProperty:
    """command_refresh property 在不同配置下的回傳值"""

    def test_property_returns_none_when_disabled(self):
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig())
        assert sc.command_refresh is None

    def test_property_returns_service_when_enabled(self):
        reg = DeviceRegistry()
        config = SystemControllerConfig.builder().command_refresh(interval_seconds=0.5, enabled=True).build()
        sc = SystemController(reg, config)
        # 啟動前 property 已回傳 service 實例（只是 not is_running）
        assert sc.command_refresh is not None
        assert sc.command_refresh.is_running is False

    @pytest.mark.parametrize(
        "interval,expected",
        [
            (0.1, 0.1),
            (1.0, 1.0),
            (5.5, 5.5),
        ],
    )
    def test_property_interval_matches_config(self, interval: float, expected: float):
        """AC5：service 使用 config 的 refresh_interval"""
        reg = DeviceRegistry()
        config = SystemControllerConfig.builder().command_refresh(interval_seconds=interval, enabled=True).build()
        sc = SystemController(reg, config)
        assert sc.command_refresh is not None
        # 驗證內部 _interval 一致
        assert sc.command_refresh._interval == expected


# ─────────────── Builder 不應覆蓋其他設定 ───────────────


class TestBuilderDoesNotOverrideOtherConfig:
    """AC5：command_refresh() builder 方法不應影響其他欄位"""

    def test_builder_only_sets_command_refresh_field(self):
        """AC5：只設 command_refresh，其他欄位應維持預設"""
        config = SystemControllerConfig.builder().command_refresh(enabled=True).build()
        assert config.command_refresh is not None
        # 其他欄位維持預設
        assert config.heartbeat is None
        assert config.heartbeat_mappings == []
        assert config.protection_rules == []
        assert config.auto_stop_on_alarm is True

    def test_heartbeat_config_field_name_is_heartbeat(self):
        """AC5：HeartbeatConfig 透過 builder.heartbeat(cfg) 寫入 config.heartbeat"""
        cfg = HeartbeatConfig(
            mappings=[HeartbeatMapping(point_name="hb", device_id="pcs1")],
            interval_seconds=0.5,
        )
        config = SystemControllerConfig.builder().heartbeat(cfg).build()
        assert config.heartbeat is cfg
        assert config.command_refresh is None
