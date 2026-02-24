"""Tests for distributed config."""

from csp_lib.integration.distributed.config import DistributedConfig, RemoteSiteConfig


class TestRemoteSiteConfig:
    def test_default_channels(self):
        cfg = RemoteSiteConfig(site_id="site_bms", device_ids=["bms_1"])
        assert cfg.effective_command_channel == "channel:commands:site_bms:write"
        assert cfg.effective_result_channel == "channel:commands:site_bms:result"

    def test_custom_channels(self):
        cfg = RemoteSiteConfig(
            site_id="site_bms",
            device_ids=["bms_1"],
            command_channel="custom:cmd",
            result_channel="custom:res",
        )
        assert cfg.effective_command_channel == "custom:cmd"
        assert cfg.effective_result_channel == "custom:res"

    def test_empty_device_ids(self):
        cfg = RemoteSiteConfig(site_id="empty")
        assert cfg.device_ids == []


class TestDistributedConfig:
    def test_all_device_ids(self):
        cfg = DistributedConfig(
            sites=[
                RemoteSiteConfig(site_id="s1", device_ids=["d1", "d2"]),
                RemoteSiteConfig(site_id="s2", device_ids=["d3"]),
            ],
        )
        assert cfg.all_device_ids == ["d1", "d2", "d3"]

    def test_device_site_map(self):
        s1 = RemoteSiteConfig(site_id="s1", device_ids=["d1", "d2"])
        s2 = RemoteSiteConfig(site_id="s2", device_ids=["d3"])
        cfg = DistributedConfig(sites=[s1, s2])
        dsm = cfg.device_site_map
        assert dsm["d1"] is s1
        assert dsm["d2"] is s1
        assert dsm["d3"] is s2

    def test_empty_config(self):
        cfg = DistributedConfig()
        assert cfg.all_device_ids == []
        assert cfg.device_site_map == {}
        assert cfg.poll_interval == 1.0
        assert cfg.command_timeout == 5.0
        assert cfg.system_alarm_on_device_offline is True

    def test_defaults(self):
        cfg = DistributedConfig(poll_interval=2.0, command_timeout=10.0)
        assert cfg.poll_interval == 2.0
        assert cfg.command_timeout == 10.0

    def test_trait_device_map(self):
        cfg = DistributedConfig(
            trait_device_map={"inverter": ["inv_1", "inv_2"]},
        )
        assert cfg.trait_device_map["inverter"] == ["inv_1", "inv_2"]
