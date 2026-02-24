"""SystemAlarmEvaluator 單元測試"""

from csp_lib.equipment.alarm.definition import AlarmLevel
from csp_lib.equipment.alarm.state import AlarmEventType
from csp_lib.monitor.alarm import SystemAlarmEvaluator, create_system_alarm_evaluators
from csp_lib.monitor.collector import SystemMetrics
from csp_lib.monitor.config import MetricThresholds, MonitorConfig


# ================ create_system_alarm_evaluators ================


class TestCreateEvaluators:
    def test_default_creates_cpu_ram_disk(self):
        config = MonitorConfig()
        evaluators = create_system_alarm_evaluators(config)
        assert "cpu_percent" in evaluators
        assert "ram_percent" in evaluators
        assert "disk:/" in evaluators

    def test_cpu_disabled(self):
        config = MonitorConfig(enable_cpu=False)
        evaluators = create_system_alarm_evaluators(config)
        assert "cpu_percent" not in evaluators

    def test_ram_disabled(self):
        config = MonitorConfig(enable_ram=False)
        evaluators = create_system_alarm_evaluators(config)
        assert "ram_percent" not in evaluators

    def test_disk_disabled(self):
        config = MonitorConfig(enable_disk=False)
        evaluators = create_system_alarm_evaluators(config)
        assert not any(k.startswith("disk:") for k in evaluators)

    def test_multi_disk_paths(self):
        config = MonitorConfig(disk_paths=("/", "/data", "/backup"))
        evaluators = create_system_alarm_evaluators(config)
        assert "disk:/" in evaluators
        assert "disk:/data" in evaluators
        assert "disk:/backup" in evaluators

    def test_alarm_levels(self):
        config = MonitorConfig()
        evaluators = create_system_alarm_evaluators(config)

        cpu_alarms = evaluators["cpu_percent"].get_alarms()
        assert cpu_alarms[0].level == AlarmLevel.WARNING

        ram_alarms = evaluators["ram_percent"].get_alarms()
        assert ram_alarms[0].level == AlarmLevel.WARNING

        disk_alarms = evaluators["disk:/"].get_alarms()
        assert disk_alarms[0].level == AlarmLevel.ALARM

    def test_disk_alarm_code_format(self):
        config = MonitorConfig(disk_paths=("/", "/data"))
        evaluators = create_system_alarm_evaluators(config)

        root_alarms = evaluators["disk:/"].get_alarms()
        assert root_alarms[0].code == "SYS_DISK_HIGH_root"

        data_alarms = evaluators["disk:/data"].get_alarms()
        assert data_alarms[0].code == "SYS_DISK_HIGH_data"


# ================ SystemAlarmEvaluator ================


class TestSystemAlarmEvaluator:
    def _make_metrics(self, cpu=50.0, ram=50.0, disk_pct=50.0) -> SystemMetrics:
        return SystemMetrics(
            cpu_percent=cpu,
            ram_percent=ram,
            disk_usage={"/": disk_pct},
        )

    def test_no_alarms_under_threshold(self):
        config = MonitorConfig(hysteresis_activate=1, hysteresis_clear=1)
        evaluator = SystemAlarmEvaluator(config)
        events = evaluator.evaluate(self._make_metrics(cpu=50, ram=50, disk_pct=50))
        assert events == []
        assert evaluator.active_alarms == []

    def test_cpu_alarm_with_hysteresis(self):
        config = MonitorConfig(hysteresis_activate=3, hysteresis_clear=3)
        evaluator = SystemAlarmEvaluator(config)
        high = self._make_metrics(cpu=95)

        # 前 2 次不應觸發
        assert evaluator.evaluate(high) == []
        assert evaluator.evaluate(high) == []

        # 第 3 次觸發
        events = evaluator.evaluate(high)
        assert len(events) == 1
        assert events[0].event_type == AlarmEventType.TRIGGERED
        assert events[0].alarm.code == "SYS_CPU_HIGH"
        assert "SYS_CPU_HIGH" in evaluator.active_alarms

    def test_cpu_alarm_clear_with_hysteresis(self):
        config = MonitorConfig(hysteresis_activate=1, hysteresis_clear=3)
        evaluator = SystemAlarmEvaluator(config)
        high = self._make_metrics(cpu=95)
        low = self._make_metrics(cpu=50)

        # 觸發
        events = evaluator.evaluate(high)
        assert len(events) == 1

        # 前 2 次解除不夠
        assert evaluator.evaluate(low) == []
        assert evaluator.evaluate(low) == []

        # 第 3 次清除
        events = evaluator.evaluate(low)
        assert len(events) == 1
        assert events[0].event_type == AlarmEventType.CLEARED
        assert evaluator.active_alarms == []

    def test_ram_alarm(self):
        config = MonitorConfig(hysteresis_activate=1, hysteresis_clear=1)
        evaluator = SystemAlarmEvaluator(config)
        events = evaluator.evaluate(self._make_metrics(ram=90))
        assert len(events) == 1
        assert events[0].alarm.code == "SYS_RAM_HIGH"

    def test_disk_alarm(self):
        config = MonitorConfig(hysteresis_activate=1, hysteresis_clear=1)
        evaluator = SystemAlarmEvaluator(config)
        events = evaluator.evaluate(self._make_metrics(disk_pct=98))
        assert len(events) == 1
        assert events[0].alarm.code == "SYS_DISK_HIGH_root"

    def test_multiple_alarms_at_once(self):
        config = MonitorConfig(hysteresis_activate=1, hysteresis_clear=1)
        evaluator = SystemAlarmEvaluator(config)
        events = evaluator.evaluate(self._make_metrics(cpu=95, ram=90, disk_pct=98))
        codes = {e.alarm.code for e in events}
        assert "SYS_CPU_HIGH" in codes
        assert "SYS_RAM_HIGH" in codes
        assert "SYS_DISK_HIGH_root" in codes

    def test_custom_thresholds(self):
        config = MonitorConfig(
            thresholds=MetricThresholds(cpu_percent=50.0),
            hysteresis_activate=1,
            hysteresis_clear=1,
        )
        evaluator = SystemAlarmEvaluator(config)
        events = evaluator.evaluate(self._make_metrics(cpu=55))
        assert len(events) == 1
        assert events[0].alarm.code == "SYS_CPU_HIGH"

    def test_state_manager_accessible(self):
        evaluator = SystemAlarmEvaluator(MonitorConfig())
        assert evaluator.state_manager is not None
