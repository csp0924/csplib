# =============== v0.8.1 HeartbeatConfig + Builder Integration Tests ===============
#
# 涵蓋 Feature spec AC4 / AC5：
#   - AC4：Builder.heartbeat(HeartbeatConfig(...)) 新 API 路徑
#   - AC4：Builder.heartbeat(mappings=..., interval=..., ...) 舊 kwargs 路徑維持行為
#   - AC4：舊 kwargs 路徑不應 emit DeprecationWarning
#   - AC4：舊行為 smoke test — value 序列與 v0.8.0 一致
#   - AC5：CommandRefreshConfig Builder 各式 devices 輸入的處理
#
# Builder 進入點：
#   - SystemControllerConfig.builder().heartbeat(...)
#   - SystemControllerConfig.builder().command_refresh(...)

from __future__ import annotations

import asyncio
import warnings
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from csp_lib.integration.heartbeat_generators import ToggleGenerator
from csp_lib.integration.heartbeat_targets import DeviceHeartbeatTarget
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import HeartbeatMapping, HeartbeatMode
from csp_lib.integration.system_controller import (
    HeartbeatConfig,
    SystemController,
    SystemControllerConfig,
)


def _make_device(device_id: str, responsive: bool = True) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=True)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=False)
    type(dev).is_healthy = PropertyMock(return_value=responsive)
    type(dev).latest_values = PropertyMock(return_value={})
    type(dev).active_alarms = PropertyMock(return_value=[])
    type(dev).all_point_names = PropertyMock(return_value={"hb", "p_set", "q_set"})
    dev.write = AsyncMock()
    unsub_fn = MagicMock()
    dev.on = MagicMock(return_value=unsub_fn)
    return dev


# ─────────────── Builder.heartbeat(HeartbeatConfig) 新 API ───────────────


class TestBuilderAcceptsHeartbeatConfig:
    """AC4：Builder.heartbeat(HeartbeatConfig(...)) 物件路徑"""

    def test_passing_heartbeat_config_object(self):
        """AC4：傳入 HeartbeatConfig 應寫入 config.heartbeat 欄位"""
        dev = _make_device("pcs1")
        target = DeviceHeartbeatTarget(dev, "hb")
        hb_cfg = HeartbeatConfig(
            mappings=[
                HeartbeatMapping(
                    point_name="hb",
                    value_generator=ToggleGenerator(),
                    target=target,
                )
            ],
            interval_seconds=0.5,
            targets=[],
        )
        config = SystemControllerConfig.builder().heartbeat(hb_cfg).build()

        assert config.heartbeat is hb_cfg
        assert config.heartbeat.interval_seconds == 0.5

    def test_heartbeat_config_with_targets_kwarg(self):
        """AC4：HeartbeatConfig 支援 targets 欄位（獨立 target 列表）"""
        dev = _make_device("pcs1")
        target = DeviceHeartbeatTarget(dev, "hb")
        hb_cfg = HeartbeatConfig(
            mappings=[],
            interval_seconds=0.3,
            targets=[target],
        )
        config = SystemControllerConfig.builder().heartbeat(hb_cfg).build()
        assert config.heartbeat is hb_cfg
        assert config.heartbeat.targets == [target]

    def test_heartbeat_config_defaults(self):
        """AC4：HeartbeatConfig 預設值"""
        cfg = HeartbeatConfig()
        assert cfg.mappings == []
        assert cfg.interval_seconds == 1.0
        assert cfg.use_capability is False
        assert cfg.capability_mode is HeartbeatMode.TOGGLE
        assert cfg.capability_constant_value == 1
        assert cfg.capability_increment_max == 65535
        assert cfg.targets == []


# ─────────────── Builder.heartbeat(mappings=..., ...) 舊 kwargs 路徑 ───────────────


class TestBuilderLegacyKwargs:
    """AC4：舊 kwargs 路徑向後相容，不 emit DeprecationWarning"""

    def test_legacy_kwargs_path_sets_legacy_fields(self):
        """AC4：舊 kwargs 直接寫入 config 的 legacy 6 欄位"""
        mapping = HeartbeatMapping(point_name="hb", device_id="pcs1", mode=HeartbeatMode.INCREMENT)
        config = (
            SystemControllerConfig.builder()
            .heartbeat(
                mappings=[mapping],
                interval=2.0,
                use_capability=True,
                mode=HeartbeatMode.INCREMENT,
            )
            .build()
        )
        # 舊欄位被設值
        assert config.heartbeat_mappings == [mapping]
        assert config.heartbeat_interval == 2.0
        assert config.use_heartbeat_capability is True
        assert config.heartbeat_capability_mode is HeartbeatMode.INCREMENT
        # 新欄位為 None（因為走舊路徑）
        assert config.heartbeat is None

    def test_legacy_kwargs_no_deprecation_warning(self):
        """AC4：舊 kwargs 路徑不應 emit DeprecationWarning"""
        mapping = HeartbeatMapping(point_name="hb", device_id="pcs1", mode=HeartbeatMode.TOGGLE)
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            SystemControllerConfig.builder().heartbeat(
                mappings=[mapping],
                interval=1.0,
                use_capability=False,
                mode=HeartbeatMode.TOGGLE,
            ).build()

        deprecation = [w for w in captured if issubclass(w.category, DeprecationWarning)]
        assert deprecation == [], f"Legacy kwargs 不應 emit DeprecationWarning：{deprecation}"


# ─────────────── 舊行為 smoke：value 序列與 v0.8.0 一致 ───────────────


