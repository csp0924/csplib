# =============== Hierarchical Transport NO_CHANGE Wire-format Tests (v0.8.0 WI-V080-004) ===============
#
# 驗證 DispatchCommand / StatusReport 的 JSON 編解碼：
#   - NO_CHANGE 軸以 null 輸出；float 軸原值輸出
#   - from_dict(None) 還原為 NO_CHANGE
#   - round-trip 保持語義
#   - 跨語言互通所需的 wire format 一致

from __future__ import annotations

import json
from datetime import datetime, timezone

from csp_lib.controller.core import Command
from csp_lib.controller.core.command import NO_CHANGE, is_no_change
from csp_lib.integration.hierarchical.status import ExecutorStatus, StatusReport
from csp_lib.integration.hierarchical.transport import DispatchCommand, DispatchPriority

# =============== DispatchCommand to_dict ===============


class TestDispatchCommandToDict:
    """DispatchCommand.to_dict 對 NO_CHANGE 輸出 null"""

    def test_no_change_p_serialized_as_none(self):
        cmd = DispatchCommand(
            source_site_id="site-a",
            target_site_id="site-b",
            command=Command(p_target=NO_CHANGE, q_target=100.0),
        )
        d = cmd.to_dict()
        assert d["command"]["p_target"] is None
        assert d["command"]["q_target"] == 100.0

    def test_no_change_q_serialized_as_none(self):
        cmd = DispatchCommand(
            source_site_id="site-a",
            target_site_id="site-b",
            command=Command(p_target=50.0, q_target=NO_CHANGE),
        )
        d = cmd.to_dict()
        assert d["command"]["p_target"] == 50.0
        assert d["command"]["q_target"] is None

    def test_both_no_change_both_none(self):
        cmd = DispatchCommand(
            source_site_id="a",
            target_site_id="b",
            command=Command(p_target=NO_CHANGE, q_target=NO_CHANGE),
        )
        d = cmd.to_dict()
        assert d["command"]["p_target"] is None
        assert d["command"]["q_target"] is None

    def test_pure_float_unaffected(self):
        """無 NO_CHANGE 的 Command 序列化不受影響"""
        cmd = DispatchCommand(
            source_site_id="a",
            target_site_id="b",
            command=Command(p_target=10.0, q_target=-5.5),
        )
        d = cmd.to_dict()
        assert d["command"]["p_target"] == 10.0
        assert d["command"]["q_target"] == -5.5

    def test_to_dict_is_json_serializable(self):
        """NO_CHANGE 編碼後 to_dict 產物必須可 JSON 序列化（跨語言互通）"""
        cmd = DispatchCommand(
            source_site_id="a",
            target_site_id="b",
            command=Command(p_target=NO_CHANGE, q_target=0.0),
        )
        # 不能拋例外
        s = json.dumps(cmd.to_dict())
        assert "null" in s


# =============== DispatchCommand from_dict ===============


class TestDispatchCommandFromDict:
    """DispatchCommand.from_dict 把 None 還原為 NO_CHANGE"""

    def test_none_p_restored_to_no_change(self):
        data = {
            "source_site_id": "a",
            "target_site_id": "b",
            "command": {"p_target": None, "q_target": 100.0},
            "priority": DispatchPriority.NORMAL.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {},
        }
        cmd = DispatchCommand.from_dict(data)
        assert is_no_change(cmd.command.p_target)
        assert cmd.command.q_target == 100.0

    def test_none_q_restored_to_no_change(self):
        data = {
            "source_site_id": "a",
            "target_site_id": "b",
            "command": {"p_target": 50.0, "q_target": None},
            "priority": DispatchPriority.NORMAL.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {},
        }
        cmd = DispatchCommand.from_dict(data)
        assert cmd.command.p_target == 50.0
        assert is_no_change(cmd.command.q_target)


# =============== Round-trip ===============


class TestDispatchCommandRoundTrip:
    """encode → decode 後應得到等效 Command"""

    def test_round_trip_with_no_change(self):
        orig = DispatchCommand(
            source_site_id="a",
            target_site_id="b",
            command=Command(p_target=NO_CHANGE, q_target=100.0),
            priority=DispatchPriority.MANUAL,
        )
        decoded = DispatchCommand.from_dict(orig.to_dict())
        assert is_no_change(decoded.command.p_target)
        assert decoded.command.q_target == 100.0
        assert decoded.priority == DispatchPriority.MANUAL

    def test_round_trip_both_no_change(self):
        orig = DispatchCommand(
            source_site_id="a",
            target_site_id="b",
            command=Command(p_target=NO_CHANGE, q_target=NO_CHANGE),
        )
        decoded = DispatchCommand.from_dict(orig.to_dict())
        assert is_no_change(decoded.command.p_target)
        assert is_no_change(decoded.command.q_target)

    def test_round_trip_pure_float(self):
        orig = DispatchCommand(
            source_site_id="a",
            target_site_id="b",
            command=Command(p_target=10.0, q_target=-5.5),
        )
        decoded = DispatchCommand.from_dict(orig.to_dict())
        assert decoded.command.p_target == 10.0
        assert decoded.command.q_target == -5.5

    def test_round_trip_via_json_string(self):
        """經 JSON string 中轉，驗證跨語言/跨程序實際路徑"""
        orig = DispatchCommand(
            source_site_id="a",
            target_site_id="b",
            command=Command(p_target=NO_CHANGE, q_target=50.0),
        )
        s = json.dumps(orig.to_dict())
        decoded = DispatchCommand.from_dict(json.loads(s))
        assert is_no_change(decoded.command.p_target)
        assert decoded.command.q_target == 50.0


# =============== StatusReport ===============


class TestStatusReportWireFormat:
    """StatusReport.last_command 的 NO_CHANGE 同樣以 null 編碼"""

    def test_last_command_no_change_p_serialized_as_none(self):
        report = StatusReport(
            site_id="site-a",
            status=ExecutorStatus(
                strategy_name="pq",
                last_command=Command(p_target=NO_CHANGE, q_target=100.0),
            ),
        )
        d = report.to_dict()
        cmd = d["status"]["last_command"]
        assert cmd["p_target"] is None
        assert cmd["q_target"] == 100.0

    def test_from_dict_restores_no_change(self):
        data = {
            "site_id": "site-a",
            "status": {
                "strategy_name": "pq",
                "last_command": {"p_target": None, "q_target": 50.0, "is_fallback": False},
                "active_overrides": [],
                "base_modes": ["pq"],
                "is_running": True,
                "device_count": 1,
                "healthy_device_count": 1,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {},
        }
        report = StatusReport.from_dict(data)
        assert is_no_change(report.status.last_command.p_target)
        assert report.status.last_command.q_target == 50.0

    def test_round_trip_with_no_change(self):
        orig = StatusReport(
            site_id="site-a",
            status=ExecutorStatus(
                strategy_name="cascading",
                last_command=Command(p_target=NO_CHANGE, q_target=NO_CHANGE),
                is_running=True,
                device_count=2,
            ),
        )
        decoded = StatusReport.from_dict(orig.to_dict())
        assert is_no_change(decoded.status.last_command.p_target)
        assert is_no_change(decoded.status.last_command.q_target)
        assert decoded.status.strategy_name == "cascading"
        assert decoded.status.is_running is True
        assert decoded.status.device_count == 2

    def test_status_report_is_json_serializable_with_no_change(self):
        report = StatusReport(
            site_id="site-a",
            status=ExecutorStatus(last_command=Command(p_target=NO_CHANGE, q_target=0.0)),
        )
        s = json.dumps(report.to_dict())
        assert "null" in s

    def test_is_fallback_flag_preserved(self):
        orig = StatusReport(
            site_id="site-a",
            status=ExecutorStatus(last_command=Command(p_target=0.0, q_target=0.0, is_fallback=True)),
        )
        decoded = StatusReport.from_dict(orig.to_dict())
        assert decoded.status.last_command.is_fallback is True