class TestLegacyBehaviorUnchanged:
    """AC4：舊 API 的 heartbeat 行為（TOGGLE / INCREMENT）與 v0.8.0 完全一致"""

    async def test_legacy_toggle_sequence(self):
        """舊 kwargs 走 config.heartbeat_mappings → 序列應為 1, 0, 1, ..."""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev, traits=["pcs"])

        config = (
            SystemControllerConfig.builder()
            .heartbeat(
                mappings=[HeartbeatMapping(point_name="hb", device_id="pcs1", mode=HeartbeatMode.TOGGLE)],
                interval=0.05,
            )
            .build()
        )
        sc = SystemController(reg, config)

        async with sc:
            await asyncio.sleep(0.18)

        # 收集所有 hb write 的值（過濾掉其他點位的 write）
        hb_values = [c.args[1] for c in dev.write.await_args_list if c.args[0] == "hb"]
        assert len(hb_values) >= 3
        assert hb_values[0] == 1
        assert hb_values[1] == 0
        assert hb_values[2] == 1

    async def test_legacy_increment_sequence(self):
        """舊 kwargs + INCREMENT 模式：應看到遞增序列"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev, traits=["pcs"])

        mapping = HeartbeatMapping(
            point_name="hb",
            device_id="pcs1",
            mode=HeartbeatMode.INCREMENT,
            increment_max=3,
        )
        config = SystemControllerConfig.builder().heartbeat(mappings=[mapping], interval=0.05).build()
        sc = SystemController(reg, config)

        async with sc:
            await asyncio.sleep(0.25)

        hb_values = [c.args[1] for c in dev.write.await_args_list if c.args[0] == "hb"]
        assert len(hb_values) >= 4
        # 序列為 1, 2, 3, 0, 1, ...
        assert hb_values[0] == 1
        assert hb_values[1] == 2
        assert hb_values[2] == 3
        assert hb_values[3] == 0


# ─────────────── CommandRefreshConfig Builder 各式輸入 ───────────────


class TestCommandRefreshBuilder:
    """AC5：command_refresh() builder 對 devices 參數的處理"""

    def test_devices_list_converts_to_frozenset(self):
        """AC5：devices=['pcs1', 'pcs2'] → device_filter=frozenset({'pcs1', 'pcs2'})"""
        config = (
            SystemControllerConfig.builder()
            .command_refresh(interval_seconds=0.5, enabled=True, devices=["pcs1", "pcs2"])
            .build()
        )
        assert config.command_refresh is not None
        assert config.command_refresh.device_filter == frozenset({"pcs1", "pcs2"})

    def test_devices_none_yields_none_filter(self):
        """AC5：devices=None → device_filter=None（表示不過濾，refresh 全部）"""
        config = (
            SystemControllerConfig.builder().command_refresh(interval_seconds=0.5, enabled=True, devices=None).build()
        )
        assert config.command_refresh is not None
        assert config.command_refresh.device_filter is None

    def test_devices_empty_list_yields_none_filter(self):
        """AC5：devices=[] → 依實作以 frozenset(empty_list) is falsy 判斷；
        實作使用 `frozenset(devices) if devices else None`，空 list 視為 None。
        """
        config = (
            SystemControllerConfig.builder().command_refresh(interval_seconds=0.5, enabled=True, devices=[]).build()
        )
        assert config.command_refresh is not None
        # 空 list 在 `if devices` 下為 falsy → device_filter=None
        assert config.command_refresh.device_filter is None

    def test_default_interval_is_1_0(self):
        """AC5：command_refresh() 預設 interval_seconds=1.0"""
        config = SystemControllerConfig.builder().command_refresh(enabled=True).build()
        assert config.command_refresh is not None
        assert config.command_refresh.refresh_interval == 1.0

    def test_default_enabled_is_true_in_builder(self):
        """AC5：builder.command_refresh() 預設 enabled=True（呼叫者明示啟用）

        注意：CommandRefreshConfig 的 default 是 False，但 builder 方法的預設是 True。
        這是刻意的 UX 設計 — 呼叫 builder.command_refresh() 即表示要啟用。
        """
        config = SystemControllerConfig.builder().command_refresh().build()
        assert config.command_refresh is not None
        assert config.command_refresh.enabled is True


# ─────────────── 新舊 Heartbeat API 優先權 ───────────────


class TestHeartbeatNewApiPrecedence:
    """當 config.heartbeat 與 config.heartbeat_mappings 同時存在，以新版為準"""

    async def test_new_heartbeat_config_takes_precedence_over_legacy_fields(self):
        """AC4：config.heartbeat 有值時，SystemController 忽略 legacy heartbeat_mappings"""
        reg = DeviceRegistry()
        dev_new = _make_device("pcs_new")
        dev_legacy = _make_device("pcs_legacy")
        reg.register(dev_new, traits=["pcs"])
        reg.register(dev_legacy, traits=["pcs"])

        # 同時設定新舊欄位
        config = SystemControllerConfig(
            heartbeat=HeartbeatConfig(
                mappings=[HeartbeatMapping(point_name="hb", device_id="pcs_new")],
                interval_seconds=0.05,
            ),
            heartbeat_mappings=[HeartbeatMapping(point_name="hb", device_id="pcs_legacy")],
        )
        sc = SystemController(reg, config)

        async with sc:
            await asyncio.sleep(0.15)

        # 新版配置指向 pcs_new：應有寫入
        assert dev_new.write.await_count >= 2
        # 舊版配置指向 pcs_legacy：應被忽略，無寫入（除了其他非 hb 點位，這裡沒有）
        # 只檢查 hb 點位
        legacy_hb_calls = [c for c in dev_legacy.write.await_args_list if c.args[0] == "hb"]
        assert legacy_hb_calls == []
